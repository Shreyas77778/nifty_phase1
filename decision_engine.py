import json
import re
import pytz
import os
from datetime import datetime

class DecisionEngine:
    def __init__(self, ai_client):
        self.client = ai_client
        # 🚀 Upgraded to DeepSeek-R1 for Chain-of-Thought reasoning
        self.model_name = "deepseek-reasoner" 
        self.ist = pytz.timezone('Asia/Kolkata')
        print(f"🧠 Decision Engine: DeepSeek-R1 Active")

    def clean_json_response(self, raw_text):
        """ DeepSeek R1 often wraps JSON in backticks, this extracts it cleanly. """
        try:
            raw_text = raw_text.strip()
            # Remove Markdown code blocks
            if "```json" in raw_text:
                raw_text = raw_text.split("```json")[1].split("```")[0].strip()
            elif "```" in raw_text:
                raw_text = raw_text.split("```")[1].split("```")[0].strip()
                
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
        elif (current_hour == 12 and current_minute > 30) or (current_hour == 13 and current_minute <= 30):
            time_phase = "AFTERNOON_EURO_PHASE (12:30 PM - 1:30 PM)"
            focus_rule = "Give 80% weight to European Open (DAX/FTSE) and US Futures. Anticipate strong FII afternoon flows."
        elif (current_hour == 13 and current_minute > 30) or (current_hour >= 14 and current_hour < 16):
            time_phase = "END_GAME_PHASE (1:30 PM - 3:30 PM)"
            focus_rule = "Weightage: 40% US Pre-Market, 40% Short Covering/Long Unwinding (OI based), 20% Euro Trend. Watch out for 2:30 PM reversal spikes."
        else:
            time_phase = "OFF_MARKET_PHASE"
            focus_rule = "Market closed. Evaluate pure global macro for positional overnight carrying."

        # --- 📊 DATA EXTRACTION ---
        stats = global_data.get('stats', {})
        macro_risk = "HIGH" if stats.get('Dollar_Index', 0) > 0.4 or stats.get('US_10Y_Yield', 0) > 0.4 else "STABLE"
        news_data = global_data.get('news_sentiment', {})
        overall_news_mood = news_data.get('overall_mood', 'Neutral')
        
        market_breadth = global_data.get('market_breadth', {})
        advances = market_breadth.get('advances', 0)
        declines = market_breadth.get('declines', 0)
        ad_ratio = float(market_breadth.get('ratio', 1.0))
        
        vwap_stretch = float(global_data.get('macro_vwap_stretch', 0.0))
        
        # OFI Calculation
        total_bids, total_asks = 0, 0
        advanced_metrics = global_data.get('advanced_metrics', {})
        for token, d in advanced_metrics.items():
            total_bids += d.get("total_buy_qty", 0)
            total_asks += d.get("total_sell_qty", 0)
        ofi_ratio = round(total_bids / total_asks, 2) if total_asks > 0 else 1.0

        # Sector Sense Integration
        sector_str = "No major sector anomalies."
        try:
            if os.path.exists("live_market.json"):
                with open("live_market.json", "r") as f:
                    live_data = json.load(f)
                    sector_sense_data = live_data.get("sector_sense", {})
                    if sector_sense_data:
                        anomalies = []
                        for sec, details in sector_sense_data.items():
                            z = details.get('z_score', 0)
                            if z >= 1.5 or z <= -1.5:
                                anomalies.append(f"{sec}: {details.get('status')} (Z-Score: {z})")
                        if anomalies: sector_str = " | ".join(anomalies)
        except: pass

        # --- 🧠 DEEPSEEK-R1 PROMPT ---
        prompt = f"""
        Act as a Hedge Fund Chief Risk Officer (CRO). You manage a Nifty-50 Scale-In Positional Fund.
        Task: Analyze current flow and decide if we deploy a 10% capital tranche.

        ### ⏰ PHASE: {time_phase} | RULE: {focus_rule}
        
        ### 📥 MARKET CONTEXT:
        - GLOBAL STATS: {json.dumps(stats)}
        - ML BASE FORECAST: {global_data.get('ml_forecast', 0)}%
        - NEWS SENTIMENT: {overall_news_mood}
        - BREADTH (A/D): {ad_ratio} (Adv: {advances}, Dec: {declines})
        - ORDER FLOW (OFI): {ofi_ratio}
        - VWAP STRETCH: {vwap_stretch}%
        - FEAR & SMART MONEY: INDIA VIX: {vix_india} | PCR: {global_data.get('pcr', 'N/A')} | MAX PAIN: {global_data.get('max_pain', 'N/A')}
        - ATR: {atr_value} | MACRO RISK: {macro_risk}
        - SECTOR ANOMALIES: {sector_str}

        ### 🏗️ STRATEGY:
        1. Identify institutional traps (Liquidity sweeps vs Trend).
        2. Evaluate move sustainability. 
        3. Strict Directional Bias: Only BUY if macros+ML+Breadth align. 
        4. If Spot is far from MAX PAIN, anticipate mean-reversion.

        ### 📦 OUTPUT FORMAT (STRICT JSON ONLY):
        {{
            "action": "BUY/SELL/WAIT",
            "market_regime": "Description",
            "conviction_score": 0-100,
            "tranche_advice": "Advice",
            "logic": "Hinglish explanation",
            "devils_advocate": "What could fail?"
        }}
        """

        try:
            # 🧠 DeepSeek-R1 (OpenAI Standard Call)
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}]
            )
            
            raw_res = response.choices[0].message.content
            verdict_text = self.clean_json_response(raw_res)
            verdict = json.loads(verdict_text)
            
            # Validation
            if verdict.get("action") not in ["BUY", "SELL", "WAIT"]:
                verdict["action"] = "WAIT"

            return json.dumps(verdict)
            
        except Exception as e:
            print(f"❌ DeepSeek-R1 Logic Error: {e}")
            return json.dumps({
                "action": "WAIT", 
                "market_regime": "Error State", 
                "logic": f"Fallback to WAIT due to Engine Error: {str(e)}", 
                "conviction_score": 0
            })