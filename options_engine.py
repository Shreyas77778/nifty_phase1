import datetime
import math
import os
import scipy.stats as si
from dotenv import load_dotenv

load_dotenv()

# 🚀 1. THE INSTITUTIONAL MATH ENGINE (BLACK-SCHOLES)
class BlackScholesEngine:
    def __init__(self, risk_free_rate=0.07):
        self.r = risk_free_rate 

    def calculate_d1_d2(self, S, K, T, sigma):
        T = max(T, 0.0001) 
        sigma = max(sigma, 0.0001)
        d1 = (math.log(S / K) + (self.r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        return d1, d2

    def get_delta(self, S, K, T, sigma, option_type="C"):
        if T <= 0.0001: 
            if option_type == "C": return 1.0 if S > K else 0.0
            else: return -1.0 if S < K else 0.0
        
        d1, _ = self.calculate_d1_d2(S, K, T, sigma)
        if option_type == "C":
            return round(si.norm.cdf(d1), 3)
        else:
            return round(si.norm.cdf(d1) - 1.0, 3)

# 🚀 2. THE MONEY CONTROL & EXECUTION ENGINE
class OptionsStrikeEngine:
    def __init__(self):
        print("🛡️ Money Control & Strike Engine Initialized...")
        self.strike_step = {"NIFTY": 50}
        # Nifty lot size 2026 context mein 25 ya 50 ho sakta hai. Edit here:
        self.lot_size = int(os.getenv("NIFTY_LOT_SIZE", 25)) 
        self.bs_engine = BlackScholesEngine()

    def get_days_to_expiry(self):
        """Calculates days until the next Thursday expiry."""
        today = datetime.datetime.today().weekday() 
        expiry_day = 3 # Thursday
        dte = expiry_day - today
        if dte < 0: dte += 7 
        return max(dte, 0.5) # Minimum 0.5 to avoid ZeroDivision

    def get_dynamic_risk_pct(self, conviction_score):
        """
        🛡️ Pillar 1: Conviction-Based Sizing
        Gemini ke score ke basis par risk manage karna.
        """
        if conviction_score < 60:
            return 0.0  # Zero conviction = No Trade
        elif 60 <= conviction_score < 75:
            return 0.5  # Low conviction = 0.5% risk
        elif 75 <= conviction_score < 90:
            return 1.5  # Good conviction = 1.5% risk
        else:
            return 3.0  # Ultra-High conviction (Hammer Trade) = 3% risk

    def calculate_atr_stoploss(self, spot_price, atr_value, action, multiplier=1.5):
        """
        🛡️ Pillar 2: ATR-Based Volatility Stops
        Volatility ke hisaab se SL ko breathing space dena.
        """
        if not atr_value or atr_value <= 0:
            # Fallback if ATR is missing (Default 0.8% of spot)
            atr_value = spot_price * 0.008 
            
        risk_buffer = atr_value * multiplier
        if action.upper() == "BUY":
            sl_price = spot_price - risk_buffer
        else:
            sl_price = spot_price + risk_buffer
            
        return round(sl_price, 2)

    def calculate_position_size(self, capital, conviction_score, spot_price, sl_price, delta):
        """
        🛡️ Pillar 3: Position Sizing Math
        """
        risk_pct = self.get_dynamic_risk_pct(conviction_score)
        if risk_pct == 0:
            return {"Lots_To_Buy": 0, "Risk_Amount": 0}

        max_loss_amount = capital * (risk_pct / 100)
        spot_risk_points = abs(spot_price - sl_price)
        
        # Option premium move calculation (Delta based)
        option_risk_per_qty = spot_risk_points * abs(delta)
        risk_per_lot = option_risk_per_qty * self.lot_size
        
        if risk_per_lot <= 0: return {"Lots_To_Buy": 0, "Risk_Amount": 0}
        
        number_of_lots = math.floor(max_loss_amount / risk_per_lot)
        
        return {
            "Risk_Pct_Used": risk_pct,
            "Max_Loss_Allowed": round(max_loss_amount, 2),
            "Lots_To_Buy": int(number_of_lots),
            "Total_Qty": int(number_of_lots * self.lot_size),
            "Risk_Per_Lot": round(risk_per_lot, 2)
        }

    def select_optimal_strategy(self, spot_price, action, vix, conviction, atr, capital=100000):
        """
        The Main Execution Function
        """
        dte = self.get_days_to_expiry()
        atm_strike = round(spot_price / 50) * 50
        
        # 1. Calculate Volatility SL
        sl_price = self.calculate_atr_stoploss(spot_price, atr, action)
        
        # 2. Strike Selection Logic
        option_type = "CE" if action.upper() == "BUY" else "PE"
        
        if dte <= 1: # Expiry Near
            # OTM only if high conviction, else ATM
            selected_strike = atm_strike if conviction < 85 else (atm_strike + 50 if option_type == "CE" else atm_strike - 50)
            strat = "Expiry Momentum / Hero-Zero Proxy"
        else:
            # Positional: Deep ATM or slight ITM for better delta
            selected_strike = atm_strike
            strat = "Positional Trend Follower"

        # 3. Calculate Greeks for sizing
        T_years = dte / 365.0
        sigma = vix / 100.0
        bs_type = "C" if option_type == "CE" else "P"
        delta = self.bs_engine.get_delta(spot_price, selected_strike, T_years, sigma, bs_type)

        # 4. Final Position Sizing
        sizing = self.calculate_position_size(capital, conviction, spot_price, sl_price, delta)

        return {
            "Strategy": strat,
            "Target_Strike": f"{selected_strike} {option_type}",
            "Entry_Spot": spot_price,
            "Exit_SL_Spot": sl_price,
            "Delta": delta,
            "Conviction_Score": conviction,
            "Money_Control": sizing
        }

# 🧪 TEST THE ENGINE
if __name__ == "__main__":
    engine = OptionsStrikeEngine()
    # Example: Nifty at 22500, Conviction 85%, ATR 120 points, VIX 15
    trade_plan = engine.select_optimal_strategy(
        spot_price=22500, 
        action="BUY", 
        vix=15.0, 
        conviction=88, 
        atr=120, 
        capital=200000
    )
    
    import json
    print(json.dumps(trade_plan, indent=4))