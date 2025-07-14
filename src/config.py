# --- AI Trading Agent Configuration ---
import os
from datetime import datetime, time as dt_time

# --- DEPLOYMENT & MODE ---
# Set to True to run in live paper trading mode (uses live data, simulates trades)
# Set to False for live trading with real money
LIVE_PAPER_TRADING = True

# --- PATHS ---
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORTFOLIO_FILE = os.path.join(PROJECT_ROOT, 'src', 'portfolio.json')
PAPER_PORTFOLIO_FILE = os.path.join(PROJECT_ROOT, 'src', 'papertrading_portfolio.json')
TRADE_LOG_FILE = os.path.join(PROJECT_ROOT, 'src', 'tradelog.csv')

# --- API & BOT CREDENTIALS (from .env file) ---
API_KEY = os.getenv("KITE_API_KEY")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
NGROK_AUTH_TOKEN = os.getenv("NGROK_AUTH_TOKEN")

# --- TRADING STRATEGY PARAMETERS ---
EXCHANGE = "NSE"
RISK_PER_TRADE_PERCENTAGE = 2.5
ATR_MULTIPLIER = 2.0
TAKEPROFIT_ATR_MULTIPLIER = 3.0

# --- DYNAMIC SCREENING ---
# Set to True to use the dynamic screener, False to use the static BACKTEST_STOCKS list
DYNAMIC_SCREENING = True
SCREENER_INDEX = "NIFTY100" # Options: "NIFTY100" or "BACKTEST"
MIN_PRICE = 100 # Minimum price of stock to consider for trading
MIN_AVG_VOLUME = 100000 # Minimum 20-day average volume

# --- STATIC STOCK LIST (used if DYNAMIC_SCREENING is False) ---
TOP_N_STOCKS = 20
BACKTEST_STOCKS = [
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "HINDUNILVR", "ITC", 
    "SBIN", "BHARTIARTL", "LICI", "HCLTECH", "KOTAKBANK", "LT", "BAJFINANCE", 
    "AXISBANK", "MARUTI", "ASIANPAINT", "SUNPHARMA", "TITAN", "WIPRO", 
    "NESTLEIND", "ULTRACEMCO", "ONGC", "NTPC", "JSWSTEEL", "TATAMOTORS", 
    "ADANIENT", "M&M", "POWERGRID", "COALINDIA", "BAJAJFINSV", "INDUSINDBK", 
    "HINDALCO", "TECHM", "GRASIM", "DRREDDY", "ADANIPORTS", "TATASTEEL", 
    "CIPLA", "SBILIFE", "EICHERMOT", "BPCL", "DIVISLAB", "HEROMOTOCO", 
    "BRITANNIA", "APOLLOHOSP", "SHREECEM", "UPL", "BAJAJ-AUTO"
]

# --- MARKET & TIMING ---
MARKET_OPEN = dt_time(9, 15)
MARKET_CLOSE = dt_time(15, 30)
CHECK_INTERVAL_SECONDS = 60 * 5
NIFTY_50_TOKEN = 256265

# --- RISK & PORTFOLIO MANAGEMENT ---
VIRTUAL_CAPITAL = 100000
MAX_POSITION_PERCENTAGE = 10.0 # Max % of total portfolio value a single position can occupy
MAX_CAPITAL_PER_TRADE_PERCENTAGE = 8.0 # Max % of total portfolio value to be used in a single new trade
USE_TRAILING_STOP_LOSS = True
TRAILING_STOP_LOSS_PERCENTAGE = 5.0
MIN_HOLDING_DAYS = 3 # Minimum number of days to hold a stock before selling
WATCHLIST_EXPIRY_DAYS = 3

# --- BACKTESTING CONFIGURATION ---
# BACKTEST_STOCKS list is now defined above
BACKTEST_START_DATE = datetime(2023, 1, 1)
BACKTEST_END_DATE = datetime(2023, 12, 31)
COMMISSION_PER_TRADE = 0.0003
SLIPPAGE_PERCENTAGE = 0.0002

# --- TELEGRAM & NGROK ---
WEBHOOK_PORT = 8080

# --- PERFORMANCE & OPTIMIZATION ---
CACHE_EXPIRY_SECONDS = 3600 # 1 hour

# --- CONFIGURATION VALIDATION ---
def validate_config():
    """
    Validates that all essential configuration variables are set.
    Raises ValueError if a required variable is missing.
    """
    required_vars = [
        "API_KEY", "ACCESS_TOKEN", "TELEGRAM_BOT_TOKEN", 
        "TELEGRAM_CHAT_ID", "NGROK_AUTH_TOKEN"
    ]
    
    missing_vars = [var for var in required_vars if not globals().get(var)]
    
    if missing_vars:
        raise ValueError(f"Missing required configuration variables: {', '.join(missing_vars)}. Please set them in your .env file.")

# --- Run validation on import ---
try:
    validate_config()
except ValueError as e:
    # Use a simple print here because the logger might not be initialized yet
    print(f"CRITICAL CONFIGURATION ERROR: {e}")
    import sys
    sys.exit(1)
