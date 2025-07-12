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
RISK_PER_TRADE_PERCENTAGE = 1.0
ATR_MULTIPLIER = 2.0
TAKEPROFIT_ATR_MULTIPLIER = 3.0
TOP_N_STOCKS = 20

# --- MARKET & TIMING ---
MARKET_OPEN = dt_time(9, 15)
MARKET_CLOSE = dt_time(15, 30)
CHECK_INTERVAL_SECONDS = 60 * 5
NIFTY_50_TOKEN = 256265

# --- RISK & PORTFOLIO MANAGEMENT ---
VIRTUAL_CAPITAL = 100000
USE_TRAILING_STOP_LOSS = True
TRAILING_STOP_LOSS_PERCENTAGE = 5.0
WATCHLIST_EXPIRY_DAYS = 3
MAX_POSITION_PERCENTAGE = 25.0 # Do not allow a single stock to be more than this % of the portfolio

# --- BACKTESTING CONFIGURATION ---
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
BACKTEST_START_DATE = datetime(2023, 1, 1)
BACKTEST_END_DATE = datetime(2023, 12, 31)
COMMISSION_PER_TRADE = 0.0003
SLIPPAGE_PERCENTAGE = 0.0002

# --- TELEGRAM & NGROK ---
WEBHOOK_PORT = 8080

# --- PERFORMANCE & OPTIMIZATION ---
CACHE_EXPIRY_SECONDS = 3600 # 1 hour
