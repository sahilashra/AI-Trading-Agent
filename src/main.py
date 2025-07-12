import os
import sys
import json
from datetime import datetime, timedelta
import argparse
import asyncio
import pandas as pd
from dotenv import load_dotenv

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
from utils import retry_api_call

# --- Robust Startup Check ---
if not os.getenv("GEMINI_API_KEY"):
    log.critical("CRITICAL: GEMINI_API_KEY not found in .env file. The agent cannot start.")
    sys.exit(1)

# --- Agent State & Portfolio Initialization ---
portfolio = {"cash": config.VIRTUAL_CAPITAL, "holdings": {}, "watchlist": {}, "pending_orders": {}}
AGENT_STATE = {"is_running": True}
historical_data_cache = {}

# --- Telegram Command Handlers ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id) != config.TELEGRAM_CHAT_ID:
        return
    AGENT_STATE["is_running"] = True
    await update.message.reply_text("✅ AI Trading Agent has been started.")

async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id) != config.TELEGRAM_CHAT_ID:
        return
    AGENT_STATE["is_running"] = False
    await update.message.reply_text("🛑 AI Trading Agent has been stopped.")

@retry_api_call()
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id) != config.TELEGRAM_CHAT_ID:
        return
    kite = context.bot_data.get('kite')
    metrics = await get_portfolio_metrics(kite)
    summary = format_portfolio_summary(metrics)
    status_text = f"Agent is currently {'RUNNING' if AGENT_STATE['is_running'] else 'PAUSED'}.\n\n{summary}"
    await update.message.reply_text(status_text)

async def performance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id) != config.TELEGRAM_CHAT_ID:
        return
    log_file = config.TRADE_LOG_FILE if not config.LIVE_PAPER_TRADING else "papertrading_tradelog.csv"
    metrics = calculate_performance_metrics(log_file)
    report = format_performance_report(metrics)
    await update.message.reply_text(report)

async def trades_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id) != config.TELEGRAM_CHAT_ID:
        return
    query = "all"
    if context.args:
        query = context.args[0].lower()
    
    log_file = config.TRADE_LOG_FILE if not config.LIVE_PAPER_TRADING else "papertrading_tradelog.csv"
    df = query_trade_log(log_file, query)
    report = format_trade_log_report(df, query)
    await update.message.reply_text(report)

# --- Core Agent Functions ---
def save_portfolio(p_folio):
    file_path = config.PORTFOLIO_FILE if not config.LIVE_PAPER_TRADING else config.PAPER_PORTFOLIO_FILE
    try:
        with open(file_path, 'w') as f:
            json.dump(p_folio, f, indent=4)
        log.info(f"Portfolio saved to {file_path}")
    except Exception as e:
        log.error(f"Error saving portfolio: {e}")

def load_portfolio():
    global portfolio
    file_path = config.PORTFOLIO_FILE if not config.LIVE_PAPER_TRADING else config.PAPER_PORTFOLIO_FILE
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r') as f:
                loaded_data = json.load(f)
                portfolio["cash"] = loaded_data.get("cash", config.VIRTUAL_CAPITAL)
                portfolio["holdings"] = loaded_data.get("holdings", {})
                portfolio["watchlist"] = loaded_data.get("watchlist", {})
                portfolio["pending_orders"] = loaded_data.get("pending_orders", {}) # Add this line
            log.info(f"Portfolio loaded from {file_path}")
        except Exception as e:
            log.error(f"Error loading portfolio: {e}. Starting fresh.")
            portfolio = {"cash": config.VIRTUAL_CAPITAL, "holdings": {}, "watchlist": {}, "pending_orders": {}}
    else:
        log.info(f"No portfolio file found at {file_path}. Starting fresh.")
        portfolio = {"cash": config.VIRTUAL_CAPITAL, "holdings": {}, "watchlist": {}, "pending_orders": {}}

@retry_api_call()
async def reconcile_portfolio(kite: KiteConnect) -> str:
    log.info("--- Reconciling Portfolio ---")
    global portfolio
    try:
        broker_holdings = kite.holdings()
        margins = kite.margins()
        actual_cash = margins["equity"]["available"]["cash"]
        original_holdings = set(portfolio['holdings'].keys())
        reconciled_portfolio = {"cash": actual_cash, "holdings": {}}
        summary = []

        for item in broker_holdings:
            symbol = item['tradingsymbol']
            if symbol in portfolio['holdings']:
                reconciled_portfolio['holdings'][symbol] = portfolio['holdings'][symbol]
                if reconciled_portfolio['holdings'][symbol]['quantity'] != item['quantity']:
                    summary.append(f"~ {symbol} qty updated to {item['quantity']}")
                    reconciled_portfolio['holdings'][symbol]['quantity'] = item['quantity']
            else:
                summary.append(f"+ Added new holding: {symbol}")
                reconciled_portfolio['holdings'][symbol] = {
                    "quantity": item['quantity'],
                    "entry_price": item['average_price'],
                    "instrument_token": item['instrument_token'],
                    "stop_loss": item['average_price'] * (1 - (config.RISK_PER_TRADE_PERCENTAGE / 100) * config.ATR_MULTIPLIER),
                    "take_profit": item['average_price'] * (1 + (config.TAKEPROFIT_ATR_MULTIPLIER * 0.02)), # Fallback
                    "peak_price": item['average_price']
                }
        
        removed_symbols = original_holdings - set(reconciled_portfolio['holdings'].keys())
        for symbol in removed_symbols:
            summary.append(f"- Removed sold holding: {symbol}")

        portfolio = reconciled_portfolio
        save_portfolio(portfolio)
        return "✅ Reconciliation Complete:\n" + ("\n".join(f"- {s}" for s in summary) if summary else "- No changes detected.")
    except Exception as e:
        log.error(f"Could not reconcile portfolio: {e}.")
        raise

@retry_api_call()
async def get_portfolio_metrics(kite: KiteConnect) -> dict:
    global portfolio
    holdings_value = 0
    
    if portfolio["holdings"]:
        instrument_lookups = [f"NSE:{pos['instrument_token']}" for pos in portfolio["holdings"].values()]
        try:
            ltp_data = kite.ltp(instrument_lookups)
            for symbol, position in portfolio["holdings"].items():
                instrument = f"NSE:{position['instrument_token']}"
                last_price = ltp_data.get(instrument, {}).get('last_price', position['entry_price'])
                holdings_value += last_price * position['quantity']
        except Exception as e:
            log.error(f"Could not fetch LTP for portfolio metrics: {e}.")
            # In case of API failure, use the last known entry price
            for position in portfolio["holdings"].values():
                 holdings_value += position['entry_price'] * position['quantity']
            raise

    available_cash = portfolio.get('cash', 0)
    total_value = available_cash + holdings_value
    
    return {
        "total_value": total_value,
        "holdings_value": holdings_value,
        "available_cash": available_cash
    }

def format_portfolio_summary(metrics: dict) -> str:
    watchlist_summary = "\n".join([f"  - {s} (Confirm > ₹{d['confirmation_price']:.2f})" for s, d in portfolio.get('watchlist', {}).items()])
    pending_orders_summary = "\n".join([f"  - {d['action']} {d['symbol']} ({d['quantity']} units)" for o, d in portfolio.get('pending_orders', {}).items()])
    return (
        f"--- Portfolio Summary ---\n"
        f"💰 Total Value: ₹{metrics['total_value']:,.2f}\n"
        f"💵 Available Cash: ₹{metrics['available_cash']:,.2f}\n"
        f"📈 Holdings Value: ₹{metrics['holdings_value']:,.2f}\n"
        f"⏳ Pending Orders:\n" + (pending_orders_summary if pending_orders_summary else "  - None") + "\n"
        f"👀 Watchlist:\n" + (watchlist_summary if watchlist_summary else "  - None")
    )

@retry_api_call()
async def monitor_pending_orders(kite: KiteConnect):
    """
    Checks the status of pending orders and updates the portfolio accordingly.
    This function is for LIVE TRADING ONLY.
    """
    if not portfolio.get('pending_orders'):
        return

    log.info(f"--- Checking {len(portfolio['pending_orders'])} Pending Orders ---")
    for order_id, order_details in list(portfolio['pending_orders'].items()):
        try:
            order_history = kite.order_history(order_id=order_id)
            latest_status = order_history[-1]['status']

            if latest_status == 'COMPLETE':
                filled_quantity = order_history[-1]['filled_quantity']
                average_price = order_history[-1]['average_price']
                
                log.info(f"✅ Order {order_id} for {order_details['symbol']} COMPLETE.")
                await send_telegram_alert(f"✅ Order COMPLETE: {order_details['action']} {filled_quantity} of {order_details['symbol']} at avg. ₹{average_price:.2f}")

                # Update portfolio based on the completed trade
                if order_details['action'] == 'BUY':
                    if order_details['symbol'] not in portfolio['holdings']:
                         portfolio['holdings'][order_details['symbol']] = {
                            "quantity": 0, "entry_price": 0, 
                            "instrument_token": order_details['instrument_token'], "peak_price": 0
                         }
                    
                    existing_qty = portfolio['holdings'][order_details['symbol']]['quantity']
                    existing_avg = portfolio['holdings'][order_details['symbol']]['entry_price']
                    
                    total_value = (existing_qty * existing_avg) + (filled_quantity * average_price)
                    total_qty = existing_qty + filled_quantity
                    
                    new_avg_price = total_value / total_qty
                    
                    portfolio['holdings'][order_details['symbol']]['quantity'] = total_qty
                    portfolio['holdings'][order_details['symbol']]['entry_price'] = new_avg_price
                    portfolio['holdings'][order_details['symbol']]['peak_price'] = max(new_avg_price, portfolio['holdings'][order_details['symbol']]['peak_price'])
                    
                    portfolio['cash'] -= (filled_quantity * average_price)

                elif order_details['action'] == 'SELL':
                    pnl = (average_price - portfolio['holdings'][order_details['symbol']]['entry_price']) * filled_quantity
                    portfolio['cash'] += (filled_quantity * average_price)
                    portfolio['holdings'][order_details['symbol']]['quantity'] -= filled_quantity
                    
                    if portfolio['holdings'][order_details['symbol']]['quantity'] <= 0:
                        del portfolio['holdings'][order_details['symbol']]

                    with open(config.TRADE_LOG_FILE, 'a', newline='') as f:
                        f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')},{order_details['symbol']},{order_details['reason']},{filled_quantity},{average_price},{pnl:.2f}\n")

                del portfolio['pending_orders'][order_id]

            elif latest_status in ['REJECTED', 'CANCELLED']:
                log.warning(f"❌ Order {order_id} for {order_details['symbol']} {latest_status}. Reason: {order_history[-1]['status_message']}")
                await send_telegram_alert(f"❌ Order {latest_status}: {order_details['action']} {order_details['quantity']} of {order_details['symbol']}. Reason: {order_history[-1]['status_message']}")
                del portfolio['pending_orders'][order_id]

            else:
                log.info(f"⏳ Order {order_id} for {order_details['symbol']} is still {latest_status}.")

        except Exception as e:
            log.error(f"Could not check status for order {order_id}: {e}")
            raise
    
    save_portfolio(portfolio)


async def get_cached_historical_data(kite: KiteConnect, instrument_token: int, from_date: datetime.date, to_date: datetime.date, interval: str) -> list:
    """
    A wrapper for kite.historical_data that uses a local cache to avoid repeated API calls.
    """
    global historical_data_cache
    cache_key = f"{instrument_token}:{from_date}:{to_date}:{interval}"
    
    if cache_key in historical_data_cache:
        cached_entry = historical_data_cache[cache_key]
        if (datetime.now() - cached_entry['timestamp']).total_seconds() < config.CACHE_EXPIRY_SECONDS:
            log.debug(f"CACHE HIT for {cache_key}")
            return cached_entry['data']

    log.debug(f"CACHE MISS for {cache_key}")
    try:
        records = kite.historical_data(instrument_token, from_date, to_date, interval)
        historical_data_cache[cache_key] = {
            "timestamp": datetime.now(),
            "data": records
        }
        return records
    except Exception as e:
        log.error(f"Could not fetch historical data for token {instrument_token}: {e}")
        return []

@retry_api_call()
async def get_market_trend(kite: KiteConnect) -> str:
    try:
        to_date = datetime.now().date()
        from_date = to_date - timedelta(days=300)
        nifty_data = await get_cached_historical_data(kite, config.NIFTY_50_TOKEN, from_date, to_date, "day")
        
        if len(nifty_data) < 200:
            log.warning("Not enough Nifty 50 data to determine market trend. Defaulting to Uptrend.")
            return "Uptrend"
            
        df = pd.DataFrame(nifty_data)
        df['sma_200'] = df['close'].rolling(window=200).mean()
        
        last_close = df['close'].iloc[-1]
        last_sma = df['sma_200'].iloc[-1]
        
        if last_close > last_sma:
            return "Uptrend"
        else:
            return "Downtrend"
            
    except Exception as e:
        log.error(f"Could not determine market trend: {e}. Defaulting to Uptrend.")
        return "Uptrend"

@retry_api_call()
async def screen_for_momentum_pullbacks(kite: KiteConnect, n: int) -> list:
    """
    Scans for stocks in a strong uptrend that have recently pulled back.
    """
    log.info(f"--- Screening for Top {n} Momentum Pullback Stocks ---")
    try:
        all_instruments = kite.instruments(exchange=config.EXCHANGE)
        nse_equities = [inst for inst in all_instruments if inst['instrument_type'] == 'EQ' and inst['segment'] == 'NSE' and inst.get('name') != 'NIFTYBEES'] # Exclude NiftyBees

        candidate_stocks = []
        today = datetime.now().date()
        from_date = today - timedelta(days=365)

        for i, inst in enumerate(nse_equities):
            if i >= 200:
                break
            try:
                records = await get_cached_historical_data(kite, inst['instrument_token'], from_date, today, "day")
                if len(records) < 200:
                    continue

                df = pd.DataFrame(records)
                df['close'] = pd.to_numeric(df['close'])
                
                df['sma_50'] = df['close'].rolling(window=50).mean()
                df['sma_200'] = df['close'].rolling(window=200).mean()
                df['high_52_week'] = df['high'].rolling(window=252).max()

                last_price = df['close'].iloc[-1]
                sma_50 = df['sma_50'].iloc[-1]
                sma_200 = df['sma_200'].iloc[-1]
                high_52_week = df['high_52_week'].iloc[-1]

                is_uptrend = last_price > sma_50 and last_price > sma_200 and sma_50 > sma_200
                is_pullback = last_price < high_52_week * 0.95 and last_price > high_52_week * 0.75

                if is_uptrend and is_pullback:
                    distance_from_high = (high_52_week - last_price) / high_52_week
                    candidate_stocks.append({
                        "symbol": inst['tradingsymbol'],
                        "instrument_token": inst['instrument_token'],
                        "score": distance_from_high
                    })
                    log.info(f"Found candidate: {inst['tradingsymbol']} (Pullback: {distance_from_high:.2%})")

            except Exception as e:
                log.warning(f"Could not process {inst['tradingsymbol']} for screening: {e}")
                continue
        
        sorted_candidates = sorted(candidate_stocks, key=lambda x: x['score'])
        top_stocks = sorted_candidates[:n]
        
        log.info(f"Found {len(top_stocks)} potential new stocks to analyze.")
        return top_stocks

    except Exception as e:
        log.error(f"Error screening for momentum pullback stocks: {e}")
        return []

def create_trading_prompt(market_data: dict, news_headlines: list, indicators: dict, current_trading_symbol: str) -> str:
    """
    Creates a specialized prompt for the Gemini model, focusing on a momentum pullback strategy.
    """
    prompt = f"""
    Act as a seasoned technical analyst and swing trader. Your sole focus is on the 'Momentum Pullback' strategy.
    You will be given data for a stock that is already in a confirmed long-term uptrend but has recently pulled back from its peak.
    Your task is to determine if this is an optimal entry point ('BUY'), if it's better to wait ('HOLD'), or if the pullback is a sign of a larger reversal ('SELL').

    **Strategy Context:**
    - **Market Trend:** The overall market is in an Uptrend.
    - **Stock Status:** The stock is in a long-term uptrend (Price > 50 SMA > 200 SMA) and has pulled back from its 52-week high.

    **Analyze the following data for {current_trading_symbol}:**

    **1. Current Price Action:**
    - Last Price: {market_data.get('last_price')}
    - Today's Open: {market_data.get('ohlc', {}).get('open')}
    - Today's High: {market_data.get('ohlc', {}).get('high')}
    - Today's Low: {market_data.get('ohlc', {}).get('low')}

    **2. Key Technical Indicators:**
    - **RSI (14):** {indicators.get('rsi_14', 'N/A')} (Is it oversold, neutral, or overbought? Pullbacks to the 40-50 range are often ideal entry points).
    - **MACD Line:** {indicators.get('macd_line', 'N/A')}
    - **MACD Signal:** {indicators.get('macd_signal', 'N/A')} (Is there a bullish crossover, or is it trending down?)
    - **50-Day SMA:** {indicators.get('sma_50', 'N/A')} (Is the price finding support near this key moving average?)
    - **Bollinger Band Upper:** {indicators.get('bb_upper', 'N/A')}
    - **Bollinger Band Lower:** {indicators.get('bb_lower', 'N/A')} (Is the price near the lower band, suggesting it's oversold in the short term?)
    - **ATR (14):** {indicators.get('atr_14', 'N/A')} (This indicates volatility and helps in setting a stop-loss).

    **3. Recent News Headlines (Sentiment Analysis):**
    - {news_headlines if news_headlines else "No recent news."}
    (Is the news positive, negative, or neutral? Does it support a continued uptrend?)

    **Your Decision:**
    Based on a holistic analysis of the data, decide if this pullback offers a high-probability entry point.
    - **BUY:** If you see strong signs of the pullback ending (e.g., price bouncing off a key SMA, bullish divergence on RSI/MACD, stabilizing price action).
    - **HOLD:** If the pullback seems to be continuing or if indicators are neutral/conflicting. It's better to wait for a clearer signal.
    - **SELL:** If you see signs that this is not a minor pullback but a potential trend reversal (e.g., price breaking below the 50-day SMA with high volume, negative news, bearish MACD cross).

    Your final response MUST be a single word: BUY, SELL, or HOLD.
    """
    return prompt

async def analyze_and_trade_stock(kite: KiteConnect, symbol: str, token: int, is_holding: bool, total_portfolio_value: float):
    global portfolio
    log.info(f"--- Analyzing {'Holding' if is_holding else 'Opportunity'}: {symbol} ---")
    try:
        to_date = datetime.now().date()
        from_date = to_date - timedelta(days=365) # Use 1 year of data for better analysis
        historical_data = await get_cached_historical_data(kite, token, from_date, to_date, "day")
        if not historical_data:
            log.error(f"No historical data for {symbol}.")
            return
        
        indicators = calculate_indicators(historical_data)
        latest_candle = historical_data[-1]
        market_data = {"last_price": latest_candle["close"], "ohlc": latest_candle}
        current_price = market_data["last_price"]

        # --- SELL LOGIC (FOR HOLDINGS ONLY) ---
        if is_holding:
            position = portfolio["holdings"][symbol]
            exit_reason = None
            
            # RSI based take profit
            if indicators.get('rsi_14', 50) > 75:
                exit_reason = "SELL_RSI_TP"
                await send_telegram_alert(f"🟢 TAKE-PROFIT (RSI) HIT for {symbol} at {current_price:.2f}")
            
            # Trailing Stop Loss
            elif config.USE_TRAILING_STOP_LOSS:
                if current_price > position.get('peak_price', position['entry_price']):
                    position['peak_price'] = current_price
                
                trailing_stop = position['peak_price'] * (1 - config.TRAILING_STOP_LOSS_PERCENTAGE / 100)
                if trailing_stop > position['stop_loss']:
                    position['stop_loss'] = trailing_stop
                    await send_telegram_alert(f"📈 Trailing SL for {symbol} moved up to {trailing_stop:.2f}")

            # Stop Loss and Fixed Take Profit
            if not exit_reason and current_price <= position["stop_loss"]:
                exit_reason = "SELL_SL"
                await send_telegram_alert(f"🔴 STOP-LOSS HIT for {symbol} at {position['stop_loss']:.2f}")
            elif not exit_reason and current_price >= position["take_profit"]:
                exit_reason = "SELL_TP"
                await send_telegram_alert(f"🟢 TAKE-PROFIT (Fixed) HIT for {symbol} at {position['take_profit']:.2f}")

            # AI-driven sell
            if not exit_reason:
                news_headlines = get_financial_news(query=symbol)
                prompt = create_trading_prompt(market_data, news_headlines, indicators, symbol)
                decision = analysis.get_market_analysis(prompt)
                await send_telegram_alert(f"💡 Gemini's Decision for {symbol}: {decision}")
                if decision == "SELL":
                    exit_reason = "SELL_AI"

            if exit_reason:
                order_id = await place_market_order(kite, symbol, "SELL", position['quantity'])
                if order_id:
                    portfolio['pending_orders'][order_id] = {
                        "symbol": symbol, "action": "SELL", "quantity": position['quantity'], 
                        "reason": exit_reason, "placed_at": datetime.now().isoformat()
                    }
                    save_portfolio(portfolio)
                    await send_telegram_alert(f"⌛ SELL order for {position['quantity']} of {symbol} placed. Awaiting confirmation.")
                return # Stop further analysis for this stock

        # --- BUY LOGIC (FOR OPPORTUNITIES ONLY) ---
        if not is_holding:
            news_headlines = get_financial_news(query=symbol)
            prompt = create_trading_prompt(market_data, news_headlines, indicators, symbol)
            decision = analysis.get_market_analysis(prompt)
            await send_telegram_alert(f"💡 Gemini's Decision for {symbol}: {decision}")

            if decision == "BUY":
                confirmation_price = market_data["ohlc"]["high"]
                portfolio["watchlist"][symbol] = {
                    "instrument_token": token,
                    "confirmation_price": confirmation_price,
                    "added_date": datetime.now().strftime('%Y-%m-%d')
                }
                save_portfolio(portfolio)
                await send_telegram_alert(f"➕ {symbol} added to watchlist. Will buy if price moves above {confirmation_price:.2f}.")

    except Exception as e:
        log.error(f"Error analyzing {symbol}: {e}")
        await send_telegram_alert(f"🔥 ERROR analyzing {symbol}: {e}")

async def is_trade_safe(symbol: str, trade_value: float, total_portfolio_value: float) -> bool:
    """
    Performs pre-trade risk checks.
    """
    # 1. Check for sufficient cash
    if portfolio['cash'] < trade_value:
        log.warning(f"TRADE REJECTED: Insufficient cash for {symbol}. Needed: {trade_value:.2f}, Available: {portfolio['cash']:.2f}")
        await send_telegram_alert(f"⚠️ Trade REJECTED: Insufficient cash for {symbol}.")
        return False

    # 2. Check if the position size exceeds the maximum allowed percentage of the portfolio
    max_position_value = total_portfolio_value * (config.MAX_POSITION_PERCENTAGE / 100)
    if trade_value > max_position_value:
        log.warning(f"TRADE REJECTED: Position size for {symbol} ({trade_value:.2f}) exceeds the maximum allowed of {config.MAX_POSITION_PERCENTAGE}% of the portfolio ({max_position_value:.2f}).")
        await send_telegram_alert(f"⚠️ Trade REJECTED: Position size for {symbol} is too large.")
        return False
        
    return True

@retry_api_call()
async def manage_watchlist(kite: KiteConnect, total_portfolio_value: float):
    global portfolio
    today = datetime.now().date()
    
    for symbol, item in list(portfolio.get("watchlist", {}).items()):
        added_date = datetime.strptime(item['added_date'], '%Y-%m-%d').date()
        if (today - added_date).days > config.WATCHLIST_EXPIRY_DAYS:
            log.info(f"{symbol} expired from watchlist.")
            await send_telegram_alert(f"➖ {symbol} expired from watchlist.")
            del portfolio["watchlist"][symbol]
            continue

        try:
            ltp_data = kite.ltp(f"NSE:{item['instrument_token']}")
            current_price = ltp_data[f"NSE:{item['instrument_token']}"]['last_price']
            
            if current_price > item['confirmation_price']:
                log.info(f"CONFIRMED BUY for {symbol} at {current_price:.2f}")
                
                # --- Position Sizing ---
                historical_data = await get_cached_historical_data(kite, item['instrument_token'], today - timedelta(days=90), today, "day")
                indicators = calculate_indicators(historical_data)
                atr = indicators.get('atr_14', current_price * 0.02)

                capital_at_risk = total_portfolio_value * (config.RISK_PER_TRADE_PERCENTAGE / 100)
                stop_loss_price = current_price - (atr * config.ATR_MULTIPLIER)
                risk_per_share = current_price - stop_loss_price
                
                if risk_per_share <= 0:
                    log.warning(f"Risk per share for {symbol} is zero or negative. Skipping trade.")
                    del portfolio["watchlist"][symbol]
                    continue

                trade_quantity = int(capital_at_risk // risk_per_share)
                trade_value = trade_quantity * current_price

                # --- Pre-Trade Risk Checks ---
                if trade_quantity > 0 and await is_trade_safe(symbol, trade_value, total_portfolio_value):
                    await send_telegram_alert(f"✅ Risk checks passed for {symbol}. Placing BUY order.")
                    
                    order_id = await place_market_order(kite, symbol, "BUY", trade_quantity)
                    
                    if order_id:
                        # Add to pending orders instead of directly to holdings
                        portfolio['pending_orders'][order_id] = {
                            "symbol": symbol, "action": "BUY", "quantity": trade_quantity,
                            "instrument_token": item['instrument_token'], "placed_at": datetime.now().isoformat()
                        }
                        del portfolio["watchlist"][symbol] # Remove from watchlist once order is placed
                        save_portfolio(portfolio)
                        await send_telegram_alert(f"⌛ BUY order for {trade_quantity} of {symbol} placed. Awaiting confirmation.")
                    else:
                        # Handle immediate order placement failure
                        log.critical(f"CRITICAL: Market order placement failed for {symbol}. The API did not return an order_id.")
                        await send_telegram_alert(f"🔥 CRITICAL: Order placement for {symbol} FAILED. Check logs.")

        except Exception as e:
            log.error(f"Error processing watchlist for {symbol}: {e}")
            raise

def is_market_open():
    """
    Checks if the market is open based on time and weekday.
    """
    now = datetime.now()
    is_weekday = now.weekday() < 5  # Monday to Friday
    is_market_time = config.MARKET_OPEN <= now.time() <= config.MARKET_CLOSE
    # TODO: Add a check for market holidays
    return is_weekday and is_market_time

async def trading_loop(kite: KiteConnect):
    log.info("Trading loop started.")
    while True:
        if not AGENT_STATE["is_running"]:
            await asyncio.sleep(5)
            continue

        if not is_market_open():
            log.info(f"Market is closed. Waiting for {config.CHECK_INTERVAL_SECONDS} seconds...")
            await asyncio.sleep(config.CHECK_INTERVAL_SECONDS)
            continue
        
        # --- Live Trading Order Monitoring ---
        if not config.LIVE_PAPER_TRADING:
            await monitor_pending_orders(kite)

        await send_telegram_alert("--- New Trading Cycle ---")
        
        market_trend = await get_market_trend(kite)
        await send_telegram_alert(f"Market Trend: {market_trend} {'📈' if market_trend == 'Uptrend' else '📉'}")
        
        portfolio_metrics = await get_portfolio_metrics(kite)
        total_portfolio_value = portfolio_metrics['total_value']

        if portfolio["holdings"]:
            await send_telegram_alert("Phase 1: Managing existing portfolio...")
            for symbol, position in list(portfolio["holdings"].items()):
                await analyze_and_trade_stock(kite, symbol, position['instrument_token'], True, total_portfolio_value)
        
        if portfolio["watchlist"]:
            await send_telegram_alert("Phase 2: Managing watchlist...")
            await manage_watchlist(kite, total_portfolio_value)

        if market_trend == "Uptrend":
            await send_telegram_alert("Phase 3: Scanning for new opportunities...")
            scan_list = await screen_for_momentum_pullbacks(kite, n=config.TOP_N_STOCKS)
            if scan_list:
                for stock in scan_list:
                    if stock["symbol"] not in portfolio["holdings"] and stock["symbol"] not in portfolio["watchlist"]:
                        await analyze_and_trade_stock(kite, stock["symbol"], stock["instrument_token"], False, total_portfolio_value)
        else:
            await send_telegram_alert("Market is in a downtrend. New purchases are disabled.")

        final_metrics = await get_portfolio_metrics(kite)
        summary = format_portfolio_summary(final_metrics)
        await send_telegram_alert(summary)
        await send_telegram_alert(f"Cycle finished. Waiting for {config.CHECK_INTERVAL_SECONDS // 60} minutes...")
        await asyncio.sleep(config.CHECK_INTERVAL_SECONDS)

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
        # Initialize the Gemini model immediately after verifying the key
        analysis.initialize_gemini(gemini_api_key)
    except Exception as e:
        log.critical(f"Failed to initialize Gemini. Please check your API key. Error: {e}")
        sys.exit(1)

    try:
        kite = KiteConnect(api_key=config.API_KEY)
        kite.set_access_token(config.ACCESS_TOKEN)
        kite.profile()
    except Exception as e:
        log.critical(f"Kite connection failed: {e}")
        sys.exit(1)

    if args.backtest:
        backtest_config = {
            "BACKTEST_START_DATE": config.BACKTEST_START_DATE,
            "BACKTEST_END_DATE": config.BACKTEST_END_DATE,
            "COMMISSION_PER_TRADE": config.COMMISSION_PER_TRADE,
            "SLIPPAGE_PERCENTAGE": config.SLIPPAGE_PERCENTAGE,
            "TOP_N_STOCKS": config.TOP_N_STOCKS
        }
        portfolio_sim = {"cash": config.VIRTUAL_CAPITAL, "holdings": {}, "trade_log": []}
        
        log.info("Fetching historical data for backtest...")
        all_instruments = kite.instruments(exchange=config.EXCHANGE)
        symbol_to_token_map = {inst['tradingsymbol']: inst['instrument_token'] for inst in all_instruments}
        
        historical_data_map = {}
        for symbol in config.BACKTEST_STOCKS:
            try:
                token = symbol_to_token_map.get(symbol)
                if not token:
                    log.warning(f"Could not find token for {symbol}. Skipping.")
                    continue
                
                records = kite.historical_data(token, config.BACKTEST_START_DATE, config.BACKTEST_END_DATE, "day")
                historical_data_map[symbol] = records
                log.info(f"Fetched {len(records)} days of data for {symbol}.")
            except Exception as e:
                log.error(f"Could not fetch historical data for {symbol} in backtest setup: {e}")

        equity_curve, trade_log = run_dynamic_backtest(kite, backtest_config, portfolio_sim, historical_data_map)
        performance_metrics = calculate_backtest_performance(equity_curve, trade_log)
        
        if performance_metrics:
            plot_performance(performance_metrics)
            report = format_backtest_report(performance_metrics)
            print(report)
        else:
            print("Backtest completed with no trades or results to analyze.")
        return

    # --- Live Mode Setup ---
    mode = "PAPER TRADING" if config.LIVE_PAPER_TRADING else "LIVE TRADING"
    log.info(f"--- Starting in {mode} mode ---")
    
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        log.critical("Telegram Bot Token or Chat ID not found.")
        sys.exit(1)
        
    application = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
    application.bot_data['kite'] = kite
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("stop", stop_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("performance", performance_command))
    application.add_handler(CommandHandler("trades", trades_command))
    
    public_url = None
    try:
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
        sys.exit(1)

    # Reconcile portfolio from broker at startup
    startup_message = f"--- 🚀 AI Trading Agent ONLINE ({mode}) ---\n"
    reconciliation_summary = await reconcile_portfolio(kite)
    startup_message += f"\n{reconciliation_summary}\n"
    
    # Add portfolio summary to startup message
    portfolio_metrics = await get_portfolio_metrics(kite)
    summary = format_portfolio_summary(portfolio_metrics)
    startup_message += f"\n{summary}\n"

    market_status = "OPEN" if is_market_open() else f"CLOSED (Opens at {config.MARKET_OPEN.strftime('%H:%M')} on weekdays)"
    startup_message += f"\n📊 Market Status: {market_status}\n👂 Listening at: {public_url}"
    await send_telegram_alert(startup_message)
    
    try:
        await trading_loop(kite)
    finally:
        log.info("Shutting down agent...")
        await application.updater.stop()
        await application.stop()
        if public_url:
            ngrok.disconnect(public_url)
            log.info(f"ngrok tunnel {public_url} disconnected.")
        await send_telegram_alert(f"--- 😴 AI Trading Agent OFFLINE ({mode}) ---")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Agent shut down by user.")
    except Exception as e:
        log.critical(f"Failed to start the agent: {e}")