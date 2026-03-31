import json
import re
import pytz
import os
from datetime import datetime

class DecisionEngine:
    def __init__(self, gemini_client):
        self.client = gemini_client
        # 🛠️ Fixed: Indentation corrected and using verified model name
        self.model_name = "gemini-2.5-flash" 
        self.ist = pytz.timezone('Asia/Kolkata')
        
        try:
            print(f"🧠 Decision Engine Initialized with Model: {self.model_name}")
        except: 
            pass

    def clean_json_response(self, raw_text):
        try:
            raw_text = raw_text.strip()
            if raw_text.startswith("```json"):
                raw_text = raw_text[7:]
            elif raw_text.startswith("```"):
                raw_text = raw_text[3:]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]
                
            json_match = re.search(r'\{.*\}', raw_text, re.DOTALL)
            if json_match:
                return json_match.group(0)
            return raw_text
        except: 
            return raw_text

    def get_final_verdict(self, global_data, vix_india, atr_value=None):
        now_ist = datetime.now(self.ist)
        
        # --- 🕒 TIME-PHASE LOGIC ---
        current_hour = now_ist.hour
        current_minute = now_ist.minute

        time_phase = "UNKNOWN"
        focus_rule = ""

        if (current_hour == 9 and current_minute >= 10) or (current_hour == 10 and current_minute == 0):
            time_phase = "MORNING_GLOBAL_PHASE (9:10 AM - 10:00 AM)"
            focus_rule = "Give 80% weight to Asian Pre-Market, US Futures, and Overnight Macro. Evaluate Gap-up/Gap-down sustainability."
        elif (current_hour == 10 and current_minute > 0) or (current_hour == 11) or (current_hour == 12 and current_minute <= 30):
            time_phase = "MIDDAY_LOCAL_PHASE (10:00 AM - 12:30 PM)"
            focus_rule = "Give 80% weight to Live Market Breadth (A/D Ratio) and India VIX. Ignore morning gaps, focus on current Nifty trend."
        elif (current_hour == 12 and current_minute > 30) or (current_hour >= 13):
            time_phase = "AFTERNOON_EURO_PHASE (12:30 PM - 3:15 PM)"
            focus_rule = "Give 80% weight to European Open (DAX/FTSE) and US Futures. Anticipate strong FII afternoon flows."
        else:
            time_phase = "OFF_MARKET_PHASE"
            focus_rule = "Market closed. Evaluate pure global macro for positional overnight carrying."

        stats = global_data.get('stats', {})
        macro_risk = "HIGH" if stats.get('Dollar_Index', 0) > 0.4 or stats.get('US_10Y_Yield', 0) > 0.4 else "STABLE"

        news_data = global_data.get('news_sentiment', {})
        overall_news_mood = news_data.get('overall_mood', 'Neutral')
        
        asian_bias = global_data.get('asian_bias', {})
        asian_sentiment = asian_bias.get('asian_sentiment', 'Neutral')
        net_asian_momentum = asian_bias.get('net_asian_momentum', 0.0)

        pcr_value = global_data.get('pcr', 'UNKNOWN') 
        max_pain = global_data.get('max_pain', 'UNKNOWN')
                
        market_breadth = global_data.get('market_breadth', {})
        advances = market_breadth.get('advances', 0)
        declines = market_breadth.get('declines', 0)
        ad_ratio = float(market_breadth.get('ratio', 1.0))
        
        vwap_stretch = float(global_data.get('macro_vwap_stretch', 0.0))
        
        total_bids, total_asks = 0, 0
        advanced_metrics = global_data.get('advanced_metrics', {})
        for token, data in advanced_metrics.items():
            total_bids += data.get("total_buy_qty", 0)
            total_asks += data.get("total_sell_qty", 0)
            
        # 🚀 Extracting Sector-Sense Z-Scores from live_market.json
        sector_sense_data = {}
        try:
            if os.path.exists("live_market.json"):
                with open("live_market.json", "r") as f:
                    live_data = json.load(f)
                    sector_sense_data = live_data.get("sector_sense", {})
                    # Updating totals if live_market has fresher bid/ask data
                    mb = live_data.get("market_breadth", {})
                    if mb:
                        advances = mb.get("advances", advances)
                        declines = mb.get("declines", declines)
                        ad_ratio = mb.get("ratio", ad_ratio)
                        vwap_stretch = live_data.get("macro_vwap_stretch", vwap_stretch)
        except Exception: 
            pass

        ofi_ratio = round(total_bids / total_asks, 2) if total_asks > 0 else 1.0

        # Format Sector Sense string for the prompt
        sector_str = "No major sector anomalies."
        if sector_sense_data:
            anomalies = []
            for sec, details in sector_sense_data.items():
                z = details.get('z_score', 0)
                if z >= 1.5 or z <= -1.5:
                    anomalies.append(f"{sec}: {details.get('status')} (Z-Score: {z})")
            if anomalies:
                sector_str = " | ".join(anomalies)

        prompt = f"""
        Act as a Hedge Fund Chief Risk Officer & Derivatives Quant managing a Nifty-50 Scale-In Positional Fund.
        You deploy capital in 10% tranches based on absolute high-conviction signals.

        ### ⏰ CURRENT MARKET PHASE: {time_phase}
        ### 🎯 PHASE RULE: {focus_rule}

        ### 📥 INPUT DATA:
        - 🌐 GLOBAL MACRO (10 Pillars): {json.dumps(stats)}
        - 🧠 ML FORECAST (Mathematical Base): {global_data.get('ml_forecast', 0)}% (Predicted Nifty Move)
        - 📰 MACRO NEWS MOOD: {overall_news_mood}
        - 🌏 ASIAN MOMENTUM: {asian_sentiment} (Net: {net_asian_momentum}%)
        - 📊 NIFTY-50 BREADTH (A/D RATIO): {ad_ratio} (Advances: {advances}, Declines: {declines})
        - ⚖️ HEAVYWEIGHT ORDER FLOW IMBALANCE: {ofi_ratio} (Total Bids: {total_bids}, Total Asks: {total_asks})
        - 🌊 NIFTY VWAP STRETCH: {vwap_stretch}% (Positive = Overbought, Negative = Oversold)
        - 🧮 SMART MONEY & FEAR: INDIA VIX = {vix_india} | PUT-CALL RATIO (PCR) = {pcr_value} | MAX PAIN STRIKE = {max_pain}
        - 🎯 MACRO RISK: {macro_risk} | NIFTY ATR: {atr_value} 
        - 🔄 SECTOR-SENSE ROTATION: {sector_str}

        ### 🏗️ STRATEGY RULES (INSTITUTIONAL MODE):
        1. NO FORCED TRADES: You MUST evaluate if the current setup is worth deploying a 10% capital tranche. If signals are mixed, contradictory, or risk is too high (VIX spiking, Macro Risk High), you MUST output "WAIT".
        2. CONVICTION BUY: Output "BUY" only if ML Forecast is positive, Breadth > 1.2, Global Macros are supportive, and PCR indicates a solid base.
        3. CONVICTION SELL: Output "SELL" only if ML Forecast is negative, Breadth < 0.8, Global Macros are bleeding, and PCR shows heavy call writing.
        4. MAX PAIN GRAVITY: Pay close attention to the MAX PAIN STRIKE. Institutions write options to pin the market here. If Spot is stretched far from Max Pain, anticipate mean-reversion.
        5. SECTOR ARBITRAGE: If the "SECTOR-SENSE ROTATION" data shows an "ULTRA-HIGH ARB" anomaly (Z-Score > 1.5 or < -1.5), factor this into your logic. Over-extended sectors usually snap back.
        6. Focus strictly on the direction of the "NIFTY 50" Index.

        ### 📦 OUTPUT FORMAT (STRICT JSON ONLY):
        {{
            "action": "BUY", "SELL", or "WAIT",
            "market_regime": "1-2 word description (e.g., 'Risk-On', 'Panic Selling', 'Choppy')",
            "conviction_score": 0-100 (Int),
            "tranche_advice": "e.g., 'Deploy 10% Tranche', or 'Hold Capital'",
            "logic": "1-2 line crisp Hinglish explanation behind the decision.",
            "devils_advocate": "What is the biggest risk to this decision right now?"
        }}
        """

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt
            )
            verdict = json.loads(self.clean_json_response(response.text))
            
            if verdict.get("action") not in ["BUY", "SELL", "WAIT"]:
                verdict["action"] = "WAIT"
                verdict["logic"] = "System overridden to WAIT due to invalid AI response."

            return json.dumps(verdict)
            
        except Exception as e:
            return json.dumps({
                "action": "WAIT", 
                "market_regime": "Error State", 
                "logic": f"Fallback to WAIT due to Engine Error: {str(e)}", 
                "conviction_score": 0
            })