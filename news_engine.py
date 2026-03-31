import asyncio
import hashlib
import feedparser
import pytz
import requests
import re
import time
import torch
import pandas as pd
import pandas_ta as ta
import aiohttp  # 🚀 NEW: For ultra-fast parallel web scraping
from functools import lru_cache # 🚀 NEW: For FinBERT memory caching
from calendar import timegm
from difflib import SequenceMatcher
from bs4 import BeautifulSoup
from collections import defaultdict
from heapq import nlargest
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from deep_translator import GoogleTranslator
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from typing import List, Dict
import trafilatura
import yfinance as yf

# --- SQLALCHEMY DATABASE INTEGRATION ---
from sqlalchemy import create_engine, Column, Integer, String, Float, JSON
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = "sqlite:///./financial_news.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class ArticleDB(Base):
    __tablename__ = "articles"
    
    id = Column(Integer, primary_key=True, index=True)
    hash = Column(String, unique=True, index=True)
    title = Column(String)
    url = Column(String)
    published = Column(String)
    timestamp = Column(Float)
    content_modes = Column(JSON)
    tickers = Column(JSON)
    sectors = Column(JSON)
    sentiment = Column(String)
    ingestion_prices = Column(JSON)

Base.metadata.create_all(bind=engine)

def save_article_to_db(article_data: dict):
    db = SessionLocal()
    try:
        exists = db.query(ArticleDB).filter(ArticleDB.hash == article_data["hash"]).first()
        if not exists:
            db_item = ArticleDB(
                hash=article_data["hash"],
                title=article_data["title"],
                url=article_data["url"],
                published=article_data["published"],
                timestamp=article_data["timestamp"],
                content_modes=article_data["content_modes"],
                tickers=article_data["tickers"],
                sectors=article_data["sectors"],
                sentiment=article_data["sentiment"],
                ingestion_prices=article_data["ingestion_prices"]
            )
            db.add(db_item)
            db.commit()
    except Exception as e:
        print(f"❌ DB Save Error: {e}")
        db.rollback()
    finally:
        db.close()

def load_articles_from_db():
    global news_database
    db = SessionLocal()
    try:
        articles = db.query(ArticleDB).order_by(ArticleDB.timestamp.desc()).limit(200).all()
        for art in articles:
            news_database[art.hash] = {
                "hash": art.hash,
                "title": art.title,
                "url": art.url,
                "published": art.published,
                "timestamp": art.timestamp,
                "content_modes": art.content_modes,
                "tickers": art.tickers,
                "sectors": art.sectors,
                "sentiment": art.sentiment,
                "ingestion_prices": art.ingestion_prices
            }
        print(f"💾 Loaded {len(articles)} historical articles from SQLite Database!")
    except Exception as e:
        print(f"❌ DB Load Error: {e}")
    finally:
        db.close()

# --- ADVANCED FINANCIAL TRANSFORMER (FinBERT) ---
from transformers import pipeline

if torch.cuda.is_available():
    device_id = 0
    print("🚀 GPU (CUDA) detected! Accelerating FinBERT...")
elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
    device_id = "mps"
    print("🚀 Apple Silicon (MPS) detected! Accelerating FinBERT...")
else:
    device_id = -1
    print("🖥️ Running FinBERT on CPU.")

print("Loading Advanced FinBERT Model...")
finbert = pipeline(
    "sentiment-analysis", 
    model="ProsusAI/finbert", 
    truncation=True, 
    max_length=512, 
    device=device_id
)
print("✅ FinBERT Loaded Successfully!")

news_database: Dict[str, dict] = {}

# --- 🌍 INSTITUTIONAL GLOBAL & INDIAN FEEDS ---
RSS_FEEDS = [
    "https://feeds.a.dj.com/rss/RSSMarketsMain.xml", 
    "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664", 
    "https://finance.yahoo.com/news/rssindex", 
    "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms", 
    "https://www.livemint.com/rss/markets" 
]

COMPANY_TICKERS = {
    "reliance": "RELIANCE", "tcs": "TCS", "hdfc": "HDFC",
    "infosys": "INFY", "sebi": "REGULATORY", "rbi": "REGULATORY",
    "tata": "TATA", "wipro": "WIPRO", "zomato": "ZOMATO",
    "sbi": "SBI", "icici": "ICICI", "maruti": "MARUTI",
    "airtel": "BHARTIARTL", "itc": "ITC", "adani": "ADANI",
    "fed": "GLOBAL_MACRO", "federal reserve": "GLOBAL_MACRO", 
    "inflation": "GLOBAL_MACRO", "rate cut": "GLOBAL_MACRO",
    "crude oil": "GLOBAL_MACRO", "nasdaq": "GLOBAL_MACRO", "war": "GLOBAL_MACRO"
}

TICKER_SECTORS = {
    "RELIANCE": "Energy", "TCS": "IT", "HDFC": "Banking",
    "INFY": "IT", "REGULATORY": "Finance", "TATA": "Automobile",
    "WIPRO": "IT", "ZOMATO": "Consumer", "SBI": "Banking", "ICICI": "Banking",
    "MARUTI": "Automobile", "BHARTIARTL": "Telecom", "ITC": "FMCG", "ADANI": "Infrastructure",
    "GLOBAL_MACRO": "Global Impact"
}

YF_TICKERS = {
    "RELIANCE": "RELIANCE.NS", "TCS": "TCS.NS", "HDFC": "HDFCBANK.NS",
    "INFY": "INFY.NS", "TATA": "TATAMOTORS.NS", "WIPRO": "WIPRO.NS",
    "ZOMATO": "ZOMATO.NS", "SBI": "SBIN.NS", "ICICI": "ICICIBANK.NS",
    "MARUTI": "MARUTI.NS", "BHARTIARTL": "BHARTIARTL.NS", "ITC": "ITC.NS",
    "ADANI": "ADANIENT.NS", 
    "GLOBAL_MACRO": "^NSEI" 
}

MACRO_TICKERS = {
    "NIFTY50": "^NSEI",
    "BANKNIFTY": "^NSEBANK",
    "US_10Y_YIELD": "^TNX",
    "CRUDE_OIL": "CL=F",
    "DOLLAR_INDEX": "DX-Y.NYB"
}

live_prices: Dict[str, dict] = {}

def get_market_momentum(change_pct: float) -> str:
    if -0.25 < change_pct < 0.25: return "Neutral"
    elif 0.25 <= change_pct < 1.25: return "Little Bullish"
    elif change_pct >= 1.25: return "Bullish"
    elif -1.25 < change_pct <= -0.25: return "Little Bearish"
    else: return "Bearish"

# 🚀 1. ULTRA-FAST BATCH PRICE FETCHING
def fetch_prices_sync():
    try:
        all_tickers = {**YF_TICKERS, **MACRO_TICKERS}
        yf_symbols = list(set(all_tickers.values()))
        
        # Batch download (1 network request instead of 20)
        data = yf.download(yf_symbols, period="3mo", interval="1d", group_by="ticker", progress=False)
        
        for symbol, yf_symbol in all_tickers.items():
            try:
                if len(yf_symbols) > 1:
                    df = data[yf_symbol].dropna(how='all').copy()
                else:
                    df = data.dropna(how='all').copy()
                    
                rsi_val, macd_val, macds_val, sma_20 = 50.0, 0.0, 0.0, 0.0
                tech_signal = "Neutral"
                
                if not df.empty and len(df) >= 30:
                    # Multi-index fix for pandas_ta
                    df.columns = df.columns.get_level_values(0) if isinstance(df.columns, pd.MultiIndex) else df.columns
                    
                    df.ta.rsi(length=14, append=True)
                    df.ta.macd(fast=12, slow=26, signal=9, append=True)
                    df.ta.sma(length=20, append=True)
                    
                    latest = df.iloc[-1]
                    rsi_val = latest.get('RSI_14', 50.0)
                    macd_val = latest.get('MACD_12_26_9', 0.0)
                    macds_val = latest.get('MACDs_12_26_9', 0.0)
                    sma_20 = latest.get('SMA_20', latest['Close'])
                    
                    if pd.isna(rsi_val): rsi_val = 50.0
                    if pd.isna(macd_val): macd_val = 0.0
                    if pd.isna(macds_val): macds_val = 0.0
                    if pd.isna(sma_20): sma_20 = latest['Close']
                    
                    if rsi_val < 30 and macd_val > macds_val: tech_signal = "Strong Buy (Oversold)"
                    elif rsi_val > 70 and macd_val < macds_val: tech_signal = "Strong Sell (Overbought)"
                    elif rsi_val > 60: tech_signal = "Bullish Trend"
                    elif rsi_val < 40: tech_signal = "Bearish Trend"

                # Ultra-fast data extraction from dataframe instead of hitting yf.Ticker object
                if not df.empty:
                    last_price = float(df.iloc[-1]['Close'])
                    prev_close = float(df.iloc[-2]['Close']) if len(df) > 1 else last_price
                    volume = float(df.iloc[-1]['Volume']) if 'Volume' in df.columns else 0
                else:
                    last_price, prev_close, volume = 0.0, 0.0, 0.0
                    
                change_pct = ((last_price - prev_close) / prev_close) * 100 if prev_close else 0
                
                live_prices[symbol] = {
                    "price": round(last_price, 2), 
                    "change_pct": round(change_pct, 2), 
                    "volume": int(volume),
                    "market_sentiment": get_market_momentum(change_pct),
                    "rsi": round(rsi_val, 2),
                    "macd": round(macd_val, 2),
                    "sma20": round(sma_20, 2),
                    "tech_signal": tech_signal
                }
            except Exception as e:
                print(f"Error calculating TA for {symbol}: {e}")
                continue
    except Exception as e:
        print(f"Global Price Fetch Error: {e}")

async def update_prices_task():
    await asyncio.to_thread(fetch_prices_sync)

DEV_TO_LATIN = {
    'अ':'a', 'आ':'aa', 'इ':'i', 'ई':'ee', 'उ':'u', 'ऊ':'oo', 'ऋ':'ri', 'ए':'e', 'ऐ':'ai', 'ओ':'o', 'औ':'au', 'अं':'an', 'अः':'ah', 'क':'k', 'ख':'kh', 'ग':'g', 'घ':'gh', 'ङ':'ng', 'च':'ch', 'छ':'chh', 'ज':'j', 'झ':'jh', 'ञ':'ny', 'ट':'t', 'ठ':'th', 'ड':'d', 'ढ':'dh', 'ण':'n', 'त':'t', 'थ':'th', 'द':'d', 'ध':'dh', 'न':'n', 'प':'p', 'फ':'ph', 'ब':'b', 'भ':'bh', 'म':'m', 'य':'y', 'र':'r', 'ल':'l', 'व':'v', 'श':'sh', 'ष':'sh', 'स':'s', 'ह':'h', 'ा':'a', 'ि':'i', 'ी':'ee', 'ु':'u', 'ू':'oo', 'ृ':'ri', 'े':'e', 'ै':'ai', 'ो':'o', 'ौ':'au', 'ं':'n', 'ः':'h', '्':''
}

def romanize_hindi(text: str) -> str:
    return "".join(DEV_TO_LATIN.get(char, char) for char in text)

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        
    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        
    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except RuntimeError:
                pass

manager = ConnectionManager()

def generate_fingerprint(title: str, published: str) -> str:
    return hashlib.sha256(f"{title}_{published}".encode()).hexdigest()

def is_semantic_duplicate(new_title: str, threshold: float = 0.65) -> bool:
    recent_articles = list(news_database.values())[-50:]
    for article in recent_articles:
        if SequenceMatcher(None, new_title.lower(), article['title'].lower()).ratio() >= threshold:
            return True
    return False

def extract_tickers(text: str) -> List[str]: 
    return list(set([ticker for keyword, ticker in COMPANY_TICKERS.items() if re.search(r'\b' + re.escape(keyword) + r'\b', text.lower())]))

def extract_sectors(tickers: List[str]) -> List[str]:
    return list(set([TICKER_SECTORS[t] for t in tickers if t in TICKER_SECTORS]))

# 🚀 2. ASYNCHRONOUS WEB SCRAPING
async def fetch_url_text(url: str) -> str:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}, timeout=10) as response:
                return await response.text()
    except Exception:
        return ""

async def scrape_article_text_async(url: str) -> str:
    try:
        html = await fetch_url_text(url)
        if not html: return ""
        text = trafilatura.extract(html, favor_precision=True, include_comments=False, include_tables=False, include_links=False)
        if text:
            return "\n\n".join([line.strip() for line in text.split('\n') if line.strip() and len(line.split()) >= 4 and "Also Read" not in line and "Click Here" not in line])
        return ""
    except Exception:
        return ""

def extract_key_points(text: str, num_points: int = 4) -> List[str]:
    sentences = [s.strip() for s in re.split(r'(?<=[.!?]) +', text) if s.strip()]
    if len(sentences) <= num_points: return sentences
    word_freq = defaultdict(int)
    for word in re.findall(r'\w+', text.lower()):
        if len(word) > 4: word_freq[word] += 1
    sent_scores = defaultdict(int)
    for i, sentence in enumerate(sentences):
        for word in re.findall(r'\w+', sentence.lower()):
            if word in word_freq: sent_scores[i] += word_freq[word]
    top_indices = nlargest(num_points, sent_scores, key=sent_scores.get)
    top_indices.sort()
    return [sentences[i] for i in top_indices]

# 🚀 3. FINBERT MEMORY CACHING (LRU CACHE)
@lru_cache(maxsize=2000)
def analyze_financial_sentiment_5way(text: str) -> str:
    try:
        if not text.strip(): return "Neutral"
        result = finbert(text[:2500])[0]
        label = result['label'].capitalize()
        score = result['score'] 
        
        if label == "Positive": return "Bullish" if score >= 0.80 else "Little Bullish"
        elif label == "Negative": return "Bearish" if score >= 0.80 else "Little Bearish"
        else: return "Neutral"
    except Exception as e:
        print(f"FinBERT Error: {e}")
        return "Neutral"

def get_sentiment_styling(granular_sentiment: str) -> tuple:
    if granular_sentiment == "Bullish": return "#28a745", "strong upward momentum"
    elif granular_sentiment == "Little Bullish": return "#66bb6a", "mild upward momentum or stabilization"
    elif granular_sentiment == "Bearish": return "#dc3545", "heavy downward pressure"
    elif granular_sentiment == "Little Bearish": return "#e57373", "mild downward pressure or slight pullback"
    else: return "#007bff", "range-bound or sideways trading"

def generate_ai_analysis(full_text: str, title: str, granular_sentiment: str) -> List[str]:
    pts = extract_key_points(full_text, 3)
    tickers = extract_tickers(title + " " + full_text)
    ticker_str = ", ".join(tickers) if tickers else "the broader market indices"
    
    color, impact = get_sentiment_styling(granular_sentiment)
    sentiment_html = f'<span style="color: {color}; font-weight: bold;">{granular_sentiment.upper()}</span>'
        
    analysis_text = f"<strong>💡 ADVANCED FinBERT ANALYSIS:</strong> Based on deep-learning contextual sentiment, this news is classified as {sentiment_html}. This suggests that stocks related to {ticker_str} could see {impact} in the near term."
    disclaimer_text = "<em>⚠️ AI generated analysis please do your analysis too.</em>"
    
    pts.append(analysis_text)
    pts.append(disclaimer_text)
    return pts

def generate_bull_bear(full_text: str) -> List[str]:
    pts = extract_key_points(full_text, 4)
    bb_pts = []
    for p in pts:
        point_sentiment = analyze_financial_sentiment_5way(p)
        color, _ = get_sentiment_styling(point_sentiment)
        bb_pts.append(f'<span style="color: {color};">⬤</span> <strong>{point_sentiment.upper()}:</strong> {p}')
    return bb_pts

async def fetch_and_process_feed(feed_url: str):
    try:
        # Async XML Fetch
        xml_data = await fetch_url_text(feed_url)
        if not xml_data: return
        feed = feedparser.parse(xml_data)
        
        entries = sorted(
            feed.entries, 
            key=lambda e: timegm(e.published_parsed) if e.get("published_parsed") else time.time()
        )
        
        for entry in entries:
            title = entry.get("title", "")
            published = entry.get("published", "")
            link = entry.get("link", "")
            
            combined_text = title.lower() + " " + entry.get("summary", "").lower()
            important_keywords = list(COMPANY_TICKERS.keys()) + ["nifty", "sensex", "banknifty", "earnings", "profit", "loss", "gdp", "cpi", "powell", "das"]
            has_impact = any(keyword in combined_text for keyword in important_keywords)
            
            if not has_impact: continue 
                
            article_hash = generate_fingerprint(title, published)
            if article_hash in news_database: continue  
            if is_semantic_duplicate(title): continue
                
            # Async Web Scraping
            full_text = await scrape_article_text_async(link)
            if not full_text: full_text = title

            first_sentences = " ".join([s.strip() for s in re.split(r'(?<=[.!?]) +', full_text) if s.strip()][:2])
            analysis_text = f"{title}. {first_sentences}"
            overall_sentiment_5way = analyze_financial_sentiment_5way(analysis_text)
                
            content_modes = {
                "full": full_text,
                "bullets": generate_ai_analysis(full_text, title, overall_sentiment_5way), 
                "bullbear": generate_bull_bear(full_text)
            }
            
            tickers = extract_tickers(title + " " + full_text)
            sectors = extract_sectors(tickers)
            
            published_parsed = entry.get("published_parsed")
            timestamp = timegm(published_parsed) if published_parsed else time.time()
            ingestion_prices = {t: live_prices[t]['price'] for t in tickers if t in live_prices}
                
            new_article = {
                "hash": article_hash, "title": title, "url": link, "published": published, 
                "timestamp": timestamp, "content_modes": content_modes, "tickers": tickers,
                "sectors": sectors, "sentiment": overall_sentiment_5way, "ingestion_prices": ingestion_prices 
            }
            
            news_database[article_hash] = new_article
            await asyncio.to_thread(save_article_to_db, new_article)
            
            print(f"🌍 GLOBAL MACRO SAVED: {title[:40]}... | Sentiment: {overall_sentiment_5way}")
            await manager.broadcast(new_article)
            
    except Exception as e:
        print(f"Feed parsing error for {feed_url}: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    await asyncio.to_thread(load_articles_from_db)
    
    scheduler = AsyncIOScheduler(timezone=pytz.utc)
    scheduler.add_job(update_prices_task, 'interval', minutes=2)
    await update_prices_task() 
    for url in RSS_FEEDS:
        scheduler.add_job(fetch_and_process_feed, 'interval', seconds=30, args=[url])
    scheduler.start()
    for url in RSS_FEEDS:
        await fetch_and_process_feed(url)
    yield 
    scheduler.shutdown()

app = FastAPI(title="Real-Time Indian Stock News", lifespan=lifespan)

class TranslateRequest(BaseModel):
    title: str
    content_text: str = ""
    content_list: List[str] = []
    mode: str
    target_lang: str

@app.post("/api/translate")
async def translate_content(req: TranslateRequest):
    if req.target_lang == 'en': return req.dict()
    google_lang = 'hi' if req.target_lang == 'hinglish' else req.target_lang
    try:
        translator = GoogleTranslator(source='en', target=google_lang)
        t_title = await asyncio.to_thread(translator.translate, req.title)
        if req.mode == 'text':
            chunks = [req.content_text[i:i+4000] for i in range(0, len(req.content_text), 4000)]
            t_text = "".join(await asyncio.to_thread(translator.translate_batch, chunks))
            if req.target_lang == 'hinglish': t_text = romanize_hindi(t_text)
            return {"title": t_title, "content_text": t_text, "content_list": [], "mode": "text"}
        else:
            t_list = await asyncio.to_thread(translator.translate_batch, req.content_list)
            if req.target_lang == 'hinglish': t_list = [romanize_hindi(item) for item in t_list]
            return {"title": t_title, "content_text": "", "content_list": t_list, "mode": "list"}
    except Exception:
        return req.dict()

@app.get("/api/news/latest")
async def get_latest_news(limit: int = 100): 
    articles = list(news_database.values())
    articles.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
    return articles[:limit]

@app.get("/api/prices")
async def get_live_prices():
    return live_prices

html_dashboard = """
<!DOCTYPE html>
<html>
    <head>
        <title>Live Indian Stock Market Dashboard</title>
        <script src="https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js"></script>
        <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
        <style>
            body { font-family: 'Segoe UI', sans-serif; background-color: #121212; color: #ffffff; padding: 20px; max-width: 1100px; margin: auto;}
            
            /* MACRO HEALTH BANNER STYLES */
            .macro-banner { background: #0f172a; border: 1px solid #334155; padding: 15px 25px; border-radius: 8px; margin-bottom: 20px; display: flex; flex-wrap: wrap; gap: 20px; align-items: center; justify-content: space-between; box-shadow: 0 4px 6px rgba(0,0,0,0.3); border-left: 5px solid #a855f7;}
            .macro-item { display: flex; flex-direction: column; gap: 5px; }
            .macro-label { color: #94a3b8; font-size: 0.85em; text-transform: uppercase; letter-spacing: 1px; }
            .macro-value { font-size: 1.2em; color: #fff; }

            .global-controls { background: #1e1e1e; padding: 20px 25px; border-radius: 8px; margin-bottom: 20px; display: flex; gap: 20px; align-items: center; border-left: 5px solid #ff9800; box-shadow: 0 4px 15px rgba(0,0,0,0.5); position: sticky; top: 10px; z-index: 100; flex-wrap: wrap;}
            .report-controls { background: #1a1a2e; padding: 15px 25px; border-radius: 8px; margin-bottom: 30px; display: flex; gap: 15px; align-items: center; border-left: 5px solid #4da3ff; justify-content: flex-end; flex-wrap: wrap;}
            .control-group { display: flex; align-items: center; gap: 8px; flex: 1; min-width: 180px;}
            .control-group label { font-weight: bold; color: #ccc; font-size: 0.95em;}
            select.ui-select { width: 100%; background: #2b2b2b; color: #fff; border: 1px solid #555; padding: 10px 12px; border-radius: 6px; cursor: pointer; font-size: 0.95em; outline: none; transition: 0.3s;}
            select.ui-select:hover { border-color: #888; }
            .download-btn { background: #ff3333; color: #fff; padding: 10px 20px; border: none; border-radius: 6px; cursor: pointer; font-weight: bold; font-size: 0.95em; transition: 0.3s;}
            .download-btn:hover { background: #cc0000; transform: scale(1.02); }
            optgroup { font-weight: bold; color: #999; background: #1e1e1e;}
            
            #tradingview-widget-container { display: none; height: 500px; margin-bottom: 30px; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 15px rgba(0,0,0,0.5); }
            
            .news-card { background: #1e1e1e; padding: 25px; margin-bottom: 25px; border-radius: 8px; border-left: 6px solid #6c757d; box-shadow: 0 4px 6px rgba(0,0,0,0.3);}
            .bullish { border-left-color: #28a745; }
            .little-bullish { border-left-color: #66bb6a; }
            .bearish { border-left-color: #dc3545; }
            .little-bearish { border-left-color: #e57373; }
            .neutral { border-left-color: #6c757d; }
            
            .header-row { margin-bottom: 5px;}
            a.card-title { color: #4da3ff; text-decoration: none; font-size: 1.4em; font-weight: bold; line-height: 1.3;}
            a.card-title:hover { text-decoration: underline; }
            .timestamp { color: #999; font-size: 0.85em; margin-bottom: 15px; font-style: italic;}
            .price-tracker { display: flex; gap: 15px; margin-bottom: 15px; flex-wrap: wrap;}
            .price-badge { background: #252525; padding: 15px; border-radius: 6px; font-size: 0.95em; border: 1px solid #444; width: 100%; max-width: 400px; box-shadow: 0 2px 4px rgba(0,0,0,0.2);}
            .full-text { color: #dddddd; line-height: 1.7; font-size: 1em; white-space: pre-wrap; background: #252525; padding: 15px; border-radius: 6px; max-height: 400px; overflow-y: auto;}
            .key-points { color: #dddddd; line-height: 1.7; font-size: 1em; background: #252525; padding: 15px 15px 15px 35px; border-radius: 6px; margin: 0;}
            .key-points li { margin-bottom: 15px; }
            .key-points li:nth-last-child(2) { background: #333; padding: 10px; border-radius: 5px; border-left: 3px solid #ff9800; list-style-type: none; margin-left: -20px;}
            .key-points li:last-child { color: #888; font-size: 0.85em; list-style-type: none; margin-left: -20px;}
            .tag { background: #333; padding: 4px 10px; border-radius: 4px; font-size: 0.8em; margin-right: 5px; font-weight: bold;}
            .meta { font-size: 0.85em; color: #888; margin-top: 20px; display: flex; justify-content: space-between; border-top: 1px solid #333; padding-top: 15px; align-items: center;}
            .translating { opacity: 0.5; pointer-events: none; }
            ::-webkit-scrollbar { width: 8px; }
            ::-webkit-scrollbar-track { background: #1e1e1e; }
            ::-webkit-scrollbar-thumb { background: #555; border-radius: 4px; }
        </style>
    </head>
    <body>
        <h2>🔴 Live Stock Market AI Dashboard</h2>
        
        <div id="macro-banner" class="macro-banner">
            <span style="color:#888;">Fetching Global Market Health...</span>
        </div>
        
        <div class="global-controls">
            <div class="control-group">
                <label>Sector:</label>
                <select id="global-sector" class="ui-select" onchange="changeGlobalSector(this)"></select>
            </div>
            <div class="control-group">
                <label>Stock:</label>
                <select id="global-stock" class="ui-select" onchange="changeGlobalStock(this)"></select>
            </div>
            <div class="control-group">
                <label>Format:</label>
                <select id="global-style" class="ui-select" onchange="changeGlobalStyle(this)">
                    <option value="full">📖 Full Article</option>
                    <option value="bullets">🤖 AI Key Points</option>
                    <option value="bullbear">📈 5-Way Bullish/Bearish Analysis</option>
                </select>
            </div>
            <div class="control-group">
                <label>Language:</label>
                <select id="global-lang" class="ui-select" onchange="changeGlobalLang(this)"></select>
            </div>
        </div>

        <div class="report-controls">
            <label style="color:#ccc; font-weight:bold;">Generate AI Report:</label>
            <select id="report-type" class="ui-select" style="max-width: 250px;">
                <option value="detailed">1. Detailed News Report</option>
                <option value="quant">2. Numbers & Sentiment Data</option>
                <option value="simple">3. Easy To Understand (Beginner)</option>
            </select>
            <button class="download-btn" onclick="downloadReportPDF()">📄 Download PDF Report</button>
        </div>

        <div id="tradingview-widget-container"></div>

        <div id='news-feed'></div>
        
        <script>
            const articleCache = {};
            let currentGlobalStyle = 'full';
            let currentGlobalLang = 'en';
            let currentGlobalSector = 'all';
            let currentGlobalStock = 'all';
            window.globalMacroStatus = "Neutral"; 
            
            const allLanguages = { "hi": "Hindi", "hinglish": "Hinglish", "mr": "Marathi", "gu": "Gujarati", "bn": "Bengali", "te": "Telugu", "ta": "Tamil", "ur": "Urdu", "kn": "Kannada", "ml": "Malayalam", "or": "Odia", "pa": "Punjabi", "as": "Assamese", "es": "Spanish", "fr": "French", "zh-CN": "Chinese", "ar": "Arabic" };
            const allSectors = { "IT": "💻 Information Technology", "Banking": "🏦 Banking & Finance", "Energy": "⚡ Energy & Oil", "Automobile": "🚗 Automobiles", "Consumer": "🛒 Consumer & Retail", "Telecom": "📡 Telecom", "FMCG": "🧴 FMCG", "Finance": "📊 Financial Services", "Infrastructure": "🏗️ Infrastructure", "Global Impact": "🌍 Global Macro" };
            const allStocks = { "RELIANCE": "Reliance Ind.", "TCS": "Tata Consultancy Services", "HDFC": "HDFC Bank", "INFY": "Infosys", "REGULATORY": "RBI / SEBI", "TATA": "Tata Motors", "WIPRO": "Wipro", "ZOMATO": "Zomato", "SBI": "State Bank of India", "ICICI": "ICICI Bank", "MARUTI": "Maruti Suzuki", "BHARTIARTL": "Bharti Airtel", "ITC": "ITC Limited", "ADANI": "Adani Group", "GLOBAL_MACRO": "Global Economy" };
            const stockToSector = { "RELIANCE": "Energy", "TCS": "IT", "HDFC": "Banking", "INFY": "IT", "REGULATORY": "Finance", "TATA": "Automobile", "WIPRO": "IT", "ZOMATO": "Consumer", "SBI": "Banking", "ICICI": "Banking", "MARUTI": "Automobile", "BHARTIARTL": "Telecom", "ITC": "FMCG", "ADANI": "Infrastructure", "GLOBAL_MACRO": "Global Impact" };

            const tvSymbolMap = {
                "RELIANCE": "BSE:RELIANCE", "TCS": "BSE:TCS", "HDFC": "BSE:HDFCBANK",
                "INFY": "BSE:INFY", "TATA": "BSE:TATAMOTORS", "WIPRO": "BSE:WIPRO",
                "ZOMATO": "BSE:ZOMATO", "SBI": "BSE:SBIN", "ICICI": "BSE:ICICIBANK",
                "MARUTI": "BSE:MARUTI", "BHARTIARTL": "BSE:BHARTIARTL", "ITC": "BSE:ITC",
                "ADANI": "BSE:ADANIENT", "GLOBAL_MACRO": "TVC:DXY"
            };

            let recentLangs = JSON.parse(localStorage.getItem('recentLangs')) || [];
            let recentSectors = JSON.parse(localStorage.getItem('recentSectors')) || [];
            let recentStocks = JSON.parse(localStorage.getItem('recentStocks')) || [];

            function updateRecent(storageKey, listArr, code) {
                if (code === 'en' || code === 'all') return listArr; 
                let newArr = listArr.filter(l => l !== code);
                newArr.unshift(code);
                if (newArr.length > 3) newArr.pop();
                localStorage.setItem(storageKey, JSON.stringify(newArr));
                return newArr;
            }

            function generateLangOptions() {
                let html = `<option value="en">🌐 English (Default)</option>`;
                if (recentLangs.length > 0) {
                    html += `<optgroup label="🕒 Recently Used">`;
                    recentLangs.forEach(c => { if(allLanguages[c]) html += `<option value="${c}">${allLanguages[c]}</option>`; });
                    html += `</optgroup>`;
                }
                html += `<optgroup label="🌐 All Languages">`;
                for (const [code, name] of Object.entries(allLanguages)) html += `<option value="${code}">${name}</option>`;
                html += `</optgroup>`;
                return html;
            }

            function generateSectorOptions() {
                let html = `<option value="all">📊 All Sectors</option>`;
                if (recentSectors.length > 0) {
                    html += `<optgroup label="🕒 Recently Used">`;
                    recentSectors.forEach(c => { if(allSectors[c]) html += `<option value="${c}">${allSectors[c]}</option>`; });
                    html += `</optgroup>`;
                }
                html += `<optgroup label="🏢 All Sectors">`;
                for (const [code, name] of Object.entries(allSectors)) html += `<option value="${code}">${name}</option>`;
                html += `</optgroup>`;
                return html;
            }
            
            function generateStockOptions() {
                let html = `<option value="all">🏢 All Stocks / Macro</option>`;
                let filteredStocks = Object.keys(allStocks);
                if (currentGlobalSector !== 'all') {
                    filteredStocks = filteredStocks.filter(k => stockToSector[k] === currentGlobalSector);
                }
                if (recentStocks.length > 0) {
                    let validRecents = recentStocks.filter(k => filteredStocks.includes(k));
                    if (validRecents.length > 0) {
                        html += `<optgroup label="🕒 Recently Used">`;
                        validRecents.forEach(c => { html += `<option value="${c}">${allStocks[c]}</option>`; });
                        html += `</optgroup>`;
                    }
                }
                html += `<optgroup label="📈 Available Tracking">`;
                filteredStocks.forEach(code => { html += `<option value="${code}">${allStocks[code]}</option>`; });
                html += `</optgroup>`;
                return html;
            }

            document.getElementById('global-lang').innerHTML = generateLangOptions();
            document.getElementById('global-sector').innerHTML = generateSectorOptions();
            document.getElementById('global-stock').innerHTML = generateStockOptions();

            function loadTradingViewChart(stockCode) {
                const container = document.getElementById('tradingview-widget-container');
                if (stockCode === 'all' || stockCode === 'REGULATORY' || !tvSymbolMap[stockCode]) {
                    container.style.display = 'none';
                    container.innerHTML = ''; 
                    return;
                }
                
                container.style.display = 'block';
                container.innerHTML = ''; 
                
                new TradingView.widget({
                    "autosize": true,
                    "symbol": tvSymbolMap[stockCode],
                    "interval": "D",
                    "timezone": "Asia/Kolkata",
                    "theme": "dark",
                    "style": "1",
                    "locale": "en",
                    "enable_publishing": false,
                    "backgroundColor": "#1e1e1e",
                    "gridColor": "#333333",
                    "hide_top_toolbar": false,
                    "hide_legend": false,
                    "save_image": false,
                    "container_id": "tradingview-widget-container"
                });
            }

            function changeGlobalLang(selectElem) {
                currentGlobalLang = selectElem.value;
                recentLangs = updateRecent('recentLangs', recentLangs, currentGlobalLang);
                selectElem.innerHTML = generateLangOptions();
                selectElem.value = currentGlobalLang;
                Object.keys(articleCache).forEach(hash => updateCardDisplay(hash));
            }
            
            function changeGlobalStyle(selectElem) {
                currentGlobalStyle = selectElem.value;
                Object.keys(articleCache).forEach(hash => updateCardDisplay(hash));
            }

            function changeGlobalSector(selectElem) {
                currentGlobalSector = selectElem.value;
                recentSectors = updateRecent('recentSectors', recentSectors, currentGlobalSector);
                selectElem.innerHTML = generateSectorOptions();
                selectElem.value = currentGlobalSector;
                
                if (currentGlobalSector !== 'all' && currentGlobalStock !== 'all') {
                    if (stockToSector[currentGlobalStock] !== currentGlobalSector) currentGlobalStock = 'all'; 
                }
                let stockElem = document.getElementById('global-stock');
                stockElem.innerHTML = generateStockOptions();
                stockElem.value = currentGlobalStock;
                filterCards();
                loadTradingViewChart(currentGlobalStock);
            }
            
            function changeGlobalStock(selectElem) {
                currentGlobalStock = selectElem.value;
                recentStocks = updateRecent('recentStocks', recentStocks, currentGlobalStock);
                selectElem.innerHTML = generateStockOptions();
                selectElem.value = currentGlobalStock;
                filterCards();
                loadTradingViewChart(currentGlobalStock); 
            }

            function filterCards() {
                Object.keys(articleCache).forEach(hash => {
                    let cardElem = document.getElementById('card-' + hash);
                    if (!cardElem) return;
                    let sectors = articleCache[hash].sectors || [];
                    let tickers = articleCache[hash].tickers || [];
                    let sectorMatch = (currentGlobalSector === 'all') || sectors.includes(currentGlobalSector);
                    let stockMatch = (currentGlobalStock === 'all') || tickers.includes(currentGlobalStock);
                    cardElem.style.display = (sectorMatch && stockMatch) ? 'block' : 'none';
                });
            }

            function formatTime(dateString) {
                if (!dateString) return "Just Now";
                let date = new Date(dateString);
                if (isNaN(date)) return dateString; 
                return date.toLocaleString('en-US', { month: 'long', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' });
            }

            function downloadReportPDF() {
                const { jsPDF } = window.jspdf;
                const doc = new jsPDF();
                
                let reportType = document.getElementById('report-type').value;
                let dateStr = new Date().toLocaleString('en-US');
                let target = currentGlobalStock !== 'all' ? allStocks[currentGlobalStock] : 
                             (currentGlobalSector !== 'all' ? allSectors[currentGlobalSector] : "Entire Market");

                let activeArticles = Object.values(articleCache).filter(art => {
                    let sMatch = (currentGlobalSector === 'all') || art.sectors.includes(currentGlobalSector);
                    let tMatch = (currentGlobalStock === 'all') || art.tickers.includes(currentGlobalStock);
                    return sMatch && tMatch;
                });

                if(activeArticles.length === 0) {
                    alert("No news available for the selected filters to generate a report.");
                    return;
                }

                let y = 15;
                const margin = 15;
                const maxWidth = 180;
                
                function addText(text, fontSize, isBold) {
                    doc.setFontSize(fontSize);
                    doc.setFont("helvetica", isBold ? "bold" : "normal");
                    let lines = doc.splitTextToSize(text, maxWidth);
                    lines.forEach(line => {
                        if (y > 280) { doc.addPage(); y = 15; }
                        doc.text(line, margin, y);
                        y += 7;
                    });
                }

                addText("AI-GENERATED STOCK MARKET REPORT", 18, true);
                y += 5;
                addText(`Target Focus : ${target}`, 12, false);
                addText(`Generated At : ${dateStr}`, 12, false);
                addText(`Data Points  : ${activeArticles.length} FinBERT Analyzed Articles`, 12, false);
                y += 10;

                if (reportType === 'detailed') {
                    addText("--- [ DETAILED NEWS TIMELINE ] ---", 14, true);
                    y += 5;
                    activeArticles.forEach(art => {
                        let cleanText = art.modes.full.replace(/<[^>]+>/g, '');
                        addText(`[${formatTime(art.published)}]`, 10, true);
                        addText(`HEADLINE: ${art.title}`, 12, true);
                        addText(`AI SENTIMENT: ${art.sentiment.toUpperCase()}`, 10, false);
                        y+=3;
                        addText(cleanText, 10, false);
                        y += 10;
                    });
                }
                else if (reportType === 'quant') {
                    let full_bullish = activeArticles.filter(a => a.sentiment === 'Bullish').length;
                    let lit_bullish = activeArticles.filter(a => a.sentiment === 'Little Bullish').length;
                    let full_bearish = activeArticles.filter(a => a.sentiment === 'Bearish').length;
                    let lit_bearish = activeArticles.filter(a => a.sentiment === 'Little Bearish').length;
                    let neutral = activeArticles.filter(a => a.sentiment === 'Neutral').length;
                    
                    let total_bull = full_bullish + lit_bullish;
                    let total_bear = full_bearish + lit_bearish;
                    
                    let dominant = "Neutral/Sideways";
                    if (total_bull > total_bear) dominant = "Bullish (Positive Momentum)";
                    if (total_bear > total_bull) dominant = "Bearish (Downward Pressure)";

                    addText("--- [ QUANTITATIVE FINBERT ANALYSIS ] ---", 14, true);
                    y += 5;
                    addText(`Overall Sector Mood : ${dominant}`, 12, true);
                    addText(`Total Bullish News  : ${full_bullish} (Strong), ${lit_bullish} (Mild)`, 12, false);
                    addText(`Total Bearish News  : ${full_bearish} (Strong), ${lit_bearish} (Mild)`, 12, false);
                    addText(`Total Neutral News  : ${neutral}`, 12, false);
                    y += 10;
                    
                    addText("--- DATA LOG ---", 14, true);
                    y += 5;
                    activeArticles.forEach(art => {
                        let sentimentPad = art.sentiment.toUpperCase().padEnd(15, ' ');
                        addText(`[${sentimentPad}] | ${formatTime(art.published)} | ${art.title}`, 10, false);
                    });
                }
                else if (reportType === 'simple') {
                    let bullish = activeArticles.filter(a => a.sentiment.includes('Bullish')).length;
                    let bearish = activeArticles.filter(a => a.sentiment.includes('Bearish')).length;
                    
                    let explanation = "";
                    if (bullish > bearish) explanation = `Right now, the news for ${target} is mostly GOOD. Investors are hearing positive things, which usually makes stock prices go up.`;
                    else if (bearish > bullish) explanation = `Right now, the news for ${target} is mostly BAD. There are challenges being reported, which can sometimes make stock prices go down.`;
                    else explanation = `Right now, the news for ${target} is MIXED. There is no clear good or bad trend today.`;

                    addText("--- [ EASY SUMMARY (FOR BEGINNERS) ] ---", 14, true);
                    y += 5;
                    addText(`What is happening with ${target}?`, 12, true);
                    addText(explanation, 12, false);
                    y += 10;
                    
                    addText("Here are the most important things that happened recently:", 12, true);
                    y += 5;
                    activeArticles.forEach((art, idx) => {
                        if (idx > 10) return; 
                        let tone = art.sentiment.includes('Bullish') ? '(This is good news)' : (art.sentiment.includes('Bearish') ? '(This is bad news)' : '(This is normal news)');
                        addText(`* ${art.title} ${tone}`, 11, false);
                    });
                    
                    y += 15;
                    addText("*Remember: This is an AI summary. Always check with a financial advisor before buying or selling stocks.*", 9, false);
                }

                doc.save(`${target.replace(/\\s/g, '_')}_FinBERT_Report.pdf`);
            }

            async function refreshPrices() {
                try {
                    let res = await fetch('/api/prices');
                    let currentPrices = await res.json();
                    
                    // --- UPDATE MACRO HEALTH BANNER ---
                    let nifty = currentPrices["NIFTY50"];
                    let banknifty = currentPrices["BANKNIFTY"];
                    let us_yield = currentPrices["US_10Y_YIELD"];
                    let dollar = currentPrices["DOLLAR_INDEX"];
                    let crude = currentPrices["CRUDE_OIL"];

                    if(nifty && banknifty) {
                        let nColor = nifty.change_pct >= 0 ? '#28a745' : '#dc3545';
                        let nArrow = nifty.change_pct >= 0 ? '▲' : '▼';
                        let bnColor = banknifty.change_pct >= 0 ? '#28a745' : '#dc3545';
                        let bnArrow = banknifty.change_pct >= 0 ? '▲' : '▼';

                        let macroStatus = "🟢 Market is Healthy (Risk ON)";
                        let statusColor = "#28a745";
                        
                        // Adding Global Stress logic (If Yield or Dollar is up, it's bad for Indian Markets)
                        let globalStress = false;
                        if(dollar && dollar.change_pct > 0.3) globalStress = true;
                        
                        if (nifty.change_pct < -0.5 || globalStress || nifty.tech_signal.includes("Sell") || nifty.tech_signal.includes("Bearish")) {
                            macroStatus = "🔴 Market is Weak (Risk OFF / Caution)";
                            statusColor = "#dc3545";
                        } else if (nifty.change_pct > -0.5 && nifty.change_pct < 0.25) {
                            macroStatus = "🟡 Market is Sideways (Neutral)";
                            statusColor = "#ffc107";
                        }

                        let globalHtml = "";
                        if(dollar && crude) {
                             globalHtml = `
                             <div class="macro-item" style="border-left: 1px solid #334155; padding-left: 20px;">
                                <span class="macro-label">Dollar Index (DXY)</span>
                                <span class="macro-value">${dollar.price} <span style="color:${dollar.change_pct > 0 ? '#dc3545' : '#28a745'}; font-size:0.8em;">${dollar.change_pct > 0 ? '▲' : '▼'} ${dollar.change_pct}%</span></span>
                             </div>
                             <div class="macro-item" style="border-left: 1px solid #334155; padding-left: 20px;">
                                <span class="macro-label">Crude Oil (WTI)</span>
                                <span class="macro-value">$${crude.price} <span style="color:${crude.change_pct > 0 ? '#dc3545' : '#28a745'}; font-size:0.8em;">${crude.change_pct > 0 ? '▲' : '▼'} ${crude.change_pct}%</span></span>
                             </div>
                             `;
                        }

                        document.getElementById('macro-banner').innerHTML = `
                            <div class="macro-item">
                                <span class="macro-label">NIFTY 50</span>
                                <span class="macro-value">${nifty.price} <span style="color:${nColor}; font-weight:bold; font-size:0.9em;">${nArrow} ${nifty.change_pct}%</span></span>
                            </div>
                            <div class="macro-item">
                                <span class="macro-label">NIFTY 50 TA</span>
                                <span class="macro-value" style="font-size:0.95em; color:#ddd;">RSI: ${nifty.rsi} | <strong style="color:${nColor};">${nifty.tech_signal}</strong></span>
                            </div>
                            <div class="macro-item" style="border-left: 1px solid #334155; padding-left: 20px;">
                                <span class="macro-label">BANK NIFTY</span>
                                <span class="macro-value">${banknifty.price} <span style="color:${bnColor}; font-weight:bold; font-size:0.9em;">${bnArrow} ${banknifty.change_pct}%</span></span>
                            </div>
                            ${globalHtml}
                            <div class="macro-item" style="border-left: 1px solid #334155; padding-left: 20px; text-align: right; flex-grow: 1;">
                                <span class="macro-label">Macro Environment</span>
                                <span class="macro-value" style="color:${statusColor}; font-weight:bold;">${macroStatus}</span>
                            </div>
                        `;
                        
                        window.globalMacroStatus = macroStatus;
                    }
                    // --- END MACRO UPDATE ---
                    
                    document.querySelectorAll('.price-tracker-data').forEach(tracker => {
                        let ticker = tracker.getAttribute('data-ticker');
                        let aiSentiment = tracker.getAttribute('data-sentiment'); 
                        let priceData = currentPrices[ticker];
                        
                        if(priceData) {
                            let mktSent = priceData.market_sentiment;
                            let color = "#6c757d"; 
                            
                            if (mktSent === "Bullish") color = "#28a745";
                            else if (mktSent === "Little Bullish") color = "#66bb6a";
                            else if (mktSent === "Bearish") color = "#dc3545";
                            else if (mktSent === "Little Bearish") color = "#e57373";

                            let arrow = priceData.change_pct > 0 ? '▲' : (priceData.change_pct < 0 ? '▼' : '■');
                            let volStr = (priceData.volume / 100000).toFixed(2);
                            
                            let aiDir = aiSentiment.includes("Bullish") ? 1 : (aiSentiment.includes("Bearish") ? -1 : 0);
                            let mktDir = mktSent.includes("Bullish") ? 1 : (mktSent.includes("Bearish") ? -1 : 0);
                            
                            let agreement = "";
                            if (aiDir === 1 && mktDir === 1) agreement = `✅ Market Agrees (${mktSent})`;
                            else if (aiDir === -1 && mktDir === -1) agreement = `✅ Market Agrees (${mktSent})`;
                            else if (aiDir === 0 && mktDir === 0) agreement = `✅ Market Agrees (${mktSent})`;
                            else if (aiDir === 0) agreement = `➖ Neutral News, Market is ${mktSent}`;
                            else if (mktDir === 0) agreement = `⏳ Market is Neutral (Awaiting Momentum)`;
                            else agreement = `⚠️ Market Disagrees (${mktSent})`;
                            
                            let techColor = "#aaa";
                            if (priceData.tech_signal.includes("Buy") || priceData.tech_signal === "Bullish Trend") techColor = "#28a745";
                            if (priceData.tech_signal.includes("Sell") || priceData.tech_signal === "Bearish Trend") techColor = "#dc3545";

                            // Inject Macro Warning if Market is Weak
                            let macroWarningHtml = "";
                            if (window.globalMacroStatus && window.globalMacroStatus.includes("Weak") && (aiDir === 1 || agreement.includes("✅") || priceData.tech_signal.includes("Buy"))) {
                                macroWarningHtml = ` <span style="color:#ff9800; font-size:0.9em; margin-left:10px;">⚠️ Caution: Macro trend is weak!</span>`;
                            }

                            tracker.innerHTML = `
                                <div style="font-size: 1.1em; color: #fff; margin-bottom: 5px;">${ticker}: ₹${priceData.price} | <span style="color:${color}; font-weight:bold;">${arrow} ${priceData.change_pct}%</span> | Vol: ${volStr}M</div>
                                <div style="font-size: 0.85em; color: #ddd; margin-bottom: 5px; border-bottom: 1px solid #444; padding-bottom: 5px;">
                                    📈 TA: RSI: <strong>${priceData.rsi}</strong> | SMA(20): ₹${priceData.sma20} | Signal: <strong style="color:${techColor};">${priceData.tech_signal}</strong>
                                </div>
                                <div style="font-size: 0.9em; margin-top: 5px; color: #aaa;">🤖 AI Alignment: <strong style="color:${color};">${agreement}</strong>${macroWarningHtml}</div>
                            `;
                        }
                    });
                } catch(e) { console.error("Price fetch failed"); }
            }
            
            setInterval(refreshPrices, 30000); 

            function getSentimentClass(sentimentStr) {
                return sentimentStr.toLowerCase().replace(' ', '-');
            }

            function addArticle(data, isLive = false) {
                articleCache[data.hash] = { 
                    title: data.title, url: data.url, sentiment: data.sentiment, published: data.published,
                    modes: data.content_modes, sectors: data.sectors, tickers: data.tickers
                };
                
                var feed = document.getElementById('news-feed');
                
                if (document.getElementById("card-" + data.hash)) return;

                var card = document.createElement('div');
                card.className = "news-card " + getSentimentClass(data.sentiment);
                card.id = "card-" + data.hash;
                card.setAttribute("data-timestamp", data.timestamp);
                
                let sectorMatch = (currentGlobalSector === 'all') || (data.sectors && data.sectors.includes(currentGlobalSector));
                let stockMatch = (currentGlobalStock === 'all') || (data.tickers && data.tickers.includes(currentGlobalStock));
                if (!(sectorMatch && stockMatch)) card.style.display = 'none';
                
                var tagsHtml = data.tickers.map(t => `<span class="tag">${t}</span>`).join('');
                var sectorHtml = data.sectors.map(s => `<span class="tag" style="background:#4da3ff; color:#000;">${s}</span>`).join('');
                if(!tagsHtml && !sectorHtml) tagsHtml = `<span class="tag">GENERAL MARKET</span>`;
                
                var displayTime = formatTime(data.published);
                
                var priceBadges = '';
                if(data.tickers && data.tickers.length > 0) {
                    let uniqueTickers = [...new Set(data.tickers)];
                    priceBadges = `<div class="price-tracker">`;
                    uniqueTickers.forEach(t => {
                        priceBadges += `<div class="price-badge price-tracker-data" data-ticker="${t}" data-sentiment="${data.sentiment}">
                                                <span style="color:#aaa;">📊 ${t}: Fetching Market Data & TA...</span>
                                        </div>`;
                    });
                    priceBadges += `</div>`;
                }
                
                let sentimentTextColor = "#007bff"; 
                if (data.sentiment === "Bullish") sentimentTextColor = "#28a745"; 
                else if (data.sentiment === "Little Bullish") sentimentTextColor = "#66bb6a"; 
                else if (data.sentiment === "Bearish") sentimentTextColor = "#dc3545"; 
                else if (data.sentiment === "Little Bearish") sentimentTextColor = "#e57373"; 

                card.innerHTML = `
                    <div class="header-row">
                        <a href="${data.url}" target="_blank" class="card-title">${data.title}</a>
                    </div>
                    <div class="timestamp">🕒 Published: ${displayTime}</div>
                    
                    ${priceBadges}
                    
                    <div id="content-${data.hash}" class="content-display">
                        <div class="full-text" style="color:#666;">Applying global settings...</div>
                    </div>
                    <div class="meta">
                        <div>${sectorHtml} ${tagsHtml}</div>
                        <div><strong>Sentiment:</strong> <span style="color: ${sentimentTextColor}; font-weight:bold;">${data.sentiment.toUpperCase()}</span></div>
                    </div>
                `;
                
                let inserted = false;
                let existingCards = Array.from(feed.children);
                for (let i = 0; i < existingCards.length; i++) {
                    let currentCardTime = parseFloat(existingCards[i].getAttribute('data-timestamp') || 0);
                    if (data.timestamp > currentCardTime) {
                        feed.insertBefore(card, existingCards[i]);
                        inserted = true;
                        break;
                    }
                }
                
                if (!inserted) {
                    feed.appendChild(card);
                }
                
                updateCardDisplay(data.hash);
            }

            async function updateCardDisplay(hash) {
                let cache = articleCache[hash];
                let cardElem = document.getElementById('card-' + hash);
                let displayElem = document.getElementById('content-' + hash);
                let titleElem = cardElem.querySelector('.card-title');

                let targetMode = currentGlobalStyle;
                let targetLang = currentGlobalLang;
                let originalContent = cache.modes[targetMode];
                let isList = (targetMode === 'bullets' || targetMode === 'bullbear');

                const render = (title, content) => {
                    titleElem.innerText = title;
                    if (isList) {
                        displayElem.innerHTML = `<ul class="key-points">${content.map(li => `<li>${li}</li>`).join('')}</ul>`;
                    } else {
                        displayElem.innerHTML = `<div class="full-text">${content}</div>`;
                    }
                };

                if (targetLang === 'en') {
                    render(cache.title, originalContent);
                    return;
                }

                cardElem.classList.add('translating');
                try {
                    let response = await fetch('/api/translate', {
                        method: 'POST', headers: {'Content-Type': 'application/json'}, 
                        body: JSON.stringify({
                            title: cache.title, target_lang: targetLang, mode: isList ? 'list' : 'text',
                            content_text: isList ? "" : originalContent, content_list: isList ? originalContent : []
                        })
                    });
                    let translatedData = await response.json();
                    render(translatedData.title, isList ? translatedData.content_list : translatedData.content_text);
                } catch (error) {
                    render(cache.title, originalContent); 
                } finally {
                    cardElem.classList.remove('translating');
                }
            }

            loadTradingViewChart(currentGlobalStock);

            fetch('/api/news/latest?limit=50')
                .then(response => response.json())
                .then(data => { 
                    data.forEach(article => addArticle(article, false)); 
                    refreshPrices(); 
                });

            var ws = new WebSocket("ws://127.0.0.1:8000/ws");
            ws.onmessage = function(event) { 
                addArticle(JSON.parse(event.data), true); 
                refreshPrices(); 
            }; 
        </script>
    </body>
</html>
"""

@app.get("/")
async def root():
    return HTMLResponse(html_dashboard)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)