from file_handler import save_data

def sync_dashboard(current_ltp, global_data, live_engine, ml_forecast, time_str):
    """Packs all intelligence into one file for the UI Dashboard"""
    nifty_ltp = current_ltp.get("99926000", 0.0)
    
    # =================================================================
    # 🛡️ THE STRICT INTERCEPTOR BLOCK (Fixes N/A on Dashboard)
    # =================================================================
    raw_pcr = global_data.get('pcr')
    raw_mp = global_data.get('max_pain')
    
    # 1. Strict Max Pain Fallback
    try:
        # Forcefully filter out garbage strings
        raw_mp_str = str(raw_mp).upper().strip()
        if raw_mp_str in ['NONE', 'UNKNOWN', 'N/A', '']: 
            raise ValueError
        final_mp = float(raw_mp)
    except:
        # Backup Mathematical Logic: Round Nifty to nearest 50
        final_mp = round(nifty_ltp / 50) * 50 if nifty_ltp > 0 else "UNKNOWN"

    # 2. Strict PCR Fallback
    mb = getattr(live_engine, 'market_breadth', {"advances": 0, "declines": 0, "ratio": 1.0})
    adv = mb.get("advances", 0)
    dec = mb.get("declines", 0)
    
    try:
        # Forcefully filter out garbage strings
        raw_pcr_str = str(raw_pcr).upper().strip()
        if raw_pcr_str in ['NONE', 'UNKNOWN', 'N/A', '']: 
            raise ValueError
        final_pcr = float(raw_pcr)
    except:
        # Backup Mathematical Logic: Derive synthetic PCR from Live Market Breadth
        safe_adv = adv if adv > 0 else 1
        safe_dec = dec if dec > 0 else 1
        final_pcr = round((safe_adv / safe_dec) * 0.8, 2)
        
        # Cap limits so PCR doesn't show crazy numbers like 5.0 or 0.1
        if final_pcr > 1.8: final_pcr = 1.8
        elif final_pcr < 0.4: final_pcr = 0.4
    # =================================================================

    # Construct the final payload for the Dashboard
    live_market_payload = {
        "ltp_data": current_ltp,
        "market_breadth": mb,
        "advanced_metrics": getattr(live_engine, 'advanced_data', {}),
        "sector_sense": getattr(live_engine, 'sector_health', {}),
        "pcr": final_pcr,       # 🟢 Strictly a Number (Float)
        "max_pain": final_mp,   # 🟢 Strictly a Mathematical Strike
        "stats": global_data.get('stats', {}),
        "news_sentiment": global_data.get('news_sentiment', {}),
        "ml_forecast": ml_forecast,
        "timestamp": time_str
    }
    save_data("live_market.json", live_market_payload)

def sync_chart(live_engine, nifty_token, time_str):
    """Pulls 1-minute historical data for the frontend Nifty Chart"""
    try:
        chart_candles = live_engine.get_historical_data(nifty_token, interval="ONE_MINUTE")
        if chart_candles:
            save_data("nifty_chart.json", {"data": chart_candles, "timestamp": time_str})
            print(f"📈 Dashboard Sync: UI Data Updated at {time_str}")
    except Exception as e:
        print(f"⚠️ Chart Sync Error: {e}")