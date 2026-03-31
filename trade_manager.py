import os
import csv
import config
from file_handler import save_data, load_json

def load_open_trades():
    return load_json("open_trades.json")

def save_open_trades(trades_dict):
    save_data("open_trades.json", trades_dict)

def log_to_excel(trade_data):
    filename = "dummy_trades.csv"
    file_exists = os.path.isfile(filename)
    with open(filename, mode='a', newline='', encoding='utf-8') as f:
        fieldnames = ["Entry_Time", "Symbol", "Action", "Lots", "Qty", "Entry_Price", "Target", "SL", "Exit_Time", "Exit_Price", "Delta_Used", "Profit", "Loss", "Exit_Reason"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists: writer.writeheader() 
        writer.writerow({
            "Entry_Time": trade_data.get("Entry_Time"), "Symbol": trade_data.get("Symbol"),
            "Action": trade_data.get("Action"), "Lots": trade_data.get("Lots"),      
            "Qty": trade_data.get("Qty"), "Entry_Price": round(trade_data.get("Entry", 0), 2),
            "Target": round(trade_data.get("Target", 0), 2), "SL": round(trade_data.get("SL", 0), 2),
            "Exit_Time": trade_data.get("Exit_Time"), "Exit_Price": round(trade_data.get("Exit_Price", 0), 2),
            "Delta_Used": round(abs(trade_data.get("Delta", 0.5)), 2), "Profit": round(trade_data.get("Profit", 0.0), 2),  
            "Loss": round(trade_data.get("Loss", 0.0), 2), "Exit_Reason": trade_data.get("Exit_Reason")
        })

def manage_active_trades(open_trades, current_ltp, action, current_time, notifier):
    completed_trades = []
    for trade_id, trade in open_trades.items():
        ltp = current_ltp.get(trade['Token'])
        if not ltp: continue
        exit_triggered, exit_reason = False, ""
        
        if trade['Action'] == "BUY":
            if ltp > trade.get('Peak_Price', trade['Entry']):
                trade['Peak_Price'] = ltp
                new_sl = ltp * (1 - config.TRAILING_SL_PCT)
                if new_sl > trade['SL']:
                    print(f"🛡️ Trailing SL Upgraded: ₹{round(trade['SL'], 2)} ➡️ ₹{round(new_sl, 2)}")
                    trade['SL'] = new_sl
            if ltp >= trade['Target']: exit_triggered, exit_reason = True, "🎯 Target Hit"
            elif ltp <= trade['SL']: exit_triggered, exit_reason = True, "🛑 Trailing SL Hit"
            elif action == "SELL": exit_triggered, exit_reason = True, "🚨 EMERGENCY CUT: Trend Reversed"
                
        elif trade['Action'] == "SELL":
            if ltp < trade.get('Peak_Price', trade['Entry']):
                trade['Peak_Price'] = ltp
                new_sl = ltp * (1 + config.TRAILING_SL_PCT)
                if new_sl < trade['SL']:
                    print(f"🛡️ Trailing SL Downgraded: ₹{round(trade['SL'], 2)} ➡️ ₹{round(new_sl, 2)}")
                    trade['SL'] = new_sl
            if ltp <= trade['Target']: exit_triggered, exit_reason = True, "🎯 Target Hit"
            elif ltp >= trade['SL']: exit_triggered, exit_reason = True, "🛑 Trailing SL Hit"
            elif action == "BUY": exit_triggered, exit_reason = True, "🚨 EMERGENCY CUT: Trend Reversed"

        if exit_triggered:
            trade['Exit_Price'], trade['Exit_Time'], trade['Exit_Reason'] = ltp, current_time, exit_reason
            qty, entry_px = trade['Qty'], trade['Entry']
            trade_delta = abs(trade.get('Delta', 0.5)) 
            pnl = (ltp - entry_px) * qty * trade_delta if trade['Action'] == "BUY" else (entry_px - ltp) * qty * trade_delta
                
            if pnl > 0: trade['Profit'], trade['Loss'] = pnl, 0.0
            else: trade['Profit'], trade['Loss'] = 0.0, abs(pnl)
            
            log_to_excel(trade) 
            completed_trades.append(trade_id)
            pnl_str = f"🟢 Profit: ₹{round(pnl, 2)}" if pnl > 0 else f"🔴 Loss: ₹{round(pnl, 2)}"
            print(f"💸 [TRADE COMPLETED] {trade['Symbol']} | Reason: {exit_reason} | {pnl_str}")
            notifier.send_alert({"Message": f"💸 Dummy Trade Closed: {trade['Symbol']} at {ltp}. {pnl_str}. Reason: {exit_reason}"})

    for tid in completed_trades: del open_trades[tid]
    if completed_trades: save_open_trades(open_trades)
    return open_trades

def execute_new_signals(open_trades, action, nifty_ltp, vix_india, current_time, options_engine):
    if action in ["BUY", "SELL"] and len(open_trades) < config.MAX_CONCURRENT_TRADES:
        print(f"\n🎯 SIGNAL TRIGGERED: {action} (Deploying {config.ALLOCATION_PER_TRADE*100}% Tranche)")
        sym = "NIFTY"
        trade_id = f"{sym}_{current_time.replace(':', '')}"
        
        if trade_id not in open_trades:
            if nifty_ltp > 0:
                entry_price = nifty_ltp
                tgt_price = entry_price * (1 + config.POSITIONAL_TARGET_PCT) if action == "BUY" else entry_price * (1 - config.POSITIONAL_TARGET_PCT)
                sl_price = entry_price * (1 - config.INITIAL_SL_PCT) if action == "BUY" else entry_price * (1 + config.INITIAL_SL_PCT)
                
                allocated_capital = config.PAPER_CAPITAL * config.ALLOCATION_PER_TRADE
                opt_data = options_engine.select_optimal_strike(
                    symbol=sym, spot_price=nifty_ltp, action=action, 
                    vix_value=vix_india, spot_sl=sl_price,        
                    capital=allocated_capital, risk_pct=100.0 
                )
                
                display_symbol = f"{sym} ({opt_data['Recommended_Strike']})"

                open_trades[trade_id] = {
                    "Token": config.NIFTY_TOKEN, "Entry_Time": current_time, "Symbol": display_symbol,  
                    "Action": action, "Lots": opt_data.get('Lots_To_Buy', 1), "Qty": opt_data.get('Total_Quantity', 1), 
                    "Entry": entry_price, "Peak_Price": entry_price, "Target": tgt_price, "SL": sl_price,
                    "Delta": opt_data.get('BS_Exact_Delta', 0.5), "Exit_Price": None, "Exit_Time": None,
                    "Profit": 0.0, "Loss": 0.0, "Exit_Reason": None
                }
                save_open_trades(open_trades) 
                print(f"⚡ [NEW TRANCHE] {display_symbol} | Action: {action} | Spot: ₹{entry_price}")
            else:
                print("⚠️ Waiting for valid Nifty LTP to punch trade...")
    elif action in ["BUY", "SELL"]:
        print(f"🛡️ Max Capital Deployed ({config.MAX_CONCURRENT_TRADES}/{config.MAX_CONCURRENT_TRADES} Trades). Holding positions.")
    return open_trades