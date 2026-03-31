import json
import time
import random
import os
import numpy as np
from datetime import datetime

# --- CONFIGURATION ---
FILE_NAME = "live_market.json"
NIFTY_TOKEN = "99926000"
BANKNIFTY_TOKEN = "99926009"

# Token mappings for Sector Rotation tracking
SECTORS = {
    "BANKING": ["SBIN", "HDFC", "ICICI"],
    "IT": ["INFY", "TCS", "WIPRO"],
    "AUTO": ["MARUTI", "TATAMOTORS"],
    "PHARMA": ["SUNPHARMA", "DRREDDY"],
    "RELIANCE": ["RELIANCE"]
}

# Initial Prices
prices = {
    NIFTY_TOKEN: 22500.0,
    BANKNIFTY_TOKEN: 48200.0,
}

def generate_sector_sense(nifty_change):
    """
    Calculates Z-Scores for sectors relative to Nifty's performance.
    """
    sector_data = {}
    changes = []
    
    for sector in SECTORS:
        # Generate a random change % for each sector
        # Often sectors move in the same direction as Nifty but with different intensity
        s_change = nifty_change + random.uniform(-0.5, 0.5)
        changes.append(s_change)
        sector_data[sector] = s_change

    # Calculate Z-Score: (Value - Mean) / StdDev
    mean_change = np.mean(changes)
    std_change = np.std(changes) if np.std(changes) > 0 else 0.1
    
    final_sense = {}
    for sector, s_change in sector_data.items():
        z_score = round((s_change - mean_change) / std_change, 2)
        
        # Arbitrage Status Logic
        status = "Neutral"
        if z_score > 1.5: status = "Ultra-High ARB (Sell Setup)"
        elif z_score < -1.5: status = "Ultra-High ARB (Buy Setup)"
        
        final_sense[sector] = {
            "change_pct": round(s_change, 2),
            "z_score": z_score,
            "status": status
        }
    return final_sense

def update_market_json():
    global prices
    print(f"📡 Mock Market Generator Started... Writing to {FILE_NAME}")

    while True:
        try:
            # 1. Simulate Price Movement (Random Walk)
            nifty_move = random.uniform(-2.0, 2.0)
            prices[NIFTY_TOKEN] = round(prices[NIFTY_TOKEN] + nifty_move, 2)
            prices[BANKNIFTY_TOKEN] = round(prices[BANKNIFTY_TOKEN] + (nifty_move * 2.1), 2)
            
            # 2. Calculate Market Breadth
            adv = random.randint(20, 45)
            dec = 50 - adv
            ratio = round(adv / dec, 2) if dec > 0 else 50.0

            # 3. Simulate Advanced Metrics (Order Flow)
            adv_metrics = {}
            for token in [NIFTY_TOKEN, BANKNIFTY_TOKEN]:
                bids = random.randint(500000, 1500000)
                asks = random.randint(500000, 1500000)
                adv_metrics[token] = {
                    "total_buy_qty": bids,
                    "total_sell_qty": asks
                }

            # 4. Sector Rotation Logic
            nifty_change_sim = (nifty_move / prices[NIFTY_TOKEN]) * 100
            sector_sense = generate_sector_sense(nifty_change_sim)

            # 5. Build Final Payload
            payload = {
                "ltp_data": prices,
                "market_breadth": {
                    "advances": adv,
                    "declines": dec,
                    "ratio": ratio
                },
                "advanced_metrics": adv_metrics,
                "sector_sense": sector_sense,
                "macro_vwap_stretch": round(random.uniform(-0.4, 0.4), 2),
                "timestamp": datetime.now().strftime("%H:%M:%S")
            }

            # 6. ATOMIC SAVE (Write to temp then rename)
            with open(FILE_NAME + ".tmp", "w") as f:
                json.dump(payload, f, indent=4)
            os.replace(FILE_NAME + ".tmp", FILE_NAME)

            print(f"✅ [{payload['timestamp']}] Nifty: {prices[NIFTY_TOKEN]} | Adv: {adv} | Dec: {dec}")
            time.sleep(2) # Refresh every 2 seconds

        except Exception as e:
            print(f"❌ Error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    update_market_json()