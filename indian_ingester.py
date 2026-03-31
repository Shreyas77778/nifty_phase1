import os
import time
import pandas as pd
import threading
import json
import pytz
from datetime import datetime, timedelta
from SmartApi.smartWebSocketV2 import SmartWebSocketV2

class IndianLiveIngester:
    def __init__(self, smart_api):
        self.api = smart_api
        self.current_ltp = {}
        self.advanced_data = {} 
        self.market_breadth = {"advances": 0, "declines": 0, "unchanged": 0, "ratio": 1.0}
        self.vwap_deviations = {} 
        self.sector_health = {}
        
        self.ist = pytz.timezone('Asia/Kolkata')
        self.last_sync_time = datetime.now(self.ist)
        self.is_running = False 
        self.error_count = 0 
        
        self.auth_token = getattr(smart_api, 'jwt_token', smart_api.access_token)
        self.api_key = smart_api.api_key
        self.client_code = smart_api.userId
        self.feed_token = getattr(smart_api, 'feed_token', None)
        
        if not self.feed_token:
            try: self.feed_token = smart_api.getfeedToken()
            except: pass

        self.token_map = {
            "26000": "NIFTY 50", "26009": "BANK NIFTY", 
            "99926000": "NIFTY 50", "99926009": "BANK NIFTY", 
            "15083": "ADANIENT", "3251": "ADANIPORTS", "3003": "APOLLOHOSP",
            "3351": "ASIANPAINT", "5900": "AXISBANK", "16669": "BAJAJ-AUTO",
            "16675": "BAJAJFINSV", "317": "BAJFINANCE", "10604": "BHARTIARTL",
            "10794": "BPCL", "1083": "BRITANNIA", "14732": "CIPLA",
            "11532": "COALINDIA", "15044": "DIVISLAB", "10901": "DRREDDY",
            "9132": "EICHERMOT", "14065": "GRASIM", "11809": "HCLTECH",
            "1333": "HDFCBANK", "4244": "HDFCLIFE", "17963": "HEROMOTOCO",
            "2031": "HINDALCO", "1406": "HINDUNILVR", "341": "ICICIBANK",
            "10099": "ITC", "4963": "INDUSINDBK", "1594": "INFY",
            "10440": "JSWSTEEL", "1922": "KOTAKBANK", "11630": "LT",
            "17939": "LTIM", "3329": "M&M", "10940": "MARUTI",
            "17534": "NESTLEIND", "11654": "NTPC", "2475": "ONGC",
            "14977": "POWERGRID", "2885": "RELIANCE", "21808": "SBI-LIFE",
            "3045": "SBIN", "3103": "SUNPHARMA", "3456": "TATAMOTORS",
            "3499": "TATASTEEL", "3506": "TITAN", "11536": "TCS",
            "3787": "TECHM", "11483": "TRENT", "11287": "UPL",
            "11262": "ULTRACEMCO", "3718": "WIPRO"
        }
        
        self.sector_map = {
            "IT": ["INFY", "TCS", "HCLTECH", "TECHM", "WIPRO", "LTIM"],
            "BANKING": ["HDFCBANK", "ICICIBANK", "SBIN", "AXISBANK", "KOTAKBANK", "INDUSINDBK"],
            "AUTO": ["TATAMOTORS", "M&M", "MARUTI", "BAJAJ-AUTO", "HEROMOTOCO", "EICHERMOT"],
            "ENERGY": ["RELIANCE", "ONGC", "NTPC", "POWERGRID", "COALINDIA", "BPCL"]
        }
        self.setup_websocket()

    def get_historical_data(self, token, interval="ONE_MINUTE"):
        try:
            to_date = datetime.now(self.ist).strftime('%Y-%m-%d %H:%M')
            from_date = (datetime.now(self.ist) - timedelta(days=1)).strftime('%Y-%m-%d 09:15')
            params = {"exchange": "NSE", "symboltoken": token, "interval": interval, "fromdate": from_date, "todate": to_date}
            response = self.api.getCandleData(params)
            if response and response.get('status') and response.get('data'): return response['data']
            return []
        except Exception as e:
            print(f"⚠️ Historical Data Error: {e}")
            return []

    def setup_websocket(self):
        try:
            self.sws = SmartWebSocketV2(self.auth_token, self.api_key, self.client_code, self.feed_token)
            self.sws.on_data = self.on_data
            self.sws.on_open = self.on_open
            self.sws.on_error = self.on_error
            self.sws.on_close = self.on_close
        except Exception as e:
            print(f"❌ WebSocket Setup Error: {e}")
            self.sws = None

    def on_data(self, ws, msg):
        try:
            if isinstance(msg, dict) and 'last_traded_price' in msg:
                token = msg.get('token')
                price = msg['last_traded_price'] / 100
                
                # 🐛 BULLETPROOF FIX: Prevent 0 overwrite for prev_close
                raw_close = msg.get('close_price', 0) / 100
                if raw_close > 0:
                    prev_close = raw_close
                else:
                    prev_close = self.advanced_data.get(token, {}).get("prev_close", 0)

                oi = msg.get('open_interest', 0)  
                atp_vwap = msg.get('average_traded_price', 0) / 100
                
                best_5_buy = msg.get('best_5_buy_data', [])
                best_5_sell = msg.get('best_5_sell_data', [])
                total_buy_qty = sum([b.get('quantity', 0) for b in best_5_buy]) if isinstance(best_5_buy, list) else 0
                total_sell_qty = sum([s.get('quantity', 0) for s in best_5_sell]) if isinstance(best_5_sell, list) else 0
                
                self.current_ltp[token] = price
                if len(token) == 5 and token.startswith("26"):
                    legacy_token = f"999{token}"
                    self.current_ltp[legacy_token] = price
                    
                stretch_pct = 0.0
                if not token.startswith("26") and not token.startswith("99926"):
                    if atp_vwap > 0 and price > 0: 
                        stretch_pct = ((price - atp_vwap) / atp_vwap) * 100
                        self.vwap_deviations[token] = stretch_pct
                
                self.advanced_data[token] = {
                    "symbol": self.token_map.get(token, token),
                    "ltp": price,
                    "prev_close": prev_close,
                    "oi": oi,
                    "total_buy_qty": total_buy_qty,
                    "total_sell_qty": total_sell_qty,
                    "vwap_stretch_pct": round(stretch_pct, 3)
                }

                now_ist = datetime.now(self.ist)
                if (now_ist - self.last_sync_time).total_seconds() >= 2:
                    self._calculate_market_metrics() 
                    self._calculate_sector_sense() 
                    self.last_sync_time = now_ist
                    
        except Exception as e:
            self.error_count += 1

    def _calculate_market_metrics(self):
        advances, declines, unchanged = 0, 0, 0
        for token, data in self.advanced_data.items():
            if token.startswith("26") or token.startswith("99926"): continue
            ltp = data.get("ltp", 0)
            prev_close = data.get("prev_close", 0)
            if prev_close > 0:
                if ltp > prev_close: advances += 1
                elif ltp < prev_close: declines += 1
                else: unchanged += 1
        
        # 🐛 Safe ratio calculation
        ratio = round(advances / declines, 2) if declines > 0 else float(advances)
        self.market_breadth = {"advances": advances, "declines": declines, "unchanged": unchanged, "ratio": ratio}

    def _calculate_sector_sense(self):
        nifty_token = "99926000"
        nifty_ltp = self.current_ltp.get(nifty_token, 0)
        nifty_prev = self.advanced_data.get(nifty_token, {}).get("prev_close", 0)
        nifty_pct = ((nifty_ltp - nifty_prev) / nifty_prev * 100) if nifty_prev > 0 else 0.0

        for sector, symbols in self.sector_map.items():
            sect_pcts = []
            for sym in symbols:
                token = next((k for k, v in self.token_map.items() if v == sym), None)
                if token:
                    ltp = self.advanced_data.get(token, {}).get("ltp", 0)
                    pc = self.advanced_data.get(token, {}).get("prev_close", 0)
                    if pc > 0: sect_pcts.append(((ltp - pc) / pc) * 100)
            
            if sect_pcts:
                avg_sect_pct = sum(sect_pcts) / len(sect_pcts)
                divergence = avg_sect_pct - nifty_pct
                z_score = round(divergence / 0.6, 2)
                status = "NEUTRAL"
                if z_score >= 1.5: status = "🚀 ULTRA-HIGH ARB (Sell Setup)"
                elif z_score <= -1.5: status = "🩸 ULTRA-HIGH ARB (Buy Setup)"
                self.sector_health[sector] = {"change_pct": round(avg_sect_pct, 2), "divergence": round(divergence, 2), "z_score": z_score, "status": status}

    def on_open(self, ws):
        print("🟢 WebSocket Connected: Nifty Core Feed Active.")
        token_keys = list(self.token_map.keys())
        token_list = [{"exchangeType": 1, "tokens": token_keys}]
        try: self.sws.subscribe("alpha_nifty_stream", 3, token_list)
        except Exception as e: print(f"❌ Subscription Error: {e}")

    def on_error(self, ws, error): print(f"⚠️ WebSocket Error: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        if self.is_running:
            print(f"❌ WebSocket Disconnected. Auto-reconnecting in 5s...")
            time.sleep(5)
            self.setup_websocket()
            threading.Thread(target=self.sws.connect, daemon=True).start()

    def start_streaming(self):
        if self.is_running or not self.sws: return
        self.is_running = True
        threading.Thread(target=self.sws.connect, daemon=True).start()
        print("⚡ Live Mode: WebSocket thread launched.")

    def stop_streaming(self):
        if self.is_running and self.sws:
            try:
                self.is_running = False 
                self.sws.close()
            except: pass

    def get_india_vix(self):
        import yfinance as yf
        try:
            vix = yf.Ticker("^INDIAVIX").history(period="1d")['Close'].iloc[-1]
            return round(vix, 2)
        except: return 15.0