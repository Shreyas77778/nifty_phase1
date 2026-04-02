import os
import requests
import pandas as pd
import pytz
import json
import yfinance as yf
from dotenv import load_dotenv
from google import genai
from tvDatafeed import TvDatafeed, Interval

# 🚀 NEW: Import our custom NSE Option Chain Engine
from nse_options_engine import NSEOptionChain

from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

class GlobalPulse:
    def __init__(self):
        # DeepSeek is OpenAI compatible
        api_key = os.getenv("DEEPSEEK_API_KEY")
        base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        
        self.ai_client = OpenAI(api_key=api_key, base_url=base_url)
        # ... rest of the code        
         
        import logging
        logging.getLogger('tvDatafeed').setLevel(logging.CRITICAL) 
        self.tv = TvDatafeed()
        
        self.tv_tickers = {
            "Nasdaq_Cash": ("IXIC", "NASDAQ"),          
            "Dow_Cash": ("DJI", "DJ"),  
            "US_Fut_Nasdaq100": ("NQ1!", "CME"),   
            "US_Fut_SP500": ("ES1!", "CME"),       
            "US_Fut_Dow": ("YM1!", "CBOT"),        
            "US_Fut_Russell": ("RTY1!", "CME"),    
            "EU_Fut_EuroStoxx50": ("FESX1!", "EUREX"), 
            "EU_Fut_DAX": ("FDAX1!", "EUREX"),         
            "UK_Fut_FTSE": ("Z1!", "ICEEUR"),          
            "DAX_Cash": ("DAX", "XETR"),               
            "GIFT_Nifty": ("GIFTNIFTY", "NSE"),      
            "Nikkei_Japan": ("NI225", "TVC"),    
            "HangSeng_HK": ("HSI", "TVC"),      
            "Shanghai_China": ("000001", "SSE"), 
            "Dollar_Index": ("DXY", "TVC"), 
            "US_10Y_Yield": ("US10Y", "TVC"),    
            "Crude_Oil": ("CL1!", "NYMEX")         
        }
        
        self.yf_tickers = {
            "Nasdaq_Cash": "^IXIC",          
            "Dow_Cash": "^DJI",  
            "US_Fut_Nasdaq100": "NQ=F",   
            "US_Fut_SP500": "ES=F",       
            "US_Fut_Dow": "YM=F",        
            "US_Fut_Russell": "RTY=F",    
            "EU_Fut_EuroStoxx50": "^STOXX50E", 
            "EU_Fut_DAX": "^GDAXI",            
            "UK_Fut_FTSE": "^FTSE",            
            "DAX_Cash": "^GDAXI",               
            "GIFT_Nifty": None,     
            "Nikkei_Japan": "^N225",    
            "HangSeng_HK": "^HSI",      
            "Shanghai_China": "000001.SS", 
            "Dollar_Index": "DX-Y.NYB", 
            "US_10Y_Yield": "^TNX",    
            "Crude_Oil": "CL=F"         
        }
        
        self.ist = pytz.timezone('Asia/Kolkata')
        self.news_api_url = "http://127.0.0.1:8000/api/news/latest?limit=5"
        
        # 🚀 NEW: Initialize NSE Options Engine
        try:
            self.nse_oc = NSEOptionChain()
        except Exception as e:
            print(f"⚠️ NSE Engine Init Error: {e}")
            self.nse_oc = None

    def _get_price_with_fallback(self, name):
        last_price, prev_close = None, None
        source = "TV"
        
        tv_symbol, tv_exc = self.tv_tickers.get(name, (None, None))
        if tv_symbol:
            try:
                df = self.tv.get_hist(symbol=tv_symbol, exchange=tv_exc, interval=Interval.in_daily, n_bars=2)
                if df is not None and not df.empty:
                    last_price = float(df['close'].iloc[-1])
                    prev_close = float(df['close'].iloc[-2]) if len(df) >= 2 else last_price
            except Exception:
                last_price = None

        if last_price is None:
            yf_symbol = self.yf_tickers.get(name)
            if yf_symbol:
                try:
                    ticker = yf.Ticker(yf_symbol)
                    hist = ticker.history(period="5d")
                    if len(hist) >= 1:
                        last_price = float(hist['Close'].iloc[-1])
                        prev_close = float(hist['Close'].iloc[-2]) if len(hist) >= 2 else last_price
                        source = "YF"
                except Exception:
                    pass
        
        return last_price, prev_close, source

    # 🛠️ UPDATE: Connected to Live NSE Option Chain
    def get_market_pcr(self):
        """
        Fetches the Live Nifty Put-Call Ratio (PCR) and Max Pain from NSE.
        """
        if self.nse_oc:
            try:
                data = self.nse_oc.get_pcr_and_max_pain()
                return data 
            except Exception as e:
                print(f"⚠️ Error fetching live PCR/Max Pain: {e}")
                
        return {"spot_price": 0.0, "pcr": "UNKNOWN", "max_pain": "UNKNOWN", "total_ce_oi": 0, "total_pe_oi": 0}

    def fetch_live_news_sentiment(self):
        try:
            response = requests.get(self.news_api_url, timeout=10)
            if response.status_code == 200:
                articles = response.json()
                if not articles: return {"overall_mood": "Neutral", "top_headlines": ["No fresh news."]}
                
                bull_count = sum(1 for a in articles if "Bullish" in a.get("sentiment", ""))
                bear_count = sum(1 for a in articles if "Bearish" in a.get("sentiment", ""))
                
                overall_mood = "Bullish" if bull_count > bear_count else "Bearish" if bear_count > bull_count else "Mixed/Neutral"
                
                top_headlines = [f"{a['title']} -> Sentiment: {a['sentiment'].upper()}" for a in articles]
                return {"overall_mood": overall_mood, "top_headlines": top_headlines}
            return {"overall_mood": "Unknown", "top_headlines": ["News API error."]}
        except:
            return {"overall_mood": "Offline", "top_headlines": ["News Engine offline."]}

    def get_asian_macro_trend(self):
        asian_keys = ["Shanghai_China", "Nikkei_Japan", "HangSeng_HK"]
        total_change, valid_markets = 0.0, 0
        raw_changes = {}

        for name in asian_keys:
            last_price, prev_close, src = self._get_price_with_fallback(name)
            if last_price is not None and prev_close and prev_close != 0:
                change_pct = ((last_price - prev_close) / prev_close) * 100
                raw_changes[f"{name} ({src})"] = round(change_pct, 2)
                total_change += change_pct
                valid_markets += 1
                
        avg_momentum = round(total_change / valid_markets, 2) if valid_markets > 0 else 0.0
        trend = "🟢 Strong Bullish" if avg_momentum > 0.6 else "↗️ Mild Bullish" if avg_momentum > 0 else "↘️ Mild Bearish" if avg_momentum > -0.6 else "🔴 Strong Bearish"
        
        return {
            "raw_asian_changes": raw_changes,
            "net_asian_momentum": avg_momentum,
            "asian_sentiment": trend
        }

    def get_global_context(self):
        print("🔍 Scanning The Global Financial Matrix (TV + YF Fallback + NSE Options)...")
        stats = {}
        
        for name in self.tv_tickers.keys():
            last_price, prev_close, src = self._get_price_with_fallback(name)
            if last_price is not None and prev_close and prev_close != 0:
                pct_change = ((last_price - prev_close) / prev_close) * 100
                stats[name] = round(pct_change, 2)
            else:
                stats[name] = 0.0
            
        news_data = self.fetch_live_news_sentiment()
        asian_bias = self.get_asian_macro_trend()
        
        # 🛠️ UPDATE: Extracting PCR and Max Pain
        options_data = self.get_market_pcr() 
        pcr = options_data.get('pcr', 'UNKNOWN')
        max_pain = options_data.get('max_pain', 'UNKNOWN')
            
        return {
            "stats": stats,
            "news_sentiment": news_data,
            "asian_bias": asian_bias, 
            "pcr": pcr,
            "max_pain": max_pain,
            "options_data": options_data, 
            "timestamp": pd.Timestamp.now(tz=self.ist).strftime("%Y-%m-%d %H:%M:%S")
        }

    def get_indian_closes(self):
        last_price, _, src = self._get_price_with_fallback("GIFT_Nifty")
        return {"NIFTY 50": round(last_price, 2) if last_price else 0.0}