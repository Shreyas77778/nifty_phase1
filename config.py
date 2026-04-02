import pytz

# Timezone
IST = pytz.timezone('Asia/Kolkata')

# Tokens
NIFTY_TOKEN = "99926000"

# 💰 THE MASTER FUND CONFIGURATION
PAPER_CAPITAL = 100000  
ALLOCATION_PER_TRADE = 1.0  
MAX_CONCURRENT_TRADES = int(1 / ALLOCATION_PER_TRADE) 

# ⏰ INTRADAY TIME RULES
STRATEGY_START_TIME = "09:20" # Pehle 5 min volatility avoid karne ke liye
NO_NEW_TRADE_TIME = "15:00"   # 3 PM ke baad koi naya order nahi
INTRADAY_EXIT_TIME = "15:15"  # Saari positions square-off

# 🛡️ INTRADAY RISK PARAMS (Tightened)
INTRADAY_TARGET_PCT = 8   # 0.8% Target per trade
INTRADAY_SL_PCT = 5       # 0.5% Hard Stop Loss
INTRADAY_TRAILING_SL_PCT = 3 # 0.3% Trailing