import yfinance as yf
import pandas as pd
import numpy as np
import os
import joblib
import json
import warnings
from sklearn.ensemble import RandomForestRegressor
from datetime import datetime, timedelta

warnings.filterwarnings('ignore')

class ModelPredictor:
    def __init__(self):
        self.model_path = "nifty_predictor_model.pkl"
        self.model = RandomForestRegressor(n_estimators=250, max_depth=12, random_state=42)
        
        # --- 🚀 THE 10-PILLAR QUANT FEATURES ---
        self.features = [
            "^IXIC",      # 1. Nasdaq Cash 
            "ES=F",       # 2. S&P 500 Futures 
            "^N225",      # 3. Nikkei 225 
            "^GDAXI",     # 4. DAX 
            "DX-Y.NYB",   # 5. True Dollar Index 
            "^TNX",       # 6. US 10Y Yield 
            "CL=F",       # 7. Crude Oil 
            "GC=F",       # 8. Gold Futures 
            "INR=X",      # 9. USD/INR 
            "^INDIAVIX"   # 10. India VIX 
        ] 
        self.target = "^NSEI" # Nifty 50 Index

    def prepare_data(self, years=5):
        print(f"📥 Fetching {years} years of historical macro data for AI training...")
        try:
            all_tickers = self.features + [self.target]
            data = yf.download(all_tickers, period=f"{years}y", interval="1d", auto_adjust=True, progress=False)['Close']
            
            # 🛠️ UPDATE: Safer data preservation. Forward fill, backward fill, then dropna
            df = data.ffill().bfill().dropna().copy()

            for col in self.features:
                df[f'{col}_pct'] = df[col].pct_change() * 100
                df[f'{col}_prev'] = df[f'{col}_pct'].shift(1) 
            
            df['target_pct'] = df[self.target].pct_change() * 100
            
            final_df = df.dropna().copy()
            return final_df
        except Exception as e:
            print(f"❌ Data Fetch Error: {e}")
            return pd.DataFrame()

    def train_intelligence(self):
        df = self.prepare_data()
        
        if df.empty:
            print("❌ Training failed: No data available.")
            return

        X = df[[f'{f}_prev' for f in self.features]]
        y = df['target_pct']

        print("🧠 Training ML Algorithm on 10 Global & Domestic Pillars (% Change)...")
        self.model.fit(X, y)
        
        joblib.dump(self.model, self.model_path)
        print(f"✅ ML Core Trained & Saved as {self.model_path}")

    def run_backtest(self):
        print("📊 Running Backtest on historical macro data...")
        try:
            df = self.prepare_data(years=1) 
            if df.empty: return
            
            X = df[[f'{f}_prev' for f in self.features]]
            
            y_true_binary = (df['target_pct'] > 0).astype(int)
            y_pred = self.model.predict(X)
            y_pred_binary = (y_pred > 0).astype(int)
            
            accuracy = (y_true_binary == y_pred_binary).mean() * 100
            
            report = {
                "accuracy": f"{round(accuracy, 2)}%",
                "status": "High Confidence" if accuracy > 60 else "Moderate Confidence",
                "last_run": datetime.now().strftime("%Y-%m-%d %H:%M")
            }
            
            with open("backtest_report.json", "w") as f:
                json.dump(report, f)
            print(f"✅ Backtest Complete. Positional Direction Accuracy: {report['accuracy']}")
        except Exception as e:
            print(f"⚠️ Backtest failed: {e}")

    def _fetch_live_domestic_data(self):
        domestic_stats = {"Gold": 0.0, "USD_INR": 0.0, "India_VIX": 0.0}
        try:
            tickers = yf.Tickers("GC=F INR=X ^INDIAVIX")
            hist = tickers.history(period="5d")['Close'].ffill() 
            
            if len(hist) >= 2:
                domestic_stats["Gold"] = round(((hist['GC=F'].iloc[-1] - hist['GC=F'].iloc[-2]) / hist['GC=F'].iloc[-2]) * 100, 2)
                domestic_stats["USD_INR"] = round(((hist['INR=X'].iloc[-1] - hist['INR=X'].iloc[-2]) / hist['INR=X'].iloc[-2]) * 100, 2)
                domestic_stats["India_VIX"] = round(((hist['^INDIAVIX'].iloc[-1] - hist['^INDIAVIX'].iloc[-2]) / hist['^INDIAVIX'].iloc[-2]) * 100, 2)
        except Exception:
            pass
        return domestic_stats

    def predict_today_move(self, global_stats):
        try:
            if not os.path.exists(self.model_path) or os.path.getsize(self.model_path) == 0:
                print("⚠️ Model file missing/empty. Starting fresh training...")
                self.train_intelligence()
            self.model = joblib.load(self.model_path)
        except Exception as e:
            print(f"🔄 Model File Corrupt ({e}). Re-training fresh...")
            self.train_intelligence()
            self.model = joblib.load(self.model_path)

        try:
            domestic = self._fetch_live_domestic_data()

            input_dict = {
                f"{self.features[0]}_prev": global_stats.get('Nasdaq_Cash', 0),
                f"{self.features[1]}_prev": global_stats.get('US_Fut_SP500', 0), 
                f"{self.features[2]}_prev": global_stats.get('Nikkei_Japan', 0),
                f"{self.features[3]}_prev": global_stats.get('DAX_Cash', global_stats.get('EU_Fut_DAX', 0)),
                f"{self.features[4]}_prev": global_stats.get('Dollar_Index', 0), 
                f"{self.features[5]}_prev": global_stats.get('US_10Y_Yield', 0),
                f"{self.features[6]}_prev": global_stats.get('Crude_Oil', 0),
                f"{self.features[7]}_prev": domestic["Gold"],        
                f"{self.features[8]}_prev": domestic["USD_INR"],      
                f"{self.features[9]}_prev": domestic["India_VIX"]     
            }

            input_df = pd.DataFrame([input_dict])
            
            # 🛠️ UPDATE: CRITICAL FIX. Force exact column order required by Scikit-Learn
            required_cols = [f'{f}_prev' for f in self.features]
            input_df = input_df[required_cols]
            
            prediction = self.model.predict(input_df)
            return round(prediction[0], 2)
            
        except Exception as e:
            print(f"❌ Prediction Logic Error: {e}")
            return 0.0

if __name__ == "__main__":
    predictor = ModelPredictor()
    predictor.train_intelligence()
    predictor.run_backtest()