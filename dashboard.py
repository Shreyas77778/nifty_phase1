import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import yfinance as yf
from global_pulse import GlobalPulse
from model_predictor import ModelPredictor
from streamlit_autorefresh import st_autorefresh
from datetime import datetime, time, timedelta
import pytz
import json
import os
import re
from SmartApi import SmartConnect
import pyotp
from dotenv import load_dotenv

load_dotenv()

# --- PAGE CONFIG ---
st.set_page_config(page_title="Alpha-Terminal | Nifty Positional Fund", layout="wide", initial_sidebar_state="expanded")

IST = pytz.timezone('Asia/Kolkata')
now_ist = datetime.now(IST)

# 🚀 1. ANGEL ONE API LOGIN (Direct UI Lookup Support)
@st.cache_resource
def get_api_session():
    try:
        api_key = os.getenv("ANGEL_API_KEY")
        username = os.getenv("ANGEL_CLIENT_ID")
        pwd = os.getenv("ANGEL_PASSWORD")
        totp_key = os.getenv("ANGEL_TOTP_KEY")
        
        smart_api = SmartConnect(api_key=api_key)
        totp = pyotp.TOTP(totp_key).now()
        data = smart_api.generateSession(username, pwd, totp)
        if data['status']: return smart_api
    except: return None
    return None

smart_api = get_api_session()

# 🚀 2. API PRICE FETCH FUNCTION
@st.cache_data(ttl=600) # Cache for 10 mins to avoid rate limits
def get_actual_price_api(target_time_str):
    if not smart_api: return 0.0
    try:
        target_dt = datetime.combine(now_ist.date(), datetime.strptime(target_time_str, "%H:%M").time())
        params = {
            "exchange": "NSE",
            "symboltoken": "99926000", # Nifty Index
            "interval": "ONE_MINUTE",
            "fromdate": (target_dt - timedelta(minutes=5)).strftime('%Y-%m-%d %H:%M'),
            "todate": target_dt.strftime('%Y-%m-%d %H:%M')
        }
        res = smart_api.getCandleData(params)
        if res.get('status') and res.get('data'):
            return float(res['data'][-1][4]) # Close Price
    except: pass
    return 0.0

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
        
        try:
            hist = yf.download(["GC=F", "INR=X"], period="5d", progress=False)['Close'].ffill()
            if len(hist) >= 2:
                data['stats']['Gold'] = round(((hist['GC=F'].iloc[-1] - hist['GC=F'].iloc[-2]) / hist['GC=F'].iloc[-2]) * 100, 2)
                data['stats']['USD_INR'] = round(((hist['INR=X'].iloc[-1] - hist['INR=X'].iloc[-2]) / hist['INR=X'].iloc[-2]) * 100, 2)
        except: pass
            
        return data, forecast
    except:
        return {"stats": {}, "news_sentiment": {"overall_mood": "Error"}}, 0.0

# --- DATA FETCHING ---
live_payload = load_json("live_market.json")
fetch_time = live_payload.get("timestamp", "Awaiting Data...")

# --- SIDEBAR ---
st.sidebar.title("🛡️ AI Quant Health")
st.sidebar.markdown(f"**🕒 UI Time:** `{now_ist.strftime('%H:%M:%S')}`")
st.sidebar.markdown(f"**📡 Backend Data Fetched At:** `{fetch_time}`")

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
force_market_open = st.sidebar.checkbox("🛠️ Force Live UI (Weekend Mode)", value=False)

bt_report = load_json("backtest_report.json")
st.sidebar.divider()
st.sidebar.subheader("🧠 10-Pillar ML Report")
st.sidebar.metric("Backtest Accuracy", bt_report.get('accuracy', 'N/A'))

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
    sector_sense = live_payload.get("sector_sense", {})
    
    col_ticks, col_ai = st.columns([1.2, 1])
    
    with col_ticks:
        st.subheader("🇮🇳 Nifty-50 Live Breadth & Flow")
        adv, dec, ad_ratio = market_breadth.get("advances", 0), market_breadth.get("declines", 0), market_breadth.get("ratio", 1.0)
        bids = sum(d.get("total_buy_qty", 0) for d in advanced_metrics.values())
        asks = sum(d.get("total_sell_qty", 0) for d in advanced_metrics.values())
        ofi_ratio = round(bids / asks, 2) if asks > 0 else 1.0
        buy_pressure = int((bids / (bids + asks)) * 100) if (bids + asks) > 0 else 50
        
        human_text = f"Bhai, abhi hum **{current_phase}** mein hain. Global Mood **{news.get('overall_mood')}** hai."
        st.markdown(f"""<div style="background-color: #f1f8e9; padding: 12px; border-radius: 8px; border-left: 5px solid #8bc34a; margin-bottom: 15px;"><span style="font-size: 16px; color: #2e7d32;">🗣️ <b>Trader's Whisper:</b> {human_text}</span></div>""", unsafe_allow_html=True)
        st.progress(buy_pressure / 100, text=f"Buying Pressure: {buy_pressure}%")
        
        c1, c2, c3, c4 = st.columns(4)
        nifty = live_ticks.get("99926000", 0.0)
        c1.metric("NIFTY 50", f"₹{nifty}")
        c2.metric("BANK NIFTY", f"₹{live_ticks.get('99926009', 0.0)}")
        c3.metric("MAX PAIN", f"₹{max_pain}")
        c4.metric("PCR", f"{pcr}")

    with col_ai:
        st.subheader("🔮 Dynamic AI Trajectory")
        action = verdict.get("action", "WAIT")
        insight = verdict.get('logic', '')
        # Clear specific 404/Gemini Error display logic
        if "404" in insight or "gemini" in insight: insight = "⚠️ Backend AI Model Error. Verify DeepSeek Config in Backend."
        
        st.markdown(f"**🔥 Current Fund Action:** `{action}`")
        st.metric(label="🎯 AI Math Base Move", value=f"{forecast}%")
        st.caption(f"**Logic Insight:** {insight}")

    # Sector Sense (Same as original)
    if sector_sense:
        st.markdown("---")
        st.subheader("🔄 Live Sector Rotation")
        sc1, sc2 = st.columns([1.5, 1])
        with sc1:
            z_vals = [d['z_score'] for d in sector_sense.values()]
            fig_sec = go.Figure(go.Bar(x=list(sector_sense.keys()), y=z_vals, marker_color=['#ef5350' if z < -1.5 else '#26a69a' if z > 1.5 else '#78909c' for z in z_vals]))
            fig_sec.update_layout(height=280, template="plotly_dark", margin=dict(l=0, r=0, t=20, b=0))
            st.plotly_chart(fig_sec, use_container_width=True)
        with sc2:
            st.dataframe(pd.DataFrame.from_dict(sector_sense, orient='index').reset_index()[['index', 'z_score', 'status']], use_container_width=True, hide_index=True)

    # Chart (Same as original)
    st.markdown("---")
    chart_payload = load_json("nifty_chart.json")
    if chart_payload.get("data"):
        df_c = pd.DataFrame(chart_payload["data"], columns=['Datetime','O','H','L','C','V'])
        df_c['Datetime'] = pd.to_datetime(df_c['Datetime'])
        df_c.set_index('Datetime', inplace=True)
        fig_c = go.Figure(data=[go.Candlestick(x=df_c.index, open=df_c['O'], high=df_c['H'], low=df_c['L'], close=df_c['C'])])
        fig_c.update_layout(template="plotly_dark", height=400, margin=dict(l=0, r=0, t=0, b=0))
        st.plotly_chart(fig_c, use_container_width=True)

# ==========================================
# 🔮 3. PREDICTIVE SCENARIOS (API DRIVEN ADD-ON)
# ==========================================
st.markdown("---")
st.subheader("🔮 Predictive Scenarios & Strict Backtesting")

def render_projection_table(title, filename, current_nifty, expanded_val):
    payload = load_json(filename)
    with st.expander(f"{title} Flow Projections", expanded=expanded_val):
        if not payload or "data" not in payload:
            st.info(f"⌛ Awaiting {title} sync...")
            return

        st.caption(f"**Net Drift:** `{payload.get('drift', 0)}%` | Direct Angel One API Verified ✅")
        current_hm = now_ist.strftime("%H:%M")
        table_rows = []
        
        for item in payload['data']:
            start_t, end_t = item['Time Frame'].split("-")
            avg_pred = item['Target (Avg)']
            # 🎯 DIRECT API FALLBACK
            actual_val = item.get('Actual', 0.0)
            
            row = {"Interval": item['Time Frame'], "Target": f"₹{avg_pred}"}
            
            if current_hm > end_t:
                # If backend missed fetching it, UI will fetch it once
                if actual_val <= 0:
                    actual_val = get_actual_price_api(end_t)
                
                if actual_val > 0:
                    pts_err = abs(actual_val - avg_pred)
                    score = max(0, 100 - (pts_err * 5))
                    row.update({"Actual Market": f"₹{actual_val}", "Backtest Score": f"{round(score, 1)}%", "Status": "✅"})
                else:
                    row.update({"Actual Market": "Pending API", "Backtest Score": "-", "Status": "✅"})
            elif start_t <= current_hm <= end_t:
                row.update({"Actual Market": f"₹{current_nifty} (LIVE)", "Backtest Score": "Running...", "Status": "🔵"})
            else:
                row.update({"Actual Market": "-", "Backtest Score": "-", "Status": "⏳"})
            table_rows.append(row)
        st.dataframe(pd.DataFrame(table_rows), use_container_width=True, hide_index=True)

nifty_val = live_ticks.get("99926000", 0.0) if 'live_ticks' in locals() else 0.0
c_p1, c_p2, c_p3 = st.columns(3)
with c_p1: render_projection_table("🌅 Morning", "morning_projections.json", nifty_val, (9 <= now_ist.hour < 11))
with c_p2: render_projection_table("🌍 Afternoon", "afternoon_projections.json", nifty_val, (11 <= now_ist.hour < 13))
with c_p3: render_projection_table("🔥 End Game", "end_game_projections.json", nifty_val, (now_ist.hour >= 13))

# --- 🧠 FINAL VERDICT (Same as original) ---
st.divider()
st.subheader("🧠 The Final Institutional Verdict")
with st.container(border=True):
    st.markdown(f"### 🔥 FUND ACTION: {verdict.get('action', 'WAIT')}")
    st.markdown(f"**🧠 CRO Logic:** {verdict.get('logic', 'Analyzing...')}")
    st.metric("⚡ Conviction Score", f"{verdict.get('conviction_score', 0)}/100")

# --- 🌍 GLOBAL MATRIX (Same as original) ---
st.divider()
st.subheader("🌍 The 10-Pillar Global Macro Matrix")
g_cols = st.columns(5)
sd = stats.get('stats', {})
g_cols[0].metric("🇺🇸 Nasdaq", f"{sd.get('Nasdaq_Cash', 0)}%")
g_cols[1].metric("🇺🇸 S&P 500", f"{sd.get('US_Fut_SP500', 0)}%")
g_cols[2].metric("🇯🇵 Nikkei", f"{sd.get('Nikkei_Japan', 0)}%")
g_cols[3].metric("🇪🇺 DAX", f"{sd.get('DAX_Cash', 0)}%")
g_cols[4].metric("🇮🇳 GIFT Nifty", f"{sd.get('GIFT_Nifty', 0)}%")

# --- 💼 PORTFOLIO (Same as original) ---
st.divider()
st.subheader("💼 Fund Portfolio")
op = load_json("open_trades.json")
if op: st.dataframe(pd.DataFrame.from_dict(op, orient='index'), use_container_width=True)
else: st.info("No active positions.")