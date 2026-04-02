import json
import os
import pandas as pd
from datetime import datetime

def save_data(filename, payload):
    tmp_filename = f"{filename}.tmp"
    with open(tmp_filename, "w") as f:
        json.dump(payload, f, indent=4)
    os.replace(tmp_filename, filename)
    
    def get_r1_bias(stats, news_mood, ai_client):
        """ R1 se pucho ki aaj ka drift positive hoga ya negative based on macro logic """
    prompt = f"Given these macros {stats} and news {news_mood}, predict the Nifty drift bias for the next 2 hours. Just give a float multiplier between -1.0 to 1.0."
    # R1 call code...
    # Return bias

def get_rolling_anchor(current_time, frames, nifty_ltp, nifty_df):
    """
    Har 15 min ke interval ke start par pichle interval ka 'Actual Close' uthata hai.
    """
    anchor_price = nifty_ltp
    for start_t, end_t, label in frames:
        # Agar current time interval ke start par hai (e.g., 09:31, 09:46)
        if current_time == start_t and nifty_df is not None and not nifty_df.empty:
            try:
                # Pichle minute (interval end) ka price fetch karna
                target_ts = pd.Timestamp.now().replace(second=0, microsecond=0)
                idx = nifty_df.index.get_indexer([target_ts], method='pad')[0]
                if idx != -1:
                    anchor_price = nifty_df.iloc[idx]['Close']
                    print(f"🔗 Re-Anchored to Actual Market: ₹{anchor_price} at {current_time}")
            except: pass
    return anchor_price

def calculate_morning_projections(nifty_ltp, stats, news_mood, current_time, api):
    # ... (Aapka purana math logic same rahega) ...
    
    projections = []
    for s_t, e_t, label in frames:
        avg_pred = base * (1 + (step / 100))
        
        # 🎯 LIVE API LOOKUP: Agar interval khatam ho gaya hai
        actual_val = 0.0
        if current_time > e_t:
            actual_val = get_actual_price_from_api(api, "99926000", e_t)
            
        projections.append({
            "Time Frame": f"{s_t}-{e_t}",
            "Context": label,
            "Target (Avg)": round(avg_pred, 2),
            "Actual": round(actual_val, 2) if actual_val > 0 else 0.0
        })
# ---------------------------------------------------------
# 🌍 AFTERNOON PROJECTIONS (10:31 - 13:30)
# ---------------------------------------------------------
def calculate_afternoon_projections(nifty_ltp, stats, market_breadth, current_time, api):
    # Logic: Midday Bias (A/D) + Euro Open Impact (DAX)
    dax = stats.get("DAX_Cash", stats.get("EU_Fut_DAX", 0.0))
    ad_ratio = market_breadth.get("ratio", 1.0)
    
    expected_drift = ((ad_ratio - 1) * 0.15) + (dax * 0.4)
    
    frames = [
        ("10:31", "11:00", "Midday Flow"), ("11:01", "11:30", "Theta Phase"),
        ("11:31", "12:00", "Institutional"), ("12:01", "12:30", "Euro Pre-Open"),
        ("12:31", "13:00", "DAX Open Impact"), ("13:01", "13:30", "Aft Trend")
    ]
    
    projections = []
    base = nifty_ltp
    step = expected_drift / 6
    
    for s_t, e_t, label in frames:
        avg_pred = base * (1 + (step / 100))
        actual_val = get_actual_price_from_api(api, "99926000", e_t) if current_time > e_t else 0.0
        
        projections.append({
            "Time Frame": f"{s_t}-{e_t}",
            "Context": label,
            "Target (Avg)": round(avg_pred, 2),
            "Actual": round(actual_val, 2)
        })
        base = avg_pred
        
    save_data("afternoon_projections.json", {"data": projections, "drift": round(expected_drift, 2)})

# ---------------------------------------------------------
# 🔥 END GAME PROJECTIONS (13:31 - 15:30)
# ---------------------------------------------------------
def calculate_end_game_projections(nifty_ltp, stats, market_breadth, news_mood, current_time, api):
    # Logic: 40% US Fut + 40% Short Covering (Breadth) + 20% Euro Trend
    us_fut = stats.get("US_Fut_Nasdaq100", stats.get("US_Fut_SP500", 0.0))
    ad_ratio = market_breadth.get("ratio", 1.0)
    dax = stats.get("DAX_Cash", 0.0)
    
    drift = (us_fut * 0.4) + ((ad_ratio - 1) * 0.25) + (dax * 0.2)
    if news_mood == "Bullish": drift += 0.15
    
    frames = [
        ("13:31", "14:00", "US Setup"), ("14:01", "14:30", "2PM Shift"),
        ("14:31", "15:00", "Short Covering"), ("15:01", "15:30", "MOC Orders")
    ]
    
    projections = []
    base = nifty_ltp
    step = drift / 4
    
    for s_t, e_t, label in frames:
        avg_pred = base * (1 + (step / 100))
        actual_val = get_actual_price_from_api(api, "99926000", e_t) if current_time > e_t else 0.0
        
        projections.append({
            "Time Frame": f"{s_t}-{e_t}",
            "Context": label,
            "Target (Avg)": round(avg_pred, 2),
            "Actual": round(actual_val, 2)
        })
        base = avg_pred
        
    save_data("end_game_projections.json", {"data": projections, "drift": round(drift, 2)}) 
    def get_actual_price_from_api(api, token, target_time_str):
        """
    Angel One API se exact target_time ka closing price fetch karta hai.
    target_time_str: "09:30", "10:15" etc.
    """
    try:
        import pandas as pd
        from datetime import datetime, timedelta
        
        now = datetime.now()
        # Aaj ki date aur target time ko milana
        target_dt = datetime.combine(now.date(), datetime.strptime(target_time_str, "%H:%M").time())
        
        # 5 minute ka buffer le kar data mangwana taaki missing candle na ho
        from_date = (target_dt - timedelta(minutes=5)).strftime('%Y-%m-%d %H:%M')
        to_date = target_dt.strftime('%Y-%m-%d %H:%M')

        historic_param = {
            "exchange": "NSE",
            "symboltoken": token,
            "interval": "ONE_MINUTE",
            "fromdate": from_date,
            "todate": to_date
        }
        
        # API CALL
        response = api.getCandleData(historic_param)
        
        if response.get('status') and response.get('data'):
            # Sabse aakhri candle (target minute) ka 'Close' price (index 4)
            actual_close = response['data'][-1][4]
            return float(actual_close)
    except Exception as e:
        print(f"⚠️ API Price Fetch Error: {e}")
    return 0.0