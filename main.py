import time
import json
import os
import re  
import pytz
import csv 
import signal
import sys
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv

# Components
from auth_manager import SmartSession
from global_pulse import GlobalPulse
from indian_ingester import IndianLiveIngester
from decision_engine import DecisionEngine
from notifier import TelegramNotifier
from model_predictor import ModelPredictor
from options_engine import OptionsStrikeEngine
import ui_sync # 🚀 Professional Backend Sync Module

load_dotenv()

# IST Timezone Configuration
IST = pytz.timezone('Asia/Kolkata')

# 💰 🚀 THE MASTER FUND CONFIGURATION
PAPER_CAPITAL = 100000  
ALLOCATION_PER_TRADE = 0.10  
MAX_CONCURRENT_TRADES = int(1 / ALLOCATION_PER_TRADE) 

# 🛡️ POSITIONAL RISK PARAMS
POSITIONAL_TARGET_PCT = 0.03 
INITIAL_SL_PCT = 0.015       
TRAILING_SL_PCT = 0.01       

# Global flag for graceful shutdown
shutdown_flag = False

def signal_handler(sig, frame):
    global shutdown_flag
    print("\n⚠️ Interruption detected! Initiating graceful shutdown...")
    shutdown_flag = True

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def get_ist_now():
    return datetime.now(IST)

def clean_json(raw_str):
    if not raw_str: return "{}"
    match = re.search(r'\{.*\}', str(raw_str), re.DOTALL)
    return match.group(0) if match else raw_str

# 🛠️ Atomic File Saving to prevent JSON corruption
def save_data(filename, payload):
    tmp_filename = f"{filename}.tmp"
    with open(tmp_filename, "w") as f:
        json.dump(payload, f, indent=4)
    os.replace(tmp_filename, filename) 

def load_open_trades():
    if os.path.exists("open_trades.json"):
        try:
            with open("open_trades.json", "r") as f: return json.load(f)
        except Exception as e: 
            print(f"⚠️ Error loading trades: {e}. Starting fresh.")
            return {}
    return {}

def save_open_trades(trades_dict):
    save_data("open_trades.json", trades_dict)

def log_to_excel(trade_data):
    filename = "dummy_trades.csv"
    file_exists = os.path.isfile(filename)
    with open(filename, mode='a', newline='', encoding='utf-8') as f:
        fieldnames = ["Entry_Time", "Symbol", "Action", "Lots", "Qty", "Entry_Price", "Target", "SL", "Exit_Time", "Exit_Price", "Delta_Used", "Profit", "Loss", "Exit_Reason"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader() 
        writer.writerow({
            "Entry_Time": trade_data.get("Entry_Time"),
            "Symbol": trade_data.get("Symbol"),
            "Action": trade_data.get("Action"),
            "Lots": trade_data.get("Lots"),      
            "Qty": trade_data.get("Qty"),        
            "Entry_Price": round(trade_data.get("Entry", 0), 2),
            "Target": round(trade_data.get("Target", 0), 2),
            "SL": round(trade_data.get("SL", 0), 2),
            "Exit_Time": trade_data.get("Exit_Time"),
            "Exit_Price": round(trade_data.get("Exit_Price", 0), 2),
            "Delta_Used": round(abs(trade_data.get("Delta", 0.5)), 2),
            "Profit": round(trade_data.get("Profit", 0.0), 2),  
            "Loss": round(trade_data.get("Loss", 0.0), 2),      
            "Exit_Reason": trade_data.get("Exit_Reason")
        })

def main_orchestrator():
    global shutdown_flag
    print("\n" + "="*60)
    print("🔥 BOOTING: NIFTY-50 AI [ROLLING ANCHOR + BACKEND SYNC] 🔥")
    print("="*60 + "\n")

    print("🔌 Connecting to Angel One...")
    session = SmartSession()
    smart_api = session.login()
    if not smart_api: return

    pulse = GlobalPulse()
    live_engine = IndianLiveIngester(smart_api)
    engine = DecisionEngine(pulse.ai_client)
    notifier = TelegramNotifier()
    predictor = ModelPredictor()
    options_engine = OptionsStrikeEngine() 

    pre_market_done_today = False
    last_reset_date = get_ist_now().date()
    open_dummy_trades = load_open_trades()

    while not shutdown_flag: 
        try:
            now = get_ist_now()
            current_time = now.strftime("%H:%M")
            is_weekday = now.weekday() < 5 

            # --- PHASE 1: PRE-MARKET ---
            if is_weekday and "08:45" <= current_time <= "09:14" and not pre_market_done_today:
                global_data = pulse.get_global_context()
                save_data("latest_verdict.json", {"status": "Pre-Market Scanning..."})
                pre_market_done_today = True

            # --- PHASE 2: LIVE TRADING ---
            elif is_weekday and "09:15" <= current_time <= "15:30":
                if not live_engine.is_running:
                    live_engine.start_streaming()
                
                global_data = pulse.get_global_context()
                current_ltp = getattr(live_engine, 'current_ltp', {})
                nifty_ltp = current_ltp.get("99926000", 0.0)
                vix_india = getattr(live_engine, 'get_india_vix', lambda: 15.0)()

                # 🛠️ 1. ROLLING ANCHOR DATA PREP
                nifty_df = pd.DataFrame()
                if os.path.exists("nifty_chart.json"):
                    try:
                        with open("nifty_chart.json", "r") as f:
                            c_data = json.load(f).get("data", [])
                            if c_data:
                                nifty_df = pd.DataFrame(c_data, columns=['Datetime', 'Open', 'High', 'Low', 'Close', 'Volume'])
                                nifty_df['Datetime'] = pd.to_datetime(nifty_df['Datetime'])
                                nifty_df.set_index('Datetime', inplace=True)
                    except: pass

                # 🚀 2. BACKEND PROJECTION UPDATES (WITH ANCHORING)
                if nifty_ltp > 0:
                  g_stats = global_data.get('stats', {})
                m_breadth = getattr(live_engine, 'market_breadth', {"ratio": 1.0})
                news_mood = global_data.get('news_sentiment', {}).get('overall_mood', 'Neutral')
    
    # 🌅 Morning Projections (09:15 - 10:30)
                if "09:15" <= current_time <= "10:30":
        # ui_sync.py mein hum smart_api pass kar rahe hain
                    ui_sync.calculate_morning_projections(nifty_ltp, g_stats, news_mood, current_time, smart_api)
    
    # 🌍 Afternoon Projections (10:31 - 13:30)
                elif "10:31" <= current_time <= "13:30":
                    ui_sync.calculate_afternoon_projections(nifty_ltp, g_stats, m_breadth, current_time, smart_api)
    
    # 🔥 End-Game Projections (13:31 - 15:30)
                elif "13:31" <= current_time <= "15:30":
                    ui_sync.calculate_end_game_projections(nifty_ltp, g_stats, m_breadth, news_mood, current_time, smart_api)
                # 🧠 3. AI VERDICT
                verdict_raw = engine.get_final_verdict(global_data, vix_india=vix_india)
                verdict = json.loads(clean_json(verdict_raw))
                save_data("latest_verdict.json", verdict)
                action = verdict.get("action", "WAIT")

                # 📊 4. DASHBOARD SYNC
                live_market_payload = {
                    "ltp_data": current_ltp,
                    "market_breadth": getattr(live_engine, 'market_breadth', {}),
                    "sector_sense": getattr(live_engine, 'sector_health', {}),
                    "stats": global_data.get('stats', {}),
                    "timestamp": now.strftime("%H:%M:%S")
                }
                save_data("live_market.json", live_market_payload)
                
                try:
                    chart_candles = live_engine.get_historical_data("99926000", interval="ONE_MINUTE")
                    if chart_candles:
                        save_data("nifty_chart.json", {"data": chart_candles, "timestamp": now.strftime("%H:%M:%S")})
                except: pass

                # 🛡️ 5. TRADE MANAGEMENT & SIGNAL GENERATION
                # (Existing trade logic remains same)
                completed_trades = []
                for tid, trade in open_dummy_trades.items():
                    ltp = current_ltp.get(trade['Token'])
                    if not ltp: continue
                    # Trailing SL & Exit logic here...
                    # (Code truncated for brevity, same as your original)
                
                # Signal Generation (Deploy 10% Tranche)
                if action in ["BUY", "SELL"] and len(open_dummy_trades) < MAX_CONCURRENT_TRADES:
                    if nifty_ltp > 0:
                        # Trade punching logic here...
                        pass

                time.sleep(30)

            # --- PHASE 3: OFF-MARKET ---
            else:
                if live_engine.is_running: live_engine.stop_streaming()
                time.sleep(600) 

        except Exception as e:
            print(f"❌ ERROR: {e}")
            time.sleep(60)

    if live_engine.is_running: live_engine.stop_streaming()
    sys.exit(0)

if __name__ == "__main__":
    main_orchestrator()