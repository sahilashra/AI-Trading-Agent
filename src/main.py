import os
import sys
import json
from datetime import datetime, timedelta
import argparse
import asyncio
import time
import pandas as pd
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor

# --- Load .env first ---
dotenv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
load_dotenv(dotenv_path=dotenv_path)

# --- Now load other modules ---
from kiteconnect import KiteConnect
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from pyngrok import ngrok
import config
from logger import log
from alerter import send_telegram_alert
from performance import calculate_performance_metrics, format_performance_report, query_trade_log, format_trade_log_report
import analysis
from trade_executor import place_market_order, place_paper_order
from news_fetcher import get_financial_news
from technical_analysis import calculate_indicators
from backtest import run_dynamic_backtest, calculate_backtest_performance, format_backtest_report, plot_performance
from utils import retry_api_call, AsyncKiteClient
from errors import CriticalTradingError, MinorTradingError, DataValidationError
from validators import validate_portfolio_data
from health_check import health_check

import pytz

from contextlib import asynccontextmanager

from contextlib import asynccontextmanager
from state import (
    AGENT_STATE, portfolio, portfolio_lock, 
    historical_data_cache, ltp_cache, last_cache_invalidation_date
)

@asynccontextmanager
async def portfolio_context(save_after=True):
    """Context manager for safe, atomic portfolio operations."""
    async with portfolio_lock:
        try:
            yield portfolio
        finally:
            if save_after:
                await _save_portfolio_nolock(portfolio)


# --- Mock/Placeholder Functions (to be implemented properly) ---

def is_market_open():
    """
    Checks if the market is open, considering IST timezone and weekdays.
    """
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)
    
    # Check if it's a weekday (Monday=0, Sunday=6)
    if now.weekday() >= 5:
        return False
        
    # Check market hours
    market_open_time = config.MARKET_OPEN
    market_close_time = config.MARKET_CLOSE
    
    return market_open_time <= now.time() <= market_close_time

async def _save_portfolio_nolock(data):
    """Saves the portfolio data to its file without acquiring the lock."""
    try:
        # Use run_in_executor to avoid blocking the event loop with file I/O
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: json.dump(data, open(config.PORTFOLIO_FILE, 'w'), indent=4)
        )
    except Exception as e:
        log.error(f"Error saving portfolio file: {e}")


async def save_portfolio(data):
    """Saves the portfolio to a JSON file, ensuring thread safety with a lock."""
    async with portfolio_lock:
        await _save_portfolio_nolock(data)

async def load_portfolio():
    """Loads and validates the portfolio from a JSON file."""
    global portfolio
    try:
        with open(config.PORTFOLIO_FILE, 'r') as f:
            data = json.load(f)
        
        # --- Gracefully handle missing watchlist for backward compatibility ---
        if 'watchlist' not in data:
            log.warning("Portfolio file is missing 'watchlist'. Adding a default empty one.")
            data['watchlist'] = {}

        # Validate the loaded data
        validated_portfolio = validate_portfolio_data(data)
        portfolio = validated_portfolio.dict() # Use the validated and parsed data
        
        log.info(f"Portfolio loaded and validated from {config.PORTFOLIO_FILE}")

    except FileNotFoundError:
        log.warning(f"Portfolio file not found. Starting with an empty portfolio.")
        portfolio = {"cash": config.VIRTUAL_CAPITAL, "holdings": {}, "watchlist": {}}
        await save_portfolio(portfolio)
    except (DataValidationError, json.JSONDecodeError) as e:
        log.critical(f"Portfolio file is corrupted or invalid: {e}")
        # This is a critical error, the agent cannot run without a valid portfolio
        raise CriticalTradingError(f"Could not load a valid portfolio: {e}")
    except Exception as e:
        log.critical(f"An unexpected error occurred while loading the portfolio: {e}")
        raise CriticalTradingError(f"Failed to load portfolio: {e}")

def format_portfolio_summary(metrics: dict) -> str:
    return (
        f"--- Portfolio Summary ---\n"
        f"Total Value:    ₹{metrics.get('total_value', 0):,.2f}\n"
        f"Holdings Value: ₹{metrics.get('holdings_value', 0):,.2f}\n"
        f"Available Cash: ₹{metrics.get('available_cash', 0):,.2f}"
    )

async def get_market_trend(kite: "AsyncKiteClient", from_date=None, to_date=None) -> str:
    """
    Determines the market trend based on NIFTY 50's moving average.
    """
    try:
        if from_date is None:
            from_date = datetime.now() - timedelta(days=90)
        if to_date is None:
            to_date = datetime.now()

        log.info("Fetching NIFTY 50 historical data...")
        nifty_data = await kite.historical_data(config.NIFTY_50_TOKEN, from_date, to_date, "day")
        
        if not nifty_data:
            log.warning("Could not fetch NIFTY 50 data. Defaulting to 'Uptrend'.")
            return "Uptrend"

        df = pd.DataFrame(nifty_data)
        df['50_sma'] = df['close'].rolling(window=50).mean()
        
        last_close = df['close'].iloc[-1]
        last_sma = df['50_sma'].iloc[-1]

        if last_close > last_sma:
            return "Uptrend"
        else:
            return "Downtrend"
            
    except Exception as e:
        log.error(f"Error getting market trend: {e}")
        raise MinorTradingError(f"Could not determine market trend: {e}")

async def monitor_pending_orders(kite: "AsyncKiteClient"):
    """
    Monitors pending orders and handles them (e.g., cancels if not filled).
    For paper trading, this is less critical as we assume instant fills.
    """
    try:
        log.info("--- Monitoring Pending Orders ---")
        if config.LIVE_PAPER_TRADING:
            log.info("Paper trading mode: No pending orders to monitor.")
            return

        pending_orders = await kite.orders()
        
        for order in pending_orders:
            if order['status'] == 'OPEN':
                log.info(f"Pending order found: {order['tradingsymbol']} {order['transaction_type']} {order['quantity']} @ {order['price']}")
                # --- Add logic here to handle pending orders, e.g., cancel after a timeout ---

    except Exception as e:
        log.error(f"Error in monitor_pending_orders: {e}")

async def analyze_and_trade_stock(kite: "AsyncKiteClient", symbol: str, instrument_token: int, is_existing_holding: bool, total_portfolio_value: float):
    """
    Analyzes a stock using AI and news, then decides whether to buy, sell, or hold.
    """
    try:
        log.info(f"--- Analyzing {symbol} ---")
        
        # 1. Get Historical Data & News
        from_date = datetime.now() - timedelta(days=90)
        to_date = datetime.now()
        
        historical_data = await kite.historical_data(instrument_token, from_date, to_date, "day")
        
        if not historical_data:
            log.warning(f"No historical data for {symbol}")
            return

        df = pd.DataFrame(historical_data)
        df = calculate_indicators(df)
        
        news_items = get_financial_news(symbol)
        
        # 2. Get AI Analysis
        ai_decision = await analysis.get_ai_trading_decision(df, news_items, is_existing_holding)
        
        log.info(f"AI Decision for {symbol}: {ai_decision['decision']}")
        await send_telegram_alert(f"AI ({symbol}): {ai_decision['decision']}\nReason: {ai_decision['reason']}")

        # 3. Execute Trade based on AI decision
        if config.LIVE_PAPER_TRADING:
            if ai_decision['decision'] == 'BUY':
                # --- Position Sizing ---
                cash_to_allocate = portfolio['cash'] * (config.MAX_POSITION_PERCENTAGE / 100)
                price = df['close'].iloc[-1]
                quantity = int(cash_to_allocate / price)
                
                if quantity > 0:
                    await place_paper_order(symbol, "BUY", quantity, price)
                else:
                    log.warning(f"Not enough cash to buy {symbol}")

            elif ai_decision['decision'] == 'SELL' and is_existing_holding:
                quantity = portfolio['holdings'][symbol]['quantity']
                price = df['close'].iloc[-1]
                await place_paper_order(symbol, "SELL", quantity, price)
        else:
            # --- LIVE TRADING LOGIC (not implemented) ---
            log.warning("Live trading is not yet implemented.")

    except (ConnectionError, asyncio.TimeoutError) as e:
        # Network-related errors are often transient and should be treated as minor.
        log.warning(f"Network error while analyzing {symbol}: {e}")
        raise MinorTradingError(f"Network error analyzing {symbol}: {e}")
    except Exception as e:
        log.error(f"An unexpected error occurred in analyze_and_trade_stock for {symbol}: {e}")
        # Re-raise as a minor error so the main loop can decide how to handle it.
        # This prevents a single stock from crashing the entire agent.
        raise MinorTradingError(f"Failed to analyze {symbol}: {e}")

async def manage_watchlist(kite: "AsyncKiteClient", total_portfolio_value: float):
    """
    Manages the watchlist: removes old entries and re-analyzes for opportunities.
    """
    try:
        log.info("--- Managing Watchlist ---")
        today = datetime.now().date()
        
        async with portfolio_context() as portfolio_data:
            watchlist_copy = list(portfolio_data["watchlist"].items())
            
            for symbol, item in watchlist_copy:
                # Remove if expired
                if (today - datetime.strptime(item['added_date'], '%Y-%m-%d').date()).days > config.WATCHLIST_EXPIRY_DAYS:
                    del portfolio_data["watchlist"][symbol]
                    log.info(f"Removed expired watchlist item: {symbol}")
                    continue
                
                # Re-analyze to see if it's a buy now
                log.info(f"Re-analyzing watchlist item: {symbol}")
                await analyze_and_trade_stock(
                    kite,
                    symbol,
                    item['instrument_token'],
                    is_existing_holding=False,
                    total_portfolio_value=total_portfolio_value
                )

    except Exception as e:
        log.error(f"Error in manage_watchlist: {e}")
        raise MinorTradingError(f"Watchlist management failed: {e}")

async def screen_for_momentum_pullbacks(kite: "AsyncKiteClient", n: int) -> list:
    """
    Scans for stocks exhibiting momentum with a recent pullback.
    """
    try:
        log.info(f"Screening top {n} stocks for momentum pullbacks...")
        # This is a placeholder for a more sophisticated stock screener
        # In a real scenario, you would use a service like Streak or define a
        # universe of stocks to scan. For now, we'll use a predefined list.
        
        scan_list = []
        for symbol in config.BACKTEST_STOCKS[:n]:
            try:
                # This is inefficient and should be optimized in a real system
                instrument = (await kite.instruments(exchange=config.EXCHANGE, tradingsymbol=symbol))[0]
                
                from_date = datetime.now() - timedelta(days=100)
                to_date = datetime.now()
                
                data = await kite.historical_data(instrument['instrument_token'], from_date, to_date, "day")
                
                if not data:
                    continue

                df = pd.DataFrame(data)
                df = calculate_indicators(df) # From technical_analysis.py

                # --- Basic Momentum Pullback Strategy ---
                # 1. Price is above the 50-day SMA (Uptrend)
                # 2. RSI is below 50 (Pullback)
                if df['SMA_50'].iloc[-1] < df['close'].iloc[-1] and df['RSI_14'].iloc[-1] < 50:
                    scan_list.append({
                        "symbol": symbol,
                        "instrument_token": instrument['instrument_token']
                    })
                    log.info(f"Found potential opportunity: {symbol}")

            except Exception as e:
                log.warning(f"Could not screen {symbol}: {e}")
                continue
                
        return scan_list

    except Exception as e:
        log.error(f"Error in screen_for_momentum_pullbacks: {e}")
        return []


# --- Telegram Command Handlers ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /start command."""
    AGENT_STATE["is_running"] = True
    log.info("Agent started via /start command.")
    await update.message.reply_text("✅ Agent has been started.\nTrading loop is now active.")

async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /stop command."""
    AGENT_STATE["is_running"] = False
    log.info("Agent stopped via /stop command.")
    await update.message.reply_text("🛑 Agent has been stopped.\nTrading loop is paused. Use /start to resume.")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /status command."""
    kite = context.application.bot_data['kite']
    try:
        async with portfolio_lock:
            # This might be slow, consider a cached version
            metrics = await get_portfolio_metrics(kite)
            summary = format_portfolio_summary(metrics)

        market_status_str = "OPEN" if is_market_open() else "CLOSED"
        agent_status_str = "RUNNING" if AGENT_STATE["is_running"] else "PAUSED"

        status_message = (
            f"--- Agent Status ---\n"
            f"Agent: {agent_status_str}\n"
            f"Market: {market_status_str}\n\n"
            f"{summary}"
        )
        await update.message.reply_text(status_message)
    except Exception as e:
        log.error(f"Error in /status command: {e}")
        await update.message.reply_text(f"❌ Failed to get status: {e}")

async def performance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /performance command."""
    try:
        trade_log = await query_trade_log()
        if not trade_log:
            await update.message.reply_text("No trades recorded yet.")
            return

        performance_metrics = calculate_performance_metrics(trade_log)
        report = format_performance_report(performance_metrics)
        await update.message.reply_text(report)
    except Exception as e:
        log.error(f"Error in /performance command: {e}")
        await update.message.reply_text(f"❌ Failed to get performance report: {e}")

async def trades_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /trades command."""
    try:
        trade_log = await query_trade_log(limit=10)
        if not trade_log:
            await update.message.reply_text("No recent trades found.")
            return

        report = format_trade_log_report(trade_log)
        await update.message.reply_text(report)
    except Exception as e:
        log.error(f"Error in /trades command: {e}")
        await update.message.reply_text(f"❌ Failed to get trade log: {e}")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Logs errors raised by the Telegram bot."""
    log.error(f"Exception while handling a Telegram update: {context.error}", exc_info=context.error)
    # Optionally, send a message to the user or a admin chat
    # await context.bot.send_message(chat_id=config.TELEGRAM_CHAT_ID, text=f"An error occurred: {context.error}")

async def health_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /health command."""
    kite = context.application.bot_data['kite']
    try:
        health_status = await health_check(kite)
        
        # Format the health report
        status_emoji = {
            "HEALTHY": "✅",
            "DEGRADED": "⚠️",
            "UNHEALTHY": "❌"
        }
        
        report = f"{status_emoji.get(health_status['overall'], '❓')} **System Health: {health_status['overall']}**\n\n"
        
        for check_name, check_data in health_status["checks"].items():
            status = check_data["status"]
            emoji = "✅" if status == "PASS" else "⚠️" if status == "WARN" else "❌" if status == "FAIL" else "⏭️"
            report += f"*{check_name.replace('_', ' ').title()}*: {status}\n"
            
            if "error" in check_data:
                report += f"  `Error: {check_data['error']}`\n"
            elif check_name == "api_connectivity" and "user" in check_data:
                report += f"  `User: {check_data['user']}`\n"
            elif check_name == "portfolio_file":
                report += f"  `Holdings: {check_data.get('holdings_count', 0)}, Watchlist: {check_data.get('watchlist_count', 0)}`\n"
            elif check_name == "market_data" and "nifty_price" in check_data:
                report += f"  `NIFTY: ₹{check_data['nifty_price']}`\n"
            elif check_name == "memory_usage" and "usage_percent" in check_data:
                report += f"  `Usage: {check_data['usage_percent']:.1f}%`\n"
        
        if "issues" in health_status:
            report += f"\n**Issues Found:**\n"
            for issue in health_status["issues"]:
                report += f"• {issue}\n"
        
        await update.message.reply_text(report, parse_mode='Markdown')
        
    except Exception as e:
        log.error(f"Error in /health command: {e}")
        await update.message.reply_text(f"❌ Health check failed: {e}")


# 1. Fix the reconcile_portfolio function with better error handling

@retry_api_call()
async def reconcile_portfolio(kite: "AsyncKiteClient") -> str:
    """
    Synchronizes the local portfolio with the broker's actual holdings and cash.
    This function now performs a direct, locked update to prevent data corruption.
    """
    log.info("--- Starting Portfolio Reconciliation ---")
    try:
        log.info("Fetching broker holdings...")
        broker_holdings = await asyncio.wait_for(kite.holdings(), timeout=30.0)
        log.info(f"Fetched {len(broker_holdings)} holdings from broker")
        
        log.info("Fetching margins...")
        margins = await asyncio.wait_for(kite.margins(), timeout=30.0)
        actual_cash = margins["equity"]["available"]["cash"]
        log.info(f"Available cash: ₹{actual_cash:,.2f}")
        
        summary = []
        
        async with portfolio_lock:
            # --- Direct Portfolio Update ---
            original_cash = portfolio.get('cash', 0)
            if original_cash != actual_cash:
                summary.append(f"~ Cash updated from ₹{original_cash:,.2f} to ₹{actual_cash:,.2f}")
                portfolio['cash'] = actual_cash

            original_holdings = set(portfolio['holdings'].keys())
            broker_symbols = {item['tradingsymbol'] for item in broker_holdings}

            # Remove sold holdings
            removed_symbols = original_holdings - broker_symbols
            for symbol in removed_symbols:
                summary.append(f"- Removed sold holding: {symbol}")
                del portfolio['holdings'][symbol]

            # Add/update holdings
            for item in broker_holdings:
                symbol = item['tradingsymbol']
                if symbol not in original_holdings:
                    summary.append(f"+ Added new holding: {symbol}")
                    portfolio['holdings'][symbol] = {} # Create new entry
                
                # Update details for both new and existing holdings
                updated_holding = {
                    "quantity": item['quantity'],
                    "entry_price": item['average_price'],
                    "instrument_token": item['instrument_token'],
                    "exchange": item['exchange'],
                    "product": item['product'],
                    "stop_loss": portfolio['holdings'][symbol].get('stop_loss', item['average_price'] * 0.9), # Sensible default
                    "take_profit": portfolio['holdings'][symbol].get('take_profit', item['average_price'] * 1.2), # Sensible default
                    "peak_price": portfolio['holdings'][symbol].get('peak_price', item['average_price'])
                }
                
                # Check for quantity changes on existing holdings
                if symbol in original_holdings and portfolio['holdings'][symbol].get('quantity') != item['quantity']:
                    summary.append(f"~ {symbol} qty updated to {item['quantity']}")

                portfolio['holdings'][symbol].update(updated_holding)

            await _save_portfolio_nolock(portfolio)
            log.info("Portfolio reconciliation and save completed successfully")
        
        return "✅ Reconciliation Complete:\n" + ("\n".join(f"  {s}" for s in summary) if summary else "  - No changes detected.")
    
    except asyncio.TimeoutError:
        log.error("Reconciliation timeout - API calls took too long")
        raise CriticalTradingError("Reconciliation failed due to API timeout")
    except Exception as e:
        log.error(f"Reconciliation failed: {e}")
        log.error(f"Error type: {type(e).__name__}")
        import traceback
        log.error(f"Traceback: {traceback.format_exc()}")
        raise CriticalTradingError(f"Reconciliation failed: {str(e)}")


# 2. Fix the main function with better error handling and logging
async def main():
    parser = argparse.ArgumentParser(description="AI Trading Agent")
    parser.add_argument("--backtest", help="Run in backtesting mode", action="store_true")
    args = parser.parse_args()

    log.info("--- Initializing AI Trading Agent ---")
    
    # --- API Key Validation ---
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    if not gemini_api_key:
        log.critical("CRITICAL: GEMINI_API_KEY not found. Set it in your .env file or as an environment variable.")
        sys.exit(1)
    
    try:
        log.info("Initializing Gemini model...")
        analysis.initialize_gemini(gemini_api_key)
        log.info("Gemini model initialized successfully")
    except Exception as e:
        log.critical(f"Failed to initialize Gemini. Please check your API key. Error: {e}")
        sys.exit(1)

    try:
        log.info("Connecting to Kite...")
        kite = KiteConnect(api_key=config.API_KEY)
        kite.set_access_token(config.ACCESS_TOKEN)
        
        # Use the async client for cleaner code
        async_kite = AsyncKiteClient(kite)
        
        profile = await async_kite.profile()
        log.info(f"Connected to Kite successfully. User: {profile.get('user_name', 'Unknown')}")

    except Exception as e:
        log.critical(f"Kite connection failed: {e}")
        import traceback
        log.critical(f"Traceback: {traceback.format_exc()}")
        sys.exit(1)

    if args.backtest:
        log.warning("Backtesting mode is not yet updated to use the new KiteWrapper. Please run in live/paper mode.")
        return

    # --- Live Mode Setup ---
    mode = "PAPER TRADING" if config.LIVE_PAPER_TRADING else "LIVE TRADING"
    log.info(f"--- Starting in {mode} mode ---")
    
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        log.critical("Telegram Bot Token or Chat ID not found.")
        sys.exit(1)
        
    log.info("Setting up Telegram bot...")
    application = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
    application.bot_data['kite'] = async_kite # Pass the async client
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("stop", stop_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("performance", performance_command))
    application.add_handler(CommandHandler("trades", trades_command))
    application.add_handler(CommandHandler("health", health_command))
    application.add_error_handler(error_handler)
    
    public_url = None
    try:
        log.info("Setting up ngrok tunnel...")
        if config.NGROK_AUTH_TOKEN:
            ngrok.set_auth_token(config.NGROK_AUTH_TOKEN)
        public_url = ngrok.connect(config.WEBHOOK_PORT).public_url
        log.info(f"ngrok tunnel established: {public_url}")
        
        await application.initialize()
        await application.updater.start_webhook(
            listen="0.0.0.0",
            port=config.WEBHOOK_PORT,
            url_path=config.TELEGRAM_BOT_TOKEN,
            webhook_url=f"{public_url}/{config.TELEGRAM_BOT_TOKEN}"
        )
        await application.start()
        log.info("Telegram bot started with webhook.")
        
    except Exception as e:
        log.critical(f"Failed to setup ngrok or webhook: {e}")
        import traceback
        log.critical(f"Traceback: {traceback.format_exc()}")
        sys.exit(1)

    log.info("Loading portfolio...")
    await load_portfolio()
    log.info("Portfolio loaded successfully")
    
    startup_message = f"--- 🚀 AI Trading Agent ONLINE ({mode}) ---\n"
    
    log.info("Starting portfolio reconciliation...")
    try:
        reconciliation_summary = await reconcile_portfolio(async_kite)
        log.info(f"Reconciliation completed: {reconciliation_summary}")
        startup_message += f"\n{reconciliation_summary}\n"
    except Exception as e:
        log.error(f"Reconciliation failed: {e}")
        reconciliation_summary = f"❌ Reconciliation Failed: {str(e)}"
        startup_message += f"\n{reconciliation_summary}\n"
    
    log.info("Getting portfolio metrics...")
    try:
        metrics = await get_portfolio_metrics(async_kite)
        summary = format_portfolio_summary(metrics)
        startup_message += f"\n{summary}\n"
        log.info("Portfolio metrics retrieved successfully")
    except Exception as e:
        log.error(f"Failed to get portfolio metrics: {e}")
        startup_message += f"\n❌ Failed to get portfolio metrics: {str(e)}\n"

    market_status = "OPEN" if is_market_open() else f"CLOSED (Opens at {config.MARKET_OPEN.strftime('%H:%M')} on weekdays)"
    startup_message += f"\n📊 Market Status: {market_status}\n👂 Listening at: {public_url}"
    
    log.info("Sending startup message...")
    await send_telegram_alert(startup_message)
    log.info("Startup message sent successfully")
    
    log.info("Starting trading loop...")
    try:
        await trading_loop(async_kite)
    except Exception as e:
        log.critical(f"Trading loop failed: {e}")
        import traceback
        log.critical(f"Traceback: {traceback.format_exc()}")
        await send_telegram_alert(f"🔥 CRITICAL: Trading loop failed: {str(e)}")
    finally:
        log.info("Shutting down agent...")
        try:
            await application.updater.stop()
            await application.stop()
            if public_url:
                ngrok.disconnect(public_url)
                log.info(f"ngrok tunnel {public_url} disconnected.")
            async_kite.stop_worker() # Stop the worker thread
            await send_telegram_alert(f"--- 😴 AI Trading Agent OFFLINE ({mode}) ---")
        except Exception as e:
            log.error(f"Error during shutdown: {e}")


# 3. Add better error handling to trading_loop
async def trading_loop(kite: "AsyncKiteClient"):
    """Main trading loop with improved error classification and resilience."""
    global last_cache_invalidation_date
    log.info("Trading loop started.")
    
    consecutive_errors = 0
    max_consecutive_errors = 5 # Allow 5 minor errors before a long pause
    base_error_delay = 60  # 1 minute
    
    while AGENT_STATE["is_running"]:
        try:
            today = datetime.now().date()
            if last_cache_invalidation_date != today:
                historical_data_cache.clear()
                ltp_cache.clear()  # Also clear LTP cache daily
                last_cache_invalidation_date = today
                log.info("Daily cache invalidated.")

            if not is_market_open():
                log.info(f"Market is closed. Waiting for {config.CHECK_INTERVAL_SECONDS} seconds...")
                await asyncio.sleep(config.CHECK_INTERVAL_SECONDS)
                continue
            
            log.info("--- Starting new trading cycle ---")
            
            # Reset error counter on successful cycle start
            if consecutive_errors > 0:
                log.info("Resetting consecutive error count after successful cycle start.")
                consecutive_errors = 0
            
            if not config.LIVE_PAPER_TRADING:
                log.info("Monitoring pending orders...")
                await monitor_pending_orders(kite)
                log.info("Pending orders check completed")

            await send_telegram_alert("--- 🚀 New Trading Cycle ---")
            
            log.info("Getting market trend...")
            market_trend = await get_market_trend(kite)
            log.info(f"Market trend: {market_trend}")
            await send_telegram_alert(f"📊 Market Trend: {market_trend} {'📈' if market_trend == 'Uptrend' else '📉'}")
            
            log.info("Getting portfolio metrics...")
            metrics = await get_portfolio_metrics(kite)
            total_portfolio_value = metrics['total_value']
            log.info(f"Total portfolio value: ₹{total_portfolio_value:,.2f}")

            # --- Phase 1: Manage existing holdings ---
            async with portfolio_context(save_after=False) as portfolio_data:
                holdings_copy = list(portfolio_data["holdings"].items())
            
            if holdings_copy:
                log.info(f"Phase 1: Managing {len(holdings_copy)} existing holdings...")
                await send_telegram_alert("Phase 1: Managing existing portfolio...")
                
                for symbol, position in holdings_copy:
                    try:
                        log.info(f"Analyzing holding: {symbol}")
                        await analyze_and_trade_stock(kite, symbol, position['instrument_token'], True, total_portfolio_value)
                    except MinorTradingError as e:
                        log.warning(f"Minor error analyzing holding {symbol}: {e}")
                        await send_telegram_alert(f"⚠️ Skipping {symbol}: {e}")
                        continue
                log.info("Phase 1 completed")
            
            # --- Phase 2: Manage watchlist ---
            log.info("Phase 2: Managing watchlist...")
            await manage_watchlist(kite, total_portfolio_value)
            log.info("Phase 2 completed")

            # --- Phase 3: Scan for new opportunities ---
            if market_trend == "Uptrend":
                log.info("Phase 3: Scanning for new opportunities...")
                await send_telegram_alert("Phase 3: Scanning for new opportunities...")
                try:
                    scan_list = await screen_for_momentum_pullbacks(kite, n=config.TOP_N_STOCKS)
                    log.info(f"Found {len(scan_list)} potential opportunities")
                    
                    if scan_list:
                        async with portfolio_context(save_after=False) as portfolio_data:
                            current_holdings = set(portfolio_data["holdings"].keys())
                            current_watchlist = set(portfolio_data["watchlist"].keys())
                        
                        for stock in scan_list:
                            if stock["symbol"] not in current_holdings and stock["symbol"] not in current_watchlist:
                                try:
                                    log.info(f"Analyzing opportunity: {stock['symbol']}")
                                    await analyze_and_trade_stock(kite, stock["symbol"], stock["instrument_token"], False, total_portfolio_value)
                                except MinorTradingError as e:
                                    log.warning(f"Minor error analyzing new opportunity {stock['symbol']}: {e}")
                                    continue
                except Exception as e:
                    log.error(f"Error during opportunity scanning phase: {e}")
                    await send_telegram_alert(f"❌ Opportunity scanning failed: {e}")
                log.info("Phase 3 completed")
            else:
                log.info("Market is in downtrend - skipping new opportunities")
                await send_telegram_alert("Market is in a downtrend. New purchases are disabled.")

            # --- Final Summary ---
            log.info("Getting final portfolio metrics...")
            final_metrics = await get_portfolio_metrics(kite)
            summary = format_portfolio_summary(final_metrics)
            log.info("Trading cycle completed successfully")
            log.info(summary)
            await send_telegram_alert(summary)
            
        except asyncio.CancelledError:
            log.info("Shutdown signal received. Exiting trading loop gracefully.")
            AGENT_STATE["is_running"] = False # Ensure state is set for a clean exit
            break # Exit the loop immediately
        except MinorTradingError as e:
            consecutive_errors += 1
            error_delay = min(base_error_delay * (2 ** consecutive_errors), 900)  # Cap at 15 minutes
            
            log.warning(f"Minor error #{consecutive_errors} in trading loop: {e}")
            await send_telegram_alert(f"⚠️ Minor Error #{consecutive_errors}: {e}. Retrying in {error_delay//60} minutes.")
            
            if consecutive_errors >= max_consecutive_errors:
                log.critical(f"Too many consecutive minor errors ({consecutive_errors}). Entering maintenance mode for 30 minutes.")
                await send_telegram_alert(f"🔥 Too many consecutive errors. Entering maintenance mode for 30 minutes.")
                await asyncio.sleep(1800)
                consecutive_errors = 0
            else:
                await asyncio.sleep(error_delay)
            continue
            
        except CriticalTradingError as e:
            log.critical(f"A critical, non-recoverable error occurred: {e}")
            await send_telegram_alert(f"🔥 CRITICAL ERROR: {e}. The agent is shutting down.")
            AGENT_STATE["is_running"] = False
            raise
            
        except Exception as e:
            log.critical(f"An unexpected critical error occurred in the trading loop: {e}")
            import traceback
            log.critical(f"Traceback: {traceback.format_exc()}")
            await send_telegram_alert(f"🔥 UNEXPECTED CRITICAL ERROR: {e}. The agent is shutting down.")
            AGENT_STATE["is_running"] = False
            raise

        log.info(f"Cycle finished. Waiting for {config.CHECK_INTERVAL_SECONDS // 60} minutes...")
        await asyncio.sleep(config.CHECK_INTERVAL_SECONDS)


# 4. Also add timeout to get_portfolio_metrics
@retry_api_call()
async def get_portfolio_metrics(kite: "AsyncKiteClient") -> dict:
    global portfolio, ltp_cache
    holdings_value = 0
    
    async with portfolio_lock:
        if portfolio["holdings"]:
            instrument_lookups = [f"{pos['exchange']}:{pos['instrument_token']}" for pos in portfolio["holdings"].values()]
            
            # --- LTP Cache Logic ---
            cached_ltp = {}
            instruments_to_fetch = []
            now = datetime.now()

            for inst in instrument_lookups:
                if inst in ltp_cache and (now - ltp_cache[inst]['timestamp']).total_seconds() < config.CACHE_EXPIRY_SECONDS:
                    cached_ltp[inst] = ltp_cache[inst]['price']
                else:
                    instruments_to_fetch.append(inst)
            
            if instruments_to_fetch:
                try:
                    log.info(f"Fetching LTP for {len(instruments_to_fetch)} uncached instruments...")
                    ltp_data = await asyncio.wait_for(kite.ltp(instruments_to_fetch), timeout=30.0)
                    # Update cache
                    for inst, data in ltp_data.items():
                        ltp_cache[inst] = {'price': data['last_price'], 'timestamp': now}
                    
                    # Merge fetched data with cached data
                    cached_ltp.update({inst: data['last_price'] for inst, data in ltp_data.items()})

                except asyncio.TimeoutError:
                    log.error("LTP fetch timeout - using entry prices for uncached items")
                    # This is not ideal, but we can proceed with cached values.
                except Exception as e:
                    log.error(f"Could not fetch LTP for portfolio metrics: {e}")
                    # Raise a minor error as we can still function with stale data, but it should be flagged.
                    raise MinorTradingError(f"Could not fetch LTP data: {e}")

            # Calculate holdings value using the cache
            for symbol, position in portfolio["holdings"].items():
                instrument = f"{position['exchange']}:{position['instrument_token']}"
                last_price = cached_ltp.get(instrument, position['entry_price'])
                holdings_value += last_price * position['quantity']
                log.debug(f"Holdings value for {symbol}: ₹{last_price * position['quantity']:,.2f}")

        available_cash = portfolio.get('cash', 0)
        total_value = available_cash + holdings_value
    
    return {
        "total_value": total_value,
        "holdings_value": holdings_value,
        "available_cash": available_cash
    }

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Shutdown requested by user (Ctrl+C).")
    except CriticalTradingError as e:
        log.fatal(f"A critical error forced the agent to shut down: {e}")
    except Exception as e:
        log.critical(f"An unexpected top-level error occurred: {e}")
        import traceback
        log.critical(f"Traceback: {traceback.format_exc()}")
    finally:
        log.info("Agent shutdown complete.")
