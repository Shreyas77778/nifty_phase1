import time
import json
import os
import re  
import pytz
import csv 
import signal
import sys
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

# 🛠️ UPDATE: Atomic File Saving to prevent JSON corruption on crash
def save_data(filename, payload):
    tmp_filename = f"{filename}.tmp"
    with open(tmp_filename, "w") as f:
        json.dump(payload, f, indent=4)
    os.replace(tmp_filename, filename) # Atomic overwrite

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
    print("🔥 BOOTING: NIFTY-50 AI [SMART POSITIONAL + BLACK-SCHOLES] 🔥")
    print(f"💰 Capital: ₹{PAPER_CAPITAL} | Allocation Per Tranche: {ALLOCATION_PER_TRADE*100}%")
    print(f"🌍 System Timezone: Asia/Kolkata | Start Time: {get_ist_now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60 + "\n")

    print("🔌 Connecting to Angel One SmartAPI...")
    session = SmartSession()
    smart_api = session.login()
    if not smart_api: 
        print("❌ System Offline: Angel One Login Failed.")
        return

    print("🧩 Initializing Quant Modules...")
    pulse = GlobalPulse()
    live_engine = IndianLiveIngester(smart_api)
    engine = DecisionEngine(pulse.gemini)
    notifier = TelegramNotifier()
    predictor = ModelPredictor()
    options_engine = OptionsStrikeEngine() 

    training_done_today = False 
    pre_market_done_today = False
    last_reset_date = get_ist_now().date()
    
    open_dummy_trades = load_open_trades()
    print(f"✅ Loaded {len(open_dummy_trades)} active positional trades from memory.\n")

    while not shutdown_flag: # 🛠️ UPDATE: Allows graceful exit
        try:
            now = get_ist_now()
            current_time = now.strftime("%H:%M")
            is_weekday = now.weekday() < 5 

            # --- PHASE 1: PRE-MARKET ---
            if is_weekday and "08:45" <= current_time <= "09:14" and not pre_market_done_today:
                print(f"📡 [{current_time} AM] Triggering Pre-Market Intelligence Scan...")
                global_data = pulse.get_global_context()
                
                try: ml_forecast = predictor.predict_today_move(global_data.get('stats', {}))
                except: ml_forecast = 0
                global_data['ml_forecast'] = ml_forecast
                global_data['market_breadth'] = {"advances": 0, "declines": 0, "ratio": 1.0}
                global_data['advanced_metrics'] = {}
                
                verdict_raw = engine.get_final_verdict(global_data, vix_india=15.0, atr_value=None) 
                verdict = json.loads(clean_json(verdict_raw))
                verdict['action'] = f"📊 PRE-MARKET: {verdict.get('action')}"
                
                notifier.send_alert(verdict)
                save_data("latest_verdict.json", verdict)
                pre_market_done_today = True

            # --- PHASE 2: LIVE TRADING ---
            elif is_weekday and "09:15" <= current_time <= "15:30":
                if not live_engine.is_running:
                    print("🟢 Market Open! Starting WebSocket Data Stream...")
                    live_engine.start_streaming()
                
                print(f"🔄 [{current_time}] Running Tactical NIFTY Scan...")
                 
                global_data = pulse.get_global_context()
                try: ml_forecast = predictor.predict_today_move(global_data.get('stats', {}))
                except: ml_forecast = 0
                global_data['ml_forecast'] = ml_forecast
                global_data['market_breadth'] = getattr(live_engine, 'market_breadth', {"advances": 0, "declines": 0, "ratio": 1.0})
                global_data['advanced_metrics'] = getattr(live_engine, 'advanced_metrics', {})
                vix_india = getattr(live_engine, 'get_india_vix', lambda: 15.0)()
                
                token_map = getattr(live_engine, 'token_map', {})
                current_ltp = getattr(live_engine, 'current_ltp', {})

                verdict_raw = engine.get_final_verdict(global_data, vix_india=vix_india, atr_value=None)
                verdict = json.loads(clean_json(verdict_raw))
                save_data("latest_verdict.json", verdict)
                
                action = verdict.get("action", "WAIT")
                
                if action == "WAIT":
                    pass # 🛠️ UPDATE: Removed the print spam here so it doesn't flood logs every 30 seconds.
                
                nifty_token = "99926000" 
                nifty_ltp = current_ltp.get(nifty_token, 0.0)

                # =================================================================
                # 🚀 DASHBOARD SYNC LOGIC (Updates Chart, Sector, PCR & Macro Data)
                # =================================================================
                live_market_payload = {
                    "ltp_data": current_ltp,
                    "market_breadth": global_data.get('market_breadth', getattr(live_engine, 'market_breadth', {})),
                    "advanced_metrics": getattr(live_engine, 'advanced_data', {}),
                    "sector_sense": getattr(live_engine, 'sector_health', {}),
                    
                    "pcr": global_data.get('pcr', 'UNKNOWN'),
                    "max_pain": global_data.get('max_pain', 'UNKNOWN'),
                    "stats": global_data.get('stats', {}),
                    "news_sentiment": global_data.get('news_sentiment', {}),
                    "ml_forecast": ml_forecast,
                    
                    "timestamp": now.strftime("%H:%M:%S")
                }
                save_data("live_market.json", live_market_payload)

                try:
                    # Fetching 1-minute historical data for Nifty Chart
                    chart_candles = live_engine.get_historical_data(nifty_token, interval="ONE_MINUTE")
                    if chart_candles:
                        save_data("nifty_chart.json", {"data": chart_candles, "timestamp": now.strftime("%H:%M:%S")})
                        print(f"📈 Dashboard Sync: UI Updated at {now.strftime('%H:%M:%S')}")
                except Exception as e:
                    print(f"⚠️ Chart Sync Error: {e}")
                # =================================================================

                # =================================================================
                # 🚀 1. ACTIVE TRADE MANAGER (TRAILING SL + REVERSAL LOGIC)
                # =================================================================
                completed_trades = []
                for trade_id, trade in open_dummy_trades.items():
                    ltp = current_ltp.get(trade['Token'])
                    if not ltp: continue
                    
                    exit_triggered = False
                    exit_reason = ""
                    
                    if trade['Action'] == "BUY":
                        if ltp > trade.get('Peak_Price', trade['Entry']):
                            trade['Peak_Price'] = ltp
                            new_sl = ltp * (1 - TRAILING_SL_PCT)
                            if new_sl > trade['SL']:
                                print(f"🛡️ Trailing SL Upgraded: ₹{round(trade['SL'], 2)} ➡️ ₹{round(new_sl, 2)}")
                                trade['SL'] = new_sl
                        
                        if ltp >= trade['Target']:
                            exit_triggered, exit_reason = True, "🎯 Positional Target Hit"
                        elif ltp <= trade['SL']:
                            exit_triggered, exit_reason = True, "🛑 Trailing SL Hit"
                        elif action == "SELL":
                            exit_triggered, exit_reason = True, "🚨 EMERGENCY CUT: AI Trend Reversed to SELL"
                            
                    elif trade['Action'] == "SELL":
                        if ltp < trade.get('Peak_Price', trade['Entry']):
                            trade['Peak_Price'] = ltp
                            new_sl = ltp * (1 + TRAILING_SL_PCT)
                            if new_sl < trade['SL']:
                                print(f"🛡️ Trailing SL Downgraded: ₹{round(trade['SL'], 2)} ➡️ ₹{round(new_sl, 2)}")
                                trade['SL'] = new_sl

                        if ltp <= trade['Target']:
                            exit_triggered, exit_reason = True, "🎯 Positional Target Hit"
                        elif ltp >= trade['SL']:
                            exit_triggered, exit_reason = True, "🛑 Trailing SL Hit"
                        elif action == "BUY":
                            exit_triggered, exit_reason = True, "🚨 EMERGENCY CUT: AI Trend Reversed to BUY"

                    if exit_triggered:
                        trade['Exit_Price'] = ltp
                        trade['Exit_Time'] = current_time
                        trade['Exit_Reason'] = exit_reason
                        
                        qty = trade['Qty']
                        entry_px = trade['Entry']
                        
                        # Note: This is purely a linear theoretical PnL.
                        trade_delta = abs(trade.get('Delta', 0.5)) 
                        
                        if trade['Action'] == "BUY": 
                            pnl = (ltp - entry_px) * qty * trade_delta
                        else: 
                            pnl = (entry_px - ltp) * qty * trade_delta
                            
                        if pnl > 0: trade['Profit'], trade['Loss'] = pnl, 0.0
                        else: trade['Profit'], trade['Loss'] = 0.0, abs(pnl)
                        
                        log_to_excel(trade) 
                        completed_trades.append(trade_id)
                        
                        pnl_str = f"🟢 Option Profit: ₹{round(pnl, 2)}" if pnl > 0 else f"🔴 Option Loss: ₹{round(pnl, 2)}"
                        
                        print("=" * 50)
                        print(f"💸 [TRADE COMPLETED] {trade['Symbol']}")
                        print(f"Underlying Exit Price: ₹{ltp} | Delta: {trade_delta} | Reason: {exit_reason}")
                        print(f"{pnl_str}")
                        print("=" * 50)
                        notifier.send_alert({"Message": f"💸 Dummy Trade Closed: {trade['Symbol']} at Spot {ltp}. {pnl_str}. Reason: {exit_reason}"})

                for tid in completed_trades:
                    del open_dummy_trades[tid]
                    
                if completed_trades: # Only save if something changed
                    save_open_trades(open_dummy_trades) 

                # =================================================================
                # 🚀 2. SIGNAL GENERATOR (10% SCALE-IN LOGIC)
                # =================================================================
                if action in ["BUY", "SELL"]:
                    if len(open_dummy_trades) < MAX_CONCURRENT_TRADES:
                        print(f"\n🎯 SIGNAL TRIGGERED: {action} (Deploying 10% Tranche)")
                        
                        sym = "NIFTY"
                        trade_id = f"{sym}_{current_time.replace(':', '')}"
                        
                        if trade_id not in open_dummy_trades:
                            if nifty_ltp > 0:
                                entry_price = nifty_ltp
                                
                                if action == "BUY":
                                    tgt_price = entry_price * (1 + POSITIONAL_TARGET_PCT)
                                    sl_price = entry_price * (1 - INITIAL_SL_PCT)
                                else:
                                    tgt_price = entry_price * (1 - POSITIONAL_TARGET_PCT)
                                    sl_price = entry_price * (1 + INITIAL_SL_PCT)
                                
                                allocated_capital = PAPER_CAPITAL * ALLOCATION_PER_TRADE
                                
                                opt_data = options_engine.select_optimal_strike(
                                    symbol=sym, spot_price=nifty_ltp, action=action, 
                                    vix_value=vix_india, spot_sl=sl_price,        
                                    capital=allocated_capital, risk_pct=100.0 
                                )
                                
                                suggested_option = opt_data['Recommended_Strike']
                                lots_to_buy = opt_data.get('Lots_To_Buy', 1)
                                total_qty = opt_data.get('Total_Quantity', 1)
                                bs_delta = opt_data.get('BS_Exact_Delta', 0.5)
                                
                                display_symbol = f"{sym} ({suggested_option})"

                                open_dummy_trades[trade_id] = {
                                    "Token": nifty_token,
                                    "Entry_Time": current_time,
                                    "Symbol": display_symbol,  
                                    "Action": action,
                                    "Lots": lots_to_buy,
                                    "Qty": total_qty,
                                    "Entry": entry_price,
                                    "Peak_Price": entry_price, 
                                    "Target": tgt_price,
                                    "SL": sl_price,
                                    "Delta": bs_delta, 
                                    "Exit_Price": None,
                                    "Exit_Time": None,
                                    "Profit": 0.0,
                                    "Loss": 0.0,
                                    "Exit_Reason": None
                                }
                                
                                save_open_trades(open_dummy_trades) 
                                
                                print("-" * 55)
                                print(f"⚡ [NEW TRANCHE DEPLOYED] {display_symbol}")
                                print(f"Action: {action} | Spot Entry: ₹{entry_price}")
                                print(f"🧮 Black-Scholes Delta: {bs_delta} | Quant: {lots_to_buy} Lots")
                                print(f"🎯 Target: ₹{round(tgt_price, 2)} | 🛑 Initial SL: ₹{round(sl_price, 2)}")
                                print(f"⚙️ Trailing SL + Emergency Reversal System Active")
                                print("-" * 55)
                            else:
                                print("⚠️ Waiting for valid Nifty LTP to punch trade...")
                    else:
                        print(f"🛡️ Max Capital Deployed ({MAX_CONCURRENT_TRADES}/{MAX_CONCURRENT_TRADES} Trades). Holding positions.")
                
                time.sleep(30)

            # --- PHASE 3: OFF-MARKET / TRAINING ---
            else:
                if live_engine.is_running:
                    print("🔴 Market Closed! Stopping WebSocket Data Stream...")
                    live_engine.stop_streaming()
                    print("🛡️ NOTE: Trades are being HELD OVERNIGHT (Positional Mode).")
                    
                print(f"🌙 Night/Weekend Shift [{current_time} IST]: Tracking Global Cues & Preparing Models...")
                global_data = pulse.get_global_context()
                
                if now.date() > last_reset_date:
                    print("🧹 New Trading Day. Preserving Open Trades...")
                    smart_api = session.login()
                    if smart_api: live_engine.api = smart_api
                    
                    last_reset_date = now.date()
                    training_done_today = False
                    pre_market_done_today = False

                if not training_done_today and ("16:00" <= current_time <= "23:00" or not is_weekday):
                    print("🧠 Starting Offline Auto-Evolution (ML Retraining)...")
                    try:
                        predictor.train_intelligence()
                        predictor.run_backtest()
                    except: pass
                    training_done_today = True
                    print("✅ Training Complete.")

                print(f"💤 System Idle [{current_time} IST].")
                time.sleep(600) 

        except Exception as e:
            print(f"❌ CRITICAL ERROR IN MAIN LOOP: {e}")
            time.sleep(60)

    # Graceful exit logic
    if live_engine.is_running:
        live_engine.stop_streaming()
    print("🛑 Bot cleanly shut down.")
    sys.exit(0)

if __name__ == "__main__":
    main_orchestrator()