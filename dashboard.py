import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import yfinance as yf
from global_pulse import GlobalPulse
from model_predictor import ModelPredictor
from streamlit_autorefresh import st_autorefresh
from datetime import datetime, time
import pytz
import json
import os
import re

# --- PAGE CONFIG ---
st.set_page_config(page_title="Alpha-Terminal | Nifty Positional Fund", layout="wide", initial_sidebar_state="expanded")

IST = pytz.timezone('Asia/Kolkata')
now_ist = datetime.now(IST)

# 🚀 CHART PERSISTENCE
if 'last_valid_chart' not in st.session_state:
    st.session_state.last_valid_chart = None

# 🚀 DYNAMIC REFRESH ENGINE (Saves CPU & RAM)
is_weekday_today = now_ist.weekday() < 5
curr_time = now_ist.time()
if is_weekday_today and time(9, 0) <= curr_time <= time(15, 30):
    st_autorefresh(interval=5000, key="live_refresh")  # Fast refresh during market
else:
    st_autorefresh(interval=60000, key="sleep_refresh") # Slow refresh off-market

def load_json(filename):
    if os.path.exists(filename):
        try:
            with open(filename, "r") as f: return json.load(f)
        except: return {}
    return {}

@st.cache_data(ttl=300) 
def fetch_global_intelligence():
    try:
        pulse = GlobalPulse()
        predictor = ModelPredictor()
        data = pulse.get_global_context()
        forecast = predictor.predict_today_move(data['stats'])
        
        # 🐛 THE FIX: Robust yfinance download for multiple UI tickers
        try:
            hist = yf.download(["GC=F", "INR=X"], period="5d", progress=False)['Close'].ffill()
            if len(hist) >= 2:
                data['stats']['Gold'] = round(((hist['GC=F'].iloc[-1] - hist['GC=F'].iloc[-2]) / hist['GC=F'].iloc[-2]) * 100, 2)
                data['stats']['USD_INR'] = round(((hist['INR=X'].iloc[-1] - hist['INR=X'].iloc[-2]) / hist['INR=X'].iloc[-2]) * 100, 2)
        except: pass
            
        return data, forecast
    except:
        return {"stats": {}, "news_sentiment": {"overall_mood": "Error"}}, 0.0

# --- DATA FETCHING FOR SIDEBAR SYNC ---
live_payload = load_json("live_market.json")
# Extract timestamp from backend payload
fetch_time = live_payload.get("timestamp", "Awaiting Data...")

# --- SIDEBAR ---
st.sidebar.title("🛡️ AI Quant Health")
st.sidebar.markdown(f"**🕒 UI Time:** `{now_ist.strftime('%H:%M:%S')}`")
st.sidebar.markdown(f"**📡 Backend Data Fetched At:** `{fetch_time}`") # NEW: Timestamp indicator

current_hour = now_ist.hour
current_minute = now_ist.minute
if (current_hour == 9 and current_minute >= 10) or (current_hour == 10 and current_minute == 0):
    current_phase = "🌅 Morning Global Phase"
elif (current_hour == 10 and current_minute > 0) or (current_hour == 11) or (current_hour == 12 and current_minute <= 30):
    current_phase = "🇮🇳 Midday Local Phase"
elif (current_hour == 12 and current_minute > 30) or (13 <= current_hour <= 15):
    current_phase = "🌍 Euro/US Shift Phase"
else:
    current_phase = "🌙 Off-Market / Pre-Open"

st.sidebar.info(f"**⏱️ Active Cycle:**\n{current_phase}")

st.sidebar.divider()
force_market_open = st.sidebar.checkbox("🛠️ Force Live UI (Weekend Mode)", value=False, help="Enable to view UI outside market hours.")

bt_report = load_json("backtest_report.json")
st.sidebar.divider()
st.sidebar.subheader("🧠 10-Pillar ML Report")
st.sidebar.metric("Backtest Accuracy", bt_report.get('accuracy', 'N/A'))
st.sidebar.write(f"System Confidence: **{bt_report.get('status', 'Scanning')}**")
st.sidebar.caption(f"Last Trained: {bt_report.get('last_run', 'N/A')}")

verdict = load_json("latest_verdict.json")
st.sidebar.divider()
st.sidebar.subheader("📈 Market Regime")
regime = verdict.get('market_regime', 'Scanning...')
regime_color = "🟢" if "Bull" in regime or "Risk-On" in regime else "🔴" if "Bear" in regime or "Panic" in regime else "🟡"
st.sidebar.write(f"{regime_color} {regime}")

# --- MAIN UI ---
data, forecast = fetch_global_intelligence()
stats = data.get('stats', {})
news = data.get('news_sentiment', {})

pcr = data.get('pcr', 'UNKNOWN')
max_pain = data.get('max_pain', 'UNKNOWN')

is_market_open = (is_weekday_today and (time(9, 0) <= curr_time <= time(16, 0))) or force_market_open

if is_market_open:
    live_ticks = live_payload.get("ltp_data", live_payload) if isinstance(live_payload, dict) else {}
    market_breadth = live_payload.get("market_breadth", {"advances": 0, "declines": 0, "ratio": 1.0})
    advanced_metrics = live_payload.get("advanced_metrics", {})
    # 🚀 Extracting Sector Sense Data
    sector_sense = live_payload.get("sector_sense", {})
    
    col_ticks, col_ai = st.columns([1.2, 1])
    
    with col_ticks:
        st.subheader("🇮🇳 Nifty-50 Live Breadth & Flow")
        
        adv = market_breadth.get("advances", 0)
        dec = market_breadth.get("declines", 0)
        ad_ratio = market_breadth.get("ratio", 1.0)
        
        bids = sum(d.get("total_buy_qty", 0) for d in advanced_metrics.values())
        asks = sum(d.get("total_sell_qty", 0) for d in advanced_metrics.values())
        ofi_ratio = round(bids / asks, 2) if asks > 0 else 1.0
        
        total_orders = bids + asks
        buy_pressure = int((bids / total_orders) * 100) if total_orders > 0 else 50
        
        human_text = f"Bhai, abhi hum **{current_phase}** mein hain. "
        if ofi_ratio > 1.2: human_text += "Order book mein **Buyers haavi hain**. "
        elif ofi_ratio < 0.8: human_text += "Order book mein **Sellers dabba rahe hain**. "
        else: human_text += "Order book mein **Katte ki takkar** chal rahi hai. "
        
        if ad_ratio > 1.2: human_text += "Breadth solid hai (Hare Nishan). "
        elif ad_ratio < 0.8: human_text += "Breadth weak hai (Bikwali). "
        
        if pcr != 'UNKNOWN' and isinstance(pcr, (int, float)):
            if pcr > 1.2: human_text += f"**PCR {pcr}** hai, Put writers support bana rahe hain. "
            elif pcr < 0.8: human_text += f"**PCR {pcr}** hai, Call writers upar se daba rahe hain. "
        if max_pain != 'UNKNOWN':
            human_text += f"Institutions ka **Max Pain ₹{max_pain}** pe hai. "

        mood = news.get("overall_mood", "Mixed/Neutral")
        human_text += f"Global Macro Mood abhi **{mood}** lag raha hai."

        st.markdown(f"""
        <div style="background-color: #f1f8e9; padding: 12px; border-radius: 8px; border-left: 5px solid #8bc34a; margin-bottom: 15px;">
            <span style="font-size: 16px; color: #2e7d32;">🗣️ <b>Trader's Whisper:</b> {human_text}</span>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown(f"**Heavyweights Order Book:** 🟢 {bids} Bids vs 🔴 {asks} Asks (Imbalance: {ofi_ratio})")
        st.progress(buy_pressure / 100, text=f"Buying Pressure: {buy_pressure}%")
        st.write("")
        st.markdown(f"**Nifty 50 Market Breadth:** 🟢 {adv} Advances | 🔴 {dec} Declines (A/D Ratio: {ad_ratio})")
        st.write("")
        
        c1, c2, c3, c4 = st.columns(4)
        nifty = live_ticks.get("99926000", 0.0)
        banknifty = live_ticks.get("99926009", 0.0)
        
        c1.metric("NIFTY 50", f"₹{nifty}")
        c2.metric("BANK NIFTY", f"₹{banknifty}")
        c3.metric("MAX PAIN", f"₹{max_pain}" if max_pain != "UNKNOWN" else "N/A", delta="Option Pinning", delta_color="off")
        
        pcr_delta_color = "normal" if isinstance(pcr, (int, float)) and pcr >= 1 else "inverse"
        c4.metric("PCR", f"{pcr}" if pcr != "UNKNOWN" else "N/A", delta="Put/Call", delta_color=pcr_delta_color)

    with col_ai:
        st.subheader("🔮 Dynamic AI Trajectory")
        action = verdict.get("action", "WAIT")
        
        ml_pct = float(forecast) if forecast else 0.0
        adjusted_pct = ml_pct
        
        if mood == "Bullish": adjusted_pct += 0.30
        elif mood == "Bearish": adjusted_pct -= 0.30
        
        nasdaq = stats.get("Nasdaq_Cash", 0.0)
        gift = stats.get("GIFT_Nifty", 0.0)
        macro_factor = (nasdaq * 0.15) + (gift * 0.15) 
        adjusted_pct += macro_factor
        
        dxy = stats.get("Dollar_Index", 0.0)
        if dxy > 0.3: adjusted_pct -= 0.15
        elif dxy < -0.3: adjusted_pct += 0.15
        
        adjusted_pct = round(adjusted_pct, 2)
        
        if nifty > 0:
            assumed_close = nifty * (1 + (adjusted_pct / 100))
            delta_color = "normal" if adjusted_pct >= 0 else "inverse"
            st.metric(label="🎯 Expected Closing (Macro Adjusted)", value=f"₹{round(assumed_close, 2)}", delta=f"Net Move: {adjusted_pct}% (Base ML: {round(ml_pct, 2)}%)", delta_color=delta_color)
        else:
            st.info("Waiting for live Nifty price to calculate expected closing...")
            
        st.markdown(f"**🔥 Current Fund Action:** `{action}`")
        st.caption(f"**Logic Insight:** {verdict.get('logic', '')}") 

    # ==========================================
    # 🔄 1.5 LIVE SECTOR-SENSE UI (GRAPH + TABLE)
    # ==========================================
    if sector_sense:
        st.markdown("---")
        st.subheader("🔄 Live Sector-Sense Rotation (Z-Score Arbitrage)")
        st.caption("Tracking Mean-Reversion opportunities. A Z-Score > +1.5 or < -1.5 suggests an extreme stretch against Nifty 50.")
        
        s_col1, s_col2 = st.columns([1.5, 1])
        
        # BAR CHART
        with s_col1:
            names = list(sector_sense.keys())
            z_vals = [d['z_score'] for d in sector_sense.values()]
            colors = ['#ef5350' if z < -1.5 else '#26a69a' if z > 1.5 else '#78909c' for z in z_vals]
            
            fig_sec = go.Figure(go.Bar(x=names, y=z_vals, marker_color=colors, text=z_vals, textposition='outside'))
            fig_sec.add_hline(y=1.5, line_dash="dash", line_color="#ff9800", annotation_text="Overbought")
            fig_sec.add_hline(y=-1.5, line_dash="dash", line_color="#ff9800", annotation_text="Oversold")
            fig_sec.update_layout(height=300, template="plotly_dark", margin=dict(l=10, r=10, t=30, b=10), yaxis_title="Z-Score Deviation")
            st.plotly_chart(fig_sec, use_container_width=True)

        # TABLE
        with s_col2:
            sec_df = pd.DataFrame.from_dict(sector_sense, orient='index').reset_index()
            sec_df.rename(columns={'index': 'Sector', 'change_pct': 'Avg Change %', 'divergence': 'Divergence vs Nifty', 'z_score': 'Z-Score', 'status': 'Status'}, inplace=True)
            
            def highlight_arb(val):
                color = ''
                if "Buy Setup" in str(val): color = 'background-color: rgba(220, 53, 69, 0.2); color: #ff6b6b; font-weight: bold;'
                elif "Sell Setup" in str(val): color = 'background-color: rgba(40, 167, 69, 0.2); color: #69b3a2; font-weight: bold;'
                return color

            st.dataframe(sec_df[['Sector', 'Z-Score', 'Status']].style.map(highlight_arb, subset=['Status']), use_container_width=True, hide_index=True)
    else:
        st.info("⌛ Waiting for Sector-Sense calculations to stream from backend...")

    # ==========================================
    # 2. 📈 LIVE CHART (PERSISTENT LOGIC)
    # ==========================================
    st.markdown("---")
    st.subheader("📈 Live Nifty 50 Chart")
    
    try:
        chart_payload = load_json("nifty_chart.json")
        raw_data = chart_payload.get("data", chart_payload) if isinstance(chart_payload, dict) else chart_payload
        
        # Memory Lock: Sirf tabhi update karo jab asli data aaye
        if raw_data and isinstance(raw_data, list) and len(raw_data) > 0:
            st.session_state.last_valid_chart = raw_data

        if st.session_state.last_valid_chart:
            nifty_df = pd.DataFrame(st.session_state.last_valid_chart, columns=['Datetime', 'Open', 'High', 'Low', 'Close', 'Volume']) if isinstance(st.session_state.last_valid_chart[0], list) else pd.DataFrame(st.session_state.last_valid_chart)
            date_col = 'Datetime' if 'Datetime' in nifty_df.columns else 'time' if 'time' in nifty_df.columns else nifty_df.columns[0]
            nifty_df[date_col] = pd.to_datetime(nifty_df[date_col])
            nifty_df.set_index(date_col, inplace=True)

            fig = go.Figure(data=[go.Candlestick(x=nifty_df.index, open=nifty_df.iloc[:, 0], high=nifty_df.iloc[:, 1], low=nifty_df.iloc[:, 2], close=nifty_df.iloc[:, 3], name="Nifty 50", increasing_line_color='#26a69a', decreasing_line_color='#ef5350')])
            if nifty > 0: fig.add_hline(y=nifty, line_color="#1E88E5", line_width=1, annotation_text=f"🔵 Live: {nifty}", annotation_position="left")
            
            if max_pain != 'UNKNOWN' and isinstance(max_pain, (int, float)):
                fig.add_hline(y=max_pain, line_color="#ff9800", line_width=1, line_dash="dash", annotation_text=f"🟠 Max Pain: {max_pain}", annotation_position="right")

            fig.update_layout(height=400, margin=dict(l=10, r=40, t=20, b=10), xaxis_rangeslider_visible=False, template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("⌛ Live chart waiting for Angel One backend feed (Start `main.py`).")
    except Exception as e:
        st.warning(f"Live chart syncing... (Error: {e})")
# ==========================================
    # 🕒 3. PREDICTIVE TIME-PHASED SCENARIOS
    # ==========================================
    st.markdown("---")
    st.subheader("🔮 Predictive Scenarios (15-Min Intervals)")
    st.caption("Dynamic projection based on live Global Macros, GIFT Nifty, and Options Data.")

    # Fetching live variables for math
    nifty = live_ticks.get("99926000", 0.0)
    gift = stats.get("GIFT_Nifty", 0.0)
    us_fut = stats.get("US_Fut_SP500", 0.0)
    nikkei = stats.get("Nikkei_Japan", 0.0)

# ---------------------------------------------------------
    # 🌅 DROPDOWN 1: MORNING (Dynamic Step-by-Step Trajectory)
    # ---------------------------------------------------------
    with st.expander("🌅 Morning Flow (09:15 - 10:30) | Live Dynamic Predictions", expanded=True):
        if nifty > 0:
            # 🧮 1. MACRO ALGORITHM (Base Market Flow)
            macro_drift = (gift * 0.5) + (us_fut * 0.3) + (nikkei * 0.2)
            
            # 📰 2. NEWS SENTIMENT OVERLAY (The Alpha Factor)
            news_impact = 0.0
            if mood == "Bullish":
                news_impact = 0.20  # +0.20% extra boost for positive global sentiment
            elif mood == "Bearish":
                news_impact = -0.20 # -0.20% drag for negative global sentiment
                
            # 🎯 Final Calculated Morning Drift
            expected_drift_pct = macro_drift + news_impact
            
            # Define Exact Time Frames
            frames = [
                ("09:15", "09:30", "Initial Volatility"),
                ("09:31", "09:45", "Trend Establishing"),
                ("09:46", "10:00", "Morning Peak/Trough"),
                ("10:01", "10:15", "Flow Alignment"),
                ("10:16", "10:30", "Transition to Midday")
            ]
            
            current_hm = now_ist.strftime("%H:%M")
            table_data = []
            
            # Distribute the total expected drift incrementally across the 5 candles
            step_drift = expected_drift_pct / 5 
            volatility_buffer = 0.15 # Approx 15-20 points buffer for Worst/Best case per candle
            
            # The "Rolling Base" starts with Live Nifty
            proj_base = nifty 
            
            for start_t, end_t, label in frames:
                row = {"Time Frame": f"{start_t} to {end_t} ({label})"}
                
                if current_hm > end_t:
                    # 🕒 PHASE ELAPSED
                    row["🔴 Worst Case"] = "✅ Elapsed"
                    row["🟡 Average Case"] = "✅ Elapsed"
                    row["🟢 Best Case"] = "✅ Elapsed"
                    row["Status"] = "Completed"
                    
                elif start_t <= current_hm <= end_t:
                    # 🔵 CURRENT LIVE PHASE: Lock the REAL Nifty price as the new base!
                    proj_base = nifty 
                    
                    avg_c = proj_base * (1 + (step_drift / 100))
                    best_c = proj_base * (1 + ((step_drift + volatility_buffer) / 100))
                    worst_c = proj_base * (1 + ((step_drift - volatility_buffer) / 100))
                    
                    row["🔴 Worst Case"] = f"₹{round(worst_c, 2)}"
                    row["🟡 Average Case"] = f"₹{round(avg_c, 2)} (LIVE BASE)"
                    row["🟢 Best Case"] = f"₹{round(best_c, 2)}"
                    row["Status"] = "🔵 ACTIVE"
                    
                    proj_base = avg_c 
                    
                else:
                    # 🔮 FUTURE PHASES
                    avg_c = proj_base * (1 + (step_drift / 100))
                    best_c = proj_base * (1 + ((step_drift + volatility_buffer) / 100))
                    worst_c = proj_base * (1 + ((step_drift - volatility_buffer) / 100))
                    
                    row["🔴 Worst Case"] = f"₹{round(worst_c, 2)}"
                    row["🟡 Average Case"] = f"₹{round(avg_c, 2)}"
                    row["🟢 Best Case"] = f"₹{round(best_c, 2)}"
                    row["Status"] = "⏳ Pending"
                    
                    proj_base = avg_c 
                    
                table_data.append(row)
                
            # Dynamic UI Display for the formula
            st.markdown(f"**Macro Bias:** GIFT (`{gift}%`) + US Fut (`{us_fut}%`) + Nikkei (`{nikkei}%`) = `{round(macro_drift, 2)}%`")
            
            # Highlighting the News impact in the UI
            mood_color = "green" if mood == "Bullish" else "red" if mood == "Bearish" else "gray"
            st.markdown(f"**News Overlay:** :{mood_color}[{mood}] (Impact: `{news_impact}%`) ➡️ **Net Morning Drift Target:** **`{round(expected_drift_pct, 2)}%`**")
            
            st.caption("⚙️ *Engine Logic: Every 15 minutes, the system captures the actual LIVE Nifty value, applies Macro + News sentiment, and dynamically re-calculates future intervals.*")
            
            df_morn = pd.DataFrame(table_data)
            st.dataframe(df_morn, use_container_width=True, hide_index=True)
            
        else:
            st.info("⌛ Waiting for Live Nifty price to calculate Morning projections...")
    # ---------------------------------------------------------
    # 🌍 DROPDOWN 2: AFTERNOON (Midday & European Open)
    # ---------------------------------------------------------
    with st.expander("🌍 Afternoon Flow (10:30 - 13:30) | Option Decay & European Open"):
        st.write("*(Logic pending)*")

    # ---------------------------------------------------------
    # 🔥 DROPDOWN 3: END GAME (Final Trend & US Pre-Market)
    # ---------------------------------------------------------
    with st.expander("🔥 End Game (13:30 - 15:30) | Short Covering & US Cash Open Prep"):
        st.write("*(Logic pending)*")
        
# ==========================================
# 4. 🧠 THE FINAL AI VERDICT 
# ==========================================
st.divider()
st.subheader("🧠 The Final Institutional Verdict")

action = verdict.get('action', 'WAIT')
action_color = "green" if "BUY" in action else "red" if "SELL" in action else "orange"

with st.container(border=True):
    head_col1, head_col2 = st.columns([3, 1])
    with head_col1: st.markdown(f"### 🔥 FUND ACTION: :{action_color}[{action}]")
    with head_col2: st.markdown(f"**🎯 Tranche Advice:** `{verdict.get('tranche_advice', 'Hold')}`")
        
    st.markdown(f"**🧠 CRO Logic:** {verdict.get('logic', 'Analyzing live data flows...')}")
    st.divider()
    
    met_col1, met_col2 = st.columns(2)
    met_col1.metric("⚡ Conviction Score", f"{verdict.get('conviction_score', 0)}/100")
    met_col2.metric("🎯 Focus", "NIFTY-50 POSITIONAL SCALE-IN")
    
    risk = verdict.get('devils_advocate', '')
    if risk: st.warning(f"**🚫 Risk Check (Devil's Advocate):** {risk}")

# ==========================================
# 🌍 5. 10-PILLAR GLOBAL IMPACT 
# ==========================================
st.divider()
st.subheader("🌍 The 10-Pillar Global Macro Matrix")

cor_cols = st.columns(5)
nasdaq = stats.get("Nasdaq_Cash", 0.0)
cor_cols[0].metric("🇺🇸 Nasdaq (Cash)", f"{nasdaq}%", delta="Tech Sentiment", delta_color="normal" if nasdaq>0 else "inverse")

sp500 = stats.get("US_Fut_SP500", 0.0)
cor_cols[1].metric("🇺🇸 S&P 500 Fut", f"{sp500}%", delta="US Broad Mkt", delta_color="normal" if sp500>0 else "inverse")

nikkei = stats.get("Nikkei_Japan", 0.0)
cor_cols[2].metric("🇯🇵 Nikkei", f"{nikkei}%", delta="Asia Leader", delta_color="normal" if nikkei>0 else "inverse")

dax = stats.get("DAX_Cash", stats.get("EU_Fut_DAX", 0.0))
cor_cols[3].metric("🇪🇺 DAX", f"{dax}%", delta="Euro Leader", delta_color="normal" if dax>0 else "inverse")

gift = stats.get("GIFT_Nifty", 0.0)
cor_cols[4].metric("🇮🇳 GIFT Nifty", f"{gift}%", delta="Indian Proxy", delta_color="normal" if gift>0 else "inverse")

st.write("") 
cor_cols_2 = st.columns(5)

dxy = stats.get("Dollar_Index", 0.0)
cor_cols_2[0].metric("💵 Dollar (DXY)", f"{dxy}%", delta="Global Liquidity", delta_color="inverse" if dxy>0 else "normal")

yields = stats.get("US_10Y_Yield", 0.0)
cor_cols_2[1].metric("📜 10Y Yield", f"{yields}%", delta="Debt Market", delta_color="inverse" if yields>0 else "normal")

crude = stats.get("Crude_Oil", 0.0)
cor_cols_2[2].metric("🛢️ Crude Oil", f"{crude}%", delta="Inflation", delta_color="inverse" if crude>0 else "normal")

gold = stats.get("Gold", 0.0)
cor_cols_2[3].metric("🥇 Gold", f"{gold}%", delta="Safe Haven", delta_color="normal" if gold>0 else "inverse")

inr = stats.get("USD_INR", 0.0)
cor_cols_2[4].metric("₹ USD/INR", f"{inr}%", delta="Rupee Weakness", delta_color="inverse" if inr>0 else "normal")

# ==========================================
# 🔮 6. AI PREDICTION & FINBERT NEWS
# ==========================================
st.divider()
col_gauge, col_macro = st.columns([1, 1])

with col_gauge:
    st.subheader("🔮 Base ML Daily Forecast")
    safe_forecast = forecast if forecast != 0.0 else 0.01 
    fig = go.Figure(go.Indicator(
        mode = "gauge+number", value = safe_forecast, number = {'suffix': "%"},
        title = {'text': "AI Mathematical Base (Nifty 50)", 'font': {'size': 18}},
        gauge = {'axis': {'range': [-2, -0.5]}, 'bar': {'color': "#1E88E5"}, 'steps': [{'range': [-2, -0.5], 'color': "#ffebee"}, {'range': [-0.5, 0.5], 'color': "#f5f5f5"}, {'range': [0.5, 2], 'color': "#e8f5e9"}], 'threshold': {'line': {'color': "red", 'width': 4}, 'thickness': 0.75, 'value': safe_forecast}}
    ))
    fig.update_layout(height=250, margin=dict(l=20, r=20, t=40, b=20))
    st.plotly_chart(fig)

with col_macro:
    st.subheader("📰 Live FinBERT News Sentiment")
    mood = news.get("overall_mood", "Scanning...")
    mood_color = "#1E88E5"
    if mood == "Bullish": mood_color = "#28a745"
    elif mood == "Bearish": mood_color = "#dc3545"
    elif mood == "Mixed/Neutral": mood_color = "#ffc107"
    st.markdown(f"""<div style="background-color: {mood_color}20; padding: 15px; border-radius: 8px; border-left: 5px solid {mood_color}; margin-bottom: 15px;"><h3 style="margin: 0; color: {mood_color};">Macro Mood: {mood}</h3></div>""", unsafe_allow_html=True)
    headlines = news.get("top_headlines", ["Fetching from News Engine..."])
    for h in headlines[:3]: st.caption(f"{'🟢' if 'BULLISH' in h.upper() else '🔴' if 'BEARISH' in h.upper() else '⚪'} {h}")

# ==========================================
# 📡 7. ACTIVE TRANCHES & TRADE LOGS
# ==========================================
st.divider()
st.subheader("💼 Fund Portfolio: Open Tranches & Executed Trades")

col_config_dict = {
    "Entry": st.column_config.NumberColumn("Entry (₹)", format="₹%.2f"),
    "Target": st.column_config.NumberColumn("Target (₹)", format="₹%.2f"),
    "SL": st.column_config.NumberColumn("SL (₹)", format="₹%.2f"),
    "Profit": st.column_config.NumberColumn("Profit (₹)", format="₹%.2f"),
    "Loss": st.column_config.NumberColumn("Loss (₹)", format="₹%.2f"),
}

open_trades = load_json("open_trades.json")
if open_trades:
    st.markdown("### 🟢 Active Open Positions (Scale-In Tranches)")
    open_df = pd.DataFrame.from_dict(open_trades, orient='index')
    display_cols = ['Entry_Time', 'Symbol', 'Action', 'Lots', 'Entry', 'Target', 'SL', 'Delta']
    existing_cols = [c for c in display_cols if c in open_df.columns]
    
    if existing_cols: 
        st.dataframe(open_df[existing_cols], hide_index=True, use_container_width=True, column_config=col_config_dict)
else:
    st.info("⚪ No open positions currently running. Waiting for AI signal.")

st.markdown("<br>", unsafe_allow_html=True)
st.markdown("### 📜 Executed Options Trades History")
csv_file = "dummy_trades.csv"
if os.path.exists(csv_file):
    try:
        trade_df = pd.read_csv(csv_file)
        mgr_col1, mgr_col2 = st.columns([3, 1])
        mgr_col1.write("Live track record of AI-managed Options execution with Black-Scholes Delta PnL.")
        csv_data = trade_df.to_csv(index=False).encode('utf-8')
        mgr_col2.download_button("📥 Download Trade Log", data=csv_data, file_name=f"Trade_Log_{datetime.now().strftime('%Y%m%d')}.csv", mime="text/csv", use_container_width=True)
        
        st.dataframe(trade_df.tail(10).iloc[::-1], hide_index=True, use_container_width=True, column_config=col_config_dict)
    except Exception as e:
        st.error(f"Error loading trade manager data: {e}")
else:
    st.info("⌛ No closed trades yet. The Excel log will appear here once the first trade is completed.")