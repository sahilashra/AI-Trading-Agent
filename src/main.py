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

# --- Module Imports ---
import config
from logger import log
from alerter import send_telegram_alert
from llm_clients import FAIL_SAFE_DECISION
import analysis
from trade_executor import place_and_confirm_order, place_paper_order
from screener import get_top_opportunities
from trade_logger import trade_logger 
from technical_analysis import calculate_indicators
from utils import AsyncKiteClient, retry_api_call
from errors import CriticalTradingError, MinorTradingError, DataValidationError
from validators import AIDecision, validate_portfolio_data
from position_reviewer import review_open_positions
from state import (
    portfolio_context, AGENT_STATE, historical_data_cache, 
    ltp_cache, last_cache_invalidation_date, trade_cooldown_list
)
from kiteconnect import KiteConnect
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from pyngrok import ngrok
import pytz
import time

# --- Portfolio Management ---

def get_portfolio_file():
    return config.PAPER_PORTFOLIO_FILE if config.LIVE_PAPER_TRADING else config.PORTFOLIO_FILE

async def load_portfolio():
    """
    Loads and validates the portfolio from its JSON file.
    If the file is missing or corrupted, it creates a new one.
    """
    portfolio_file = get_portfolio_file()
    try:
        with open(portfolio_file, 'r') as f:
            data = json.load(f)

        # --- Data Sanitization ---
        # Ensure top-level keys exist
        if 'cash' not in data: data['cash'] = 0.0
        if 'holdings' not in data: data['holdings'] = {}
        if 'watchlist' not in data: data['watchlist'] = {}

        # If paper trading, ensure virtual capital is set for a fresh start
        if config.LIVE_PAPER_TRADING and not data.get("holdings") and data.get("cash", 0) == 0:
            log.info(f"Initializing paper trading portfolio with virtual capital: ₹{config.VIRTUAL_CAPITAL:,.2f}")
            data['cash'] = config.VIRTUAL_CAPITAL

        # Validate the sanitized data
        validated = validate_portfolio_data(data)
        log.info(f"Successfully loaded and validated portfolio from {portfolio_file}")
        return validated.model_dump()

    except (FileNotFoundError, json.JSONDecodeError, DataValidationError) as e:
        log.warning(f"Portfolio file at '{portfolio_file}' is missing, corrupted, or invalid ({e}). Creating a new one.")
        initial_cash = config.VIRTUAL_CAPITAL if config.LIVE_PAPER_TRADING else 0.0
        portfolio = {"cash": initial_cash, "holdings": {}, "watchlist": {}}
        try:
            with open(portfolio_file, 'w') as f:
                json.dump(portfolio, f, indent=4)
            log.info(f"Created new portfolio with cash: ₹{initial_cash:,.2f}")
            return portfolio
        except Exception as write_e:
            raise CriticalTradingError(f"Failed to create new portfolio file: {write_e}")
    except Exception as e:
        raise CriticalTradingError(f"An unexpected error occurred while loading the portfolio: {e}")

def format_cycle_summary(cycle_activity: dict, metrics: dict) -> str:
    """Formats a detailed summary of the trading cycle for a Telegram message."""
    
    summary_lines = ["--- Trading Cycle Report ---"]
    
    # Trade activity
    trades_made = cycle_activity.get("trades", [])
    if trades_made:
        summary_lines.append(f"Trades Executed: {len(trades_made)}")
        for trade in trades_made:
            summary_lines.append(f"  - {trade}")
    else:
        summary_lines.append("Trades Executed: 0")

    # Hold activity
    holds = cycle_activity.get("holds", [])
    if holds:
        summary_lines.append(f"\nHeld Positions: {len(holds)}")
        for symbol, reason in holds:
            summary_lines.append(f"  - {symbol}: {reason}")
        
    # Skipped trades
    skipped = cycle_activity.get("skipped", {})
    if skipped:
        summary_lines.append("\nSkipped Opportunities:")
        for reason, symbols in skipped.items():
            summary_lines.append(f"  - {reason}: {', '.join(symbols)}")

    # Portfolio status
    pnl_str = f"₹{metrics['unrealized_pnl']:,.2f}"
    summary_lines.append("\n--- Portfolio ---")
    summary_lines.append(f"Cash: ₹{metrics['available_cash']:,.2f}")
    summary_lines.append(f"Holdings: {metrics['holdings_count']} (Value: ₹{metrics['holdings_value']:,.2f})")
    summary_lines.append(f"Unrealized P&L: {pnl_str}")
    summary_lines.append(f"Total Value: ₹{metrics['total_value']:,.2f}")
    
    return "\n".join(summary_lines)

@retry_api_call()
async def get_portfolio_metrics(kite: "AsyncKiteClient", portfolio: dict) -> dict:
    """
    Calculates key portfolio metrics, including holdings value and unrealized P&L.
    It uses live LTP for live trading and historical close for paper trading.
    """
    holdings_value = 0.0
    unrealized_pnl = 0.0
    
    if not portfolio["holdings"]:
        # If there are no holdings, return zeroed metrics immediately
        return {
            "total_value": portfolio.get('cash', 0),
            "holdings_value": 0.0,
            "available_cash": portfolio.get('cash', 0),
            "unrealized_pnl": 0.0,
            "holdings_count": 0,
        }

    if config.LIVE_PAPER_TRADING:
        # --- Paper Trading: Use historical data for the last close price ---
        log.info("Calculating paper portfolio metrics using historical data...")
        for symbol, position in portfolio["holdings"].items():
            try:
                from_date = datetime.now() - timedelta(days=5)
                to_date = datetime.now()
                hist_data = await kite.historical_data(position['instrument_token'], from_date, to_date, "day")
                if hist_data:
                    ltp = hist_data[-1]['close']
                    holdings_value += ltp * position['quantity']
                    unrealized_pnl += (ltp - position['entry_price']) * position['quantity']
            except Exception as e:
                log.error(f"Could not fetch historical data for paper metrics on {symbol}: {e}")

    else:
        # --- Live Trading: Use live LTP ---
        instrument_lookups = [f"{pos['exchange']}:{pos['instrument_token']}" for pos in portfolio["holdings"].values() if pos.get('instrument_token')]
        if instrument_lookups:
            try:
                ltp_data = await asyncio.wait_for(kite.ltp(instrument_lookups), timeout=15.0)
                for symbol, position in portfolio["holdings"].items():
                    instrument = f"{position.get('exchange', 'NSE')}:{position['instrument_token']}"
                    if instrument in ltp_data:
                        ltp = ltp_data[instrument]['last_price']
                        holdings_value += ltp * position['quantity']
                        unrealized_pnl += (ltp - position['entry_price']) * position['quantity']
            except Exception as e:
                log.error(f"Could not fetch LTP for portfolio metrics: {e}")

    available_cash = portfolio.get('cash', 0)
    total_value = available_cash + holdings_value
    return {
        "total_value": total_value,
        "holdings_value": holdings_value,
        "available_cash": available_cash,
        "unrealized_pnl": unrealized_pnl,
        "holdings_count": len(portfolio["holdings"]),
    }


@retry_api_call()
async def reconcile_portfolio(kite: "AsyncKiteClient", portfolio: dict) -> str:
    log.info("--- Starting Portfolio Reconciliation ---")
    try:
        broker_holdings = await asyncio.wait_for(kite.holdings(), timeout=30.0)
        margins = await asyncio.wait_for(kite.margins(), timeout=30.0)
        actual_cash = margins["equity"]["available"]["live_balance"]
        summary = []
        async with portfolio_context(portfolio) as p_data:
            if p_data.get('cash', 0) != actual_cash:
                summary.append(f"~ Cash updated to ₹{actual_cash:,.2f}")
                p_data['cash'] = actual_cash
            broker_symbols = {item['tradingsymbol'] for item in broker_holdings}
            removed_symbols = set(p_data['holdings'].keys()) - broker_symbols
            for symbol in removed_symbols:
                summary.append(f"- Removed sold holding: {symbol}")
                del p_data['holdings'][symbol]
            for item in broker_holdings:
                symbol = item['tradingsymbol']
                if symbol not in p_data['holdings']:
                    summary.append(f"+ Added new holding: {symbol}")
                    p_data['holdings'][symbol] = {}
                p_data['holdings'][symbol].update({
                    "quantity": item['quantity'],
                    "entry_price": item['average_price'],
                    "instrument_token": item['instrument_token'],
                    "exchange": item['exchange'],
                    "product": item['product'],
                })
        return "✅ Reconciliation Complete:\n" + ("\n".join(f"  {s}" for s in summary) if summary else "  - No changes detected.")
    except Exception as e:
        raise CriticalTradingError(f"Reconciliation failed: {str(e)}")

# --- Core Trading Logic ---

def is_market_open():
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)
    if now.weekday() >= 5: return False
    return config.MARKET_OPEN <= now.time() <= config.MARKET_CLOSE

async def analyze_and_trade_stock(kite: AsyncKiteClient, portfolio: dict, symbol: str, instrument_token: int, is_existing: bool) -> tuple[str, str]:
    """
    Analyzes a stock and executes a trade if conditions are met.
    Returns a tuple of (status, reason).
    """
    try:
        log.info(f"Analyzing {'existing holding' if is_existing else 'opportunity'}: {symbol}")
        
        # Initialize a default analysis object. This will be overridden by TSL or AI.
        ai_analysis = FAIL_SAFE_DECISION
        tsl_triggered_sell = False

        from_date = datetime.now() - timedelta(days=90)
        to_date = datetime.now()
        historical_data = await kite.historical_data(instrument_token, from_date, to_date, "day")

        if len(historical_data) < 50:
            return "SKIPPED", "Insufficient historical data"

        indicators = calculate_indicators(historical_data)
        df = pd.DataFrame(historical_data)
        price = df['close'].iloc[-1]

        # --- Trailing Stop-Loss Check (for existing holdings only) ---
        if is_existing and config.USE_TRAILING_STOP_LOSS:
            async with portfolio_context(portfolio, save_after=True) as p_data:
                position = p_data['holdings'].get(symbol)
                if position:
                    # Check for minimum holding period before any sell action
                    purchase_date_str = position.get('purchase_date')
                    if purchase_date_str and isinstance(purchase_date_str, str):
                        purchase_date = datetime.fromisoformat(purchase_date_str).date()
                        holding_days = (datetime.now().date() - purchase_date).days
                        if holding_days < config.MIN_HOLDING_DAYS:
                            reason = f"Holding for {holding_days} days (min {config.MIN_HOLDING_DAYS})"
                            log.info(f"{reason}. Skipping sell analysis for {symbol}.")
                            return "HOLD", reason

                    if 'peak_price' not in position or position['peak_price'] is None:
                        position['peak_price'] = position.get('entry_price', price)

                    if price > position['peak_price']:
                        log.info(f"Updating peak price for {symbol} to {price:.2f}")
                        position['peak_price'] = price
                    
                    # Calculate the trailing stop-loss price using ATR
                    if not indicators.atr_14 or indicators.atr_14 <= 0:
                        log.warning(f"Cannot calculate TSL for {symbol} due to invalid ATR. Skipping TSL check.")
                        return "SKIPPED", "Invalid ATR for TSL"
                        
                    tsl_price = position['peak_price'] - (indicators.atr_14 * config.ATR_MULTIPLIER)
                    
                    # Check if the current price has breached the trailing stop
                    if price < tsl_price:
                        reason = f"Trailing stop-loss triggered at {tsl_price:.2f}"
                        log.info(f"{reason} for {symbol}")
                        ai_analysis = AIDecision(decision="SELL", confidence=10, reasoning=reason)
                        tsl_triggered_sell = True
        
        # --- AI Decision Making (only if TSL hasn't already decided to sell) ---
        if not tsl_triggered_sell:
            prompt = f"""
            Analyze the stock for a trade decision based on the provided data and strategy.
            Your response MUST be in JSON format with "decision", "confidence", and "reasoning" keys.
    
            Strategy Rules:
            1. For NEW opportunities (`is_existing` is False):
               - BUY if Price > 50-SMA AND RSI < 55. Confidence should be high (7-9).
               - Otherwise, HOLD.
            2. For EXISTING holdings (`is_existing` is True):
               - SELL if RSI > 70 AND the current price has crossed BELOW the 5-day EMA. This confirms weakness.
               - HOLD otherwise. Do not suggest buying more of an existing position.
    
            Data for {symbol}:
            - Current Price: {price:.2f}
            - 50-Day SMA: {indicators.sma_50:.2f}
            - 5-Day EMA: {indicators.ema_5:.2f}
            - RSI(14): {indicators.rsi_14:.2f}
            - Is Existing Holding: {is_existing}
            """
            
            ai_analysis = await analysis.get_market_analysis(prompt)
            log.info(f"AI Analysis for {symbol}: Decision={ai_analysis.decision}, Confidence={ai_analysis.confidence}, Reasoning='{ai_analysis.reasoning}'")
    
            if ai_analysis.confidence < 7:
                reason = f"Low AI confidence ({ai_analysis.confidence})"
                log.info(f"Skipping trade for {symbol} due to {reason}.")
                return "SKIPPED", reason
        
        # --- Trade Execution ---
        if config.LIVE_PAPER_TRADING:
            if ai_analysis.decision == 'BUY':
                async with portfolio_context(portfolio, save_after=True) as p_data:
                    cash_now = p_data['cash']
                    cash_to_allocate = cash_now * 0.10 
                    quantity = int(cash_to_allocate / price) if price > 0 else 0
                    if quantity > 0:
                        await place_paper_order(p_data, symbol, "BUY", quantity, price, instrument_token)
                        if symbol in p_data['holdings']:
                            p_data['holdings'][symbol]['peak_price'] = price
                        trade_logger.log_trade(symbol, "BUY", quantity, price, reason=ai_analysis.reasoning)
                        await send_telegram_alert(f"✅ (Paper) Bought {quantity} of {symbol}")
                        return "BOUGHT", ai_analysis.reasoning
                    else:
                        return "SKIPPED", "Insufficient cash"

            elif ai_analysis.decision == 'SELL' and is_existing:
                async with portfolio_context(portfolio, save_after=True) as p_data:
                    if symbol in p_data['holdings']:
                        quantity = p_data['holdings'][symbol]['quantity']
                        entry_price = p_data['holdings'][symbol]['entry_price']
                        pnl = (price - entry_price) * quantity
                        await place_paper_order(p_data, symbol, "SELL", quantity, price, instrument_token)
                        trade_logger.log_trade(symbol, "SELL", quantity, price, pnl=pnl, reason=ai_analysis.reasoning)
                        trade_cooldown_list.add(symbol)
                        await send_telegram_alert(f"✅ (Paper) Sold {quantity} of {symbol}. P&L: ₹{pnl:,.2f}")
                        return "SOLD", ai_analysis.reasoning
        
        else: # --- Live Trading Logic ---
            metrics = await get_portfolio_metrics(kite, portfolio)
            
            if ai_analysis.decision == 'BUY':
                if not indicators.atr_14 or indicators.atr_14 <= 0:
                    return "SKIPPED", "Invalid ATR for risk calculation"

                stop_loss_price = price - (indicators.atr_14 * config.ATR_MULTIPLIER)
                risk_per_share = price - stop_loss_price
                
                if risk_per_share <= 0:
                    return "SKIPPED", "Risk per share is zero or negative"

                risk_amount = metrics["total_value"] * (config.RISK_PER_TRADE_PERCENTAGE / 100)
                quantity_by_risk = int(risk_amount / risk_per_share)
                
                capital_per_trade = metrics["total_value"] * (config.MAX_CAPITAL_PER_TRADE_PERCENTAGE / 100)
                quantity_by_capital = int(capital_per_trade / price)
                quantity = min(quantity_by_risk, quantity_by_capital)
                trade_value = quantity * price
                
                if quantity <= 0:
                    return "SKIPPED", "Calculated quantity is 0"
                if trade_value > metrics["available_cash"]:
                    return "SKIPPED", f"Insufficient cash (needs ₹{trade_value:,.2f})"

                log.info(f"Placing BUY for {quantity} of {symbol} with SL at {stop_loss_price:.2f}")
                result = await place_and_confirm_order(kite, symbol, "BUY", quantity)
                
                if result.status in ["COMPLETE", "PARTIAL"]:
                    await reconcile_portfolio(kite, portfolio)
                    async with portfolio_context(portfolio, save_after=True) as p_data:
                        if symbol in p_data['holdings']:
                            p_data['holdings'][symbol]['peak_price'] = price
                            p_data['holdings'][symbol]['purchase_date'] = datetime.now().date().isoformat()
                    trade_logger.log_trade(symbol, "BUY", result.filled_quantity, result.average_price, reason=ai_analysis.reasoning)
                    await send_telegram_alert(f"✅ Placed BUY for {result.filled_quantity} of {symbol}. ID: {result.order_id}")
                    return "BOUGHT", ai_analysis.reasoning
                else:
                    return "FAILED", f"BUY order failed with status: {result.status}"

            elif ai_analysis.decision == 'SELL' and is_existing:
                async with portfolio_context(portfolio, save_after=False) as p_data:
                    if symbol in p_data['holdings']:
                        quantity = p_data['holdings'][symbol]['quantity']
                        entry_price = p_data['holdings'][symbol]['entry_price']
                        pnl = (price - entry_price) * quantity
                        log.info(f"Placing SELL for {quantity} of {symbol}.")
                        result = await place_and_confirm_order(kite, symbol, "SELL", quantity)
                        
                        if result.status in ["COMPLETE", "PARTIAL"]:
                            trade_logger.log_trade(symbol, "SELL", result.filled_quantity, result.average_price, pnl=pnl, reason=ai_analysis.reasoning)
                            trade_cooldown_list.add(symbol)
                            await send_telegram_alert(f"✅ Placed SELL for {result.filled_quantity} of {symbol}. P&L: ₹{pnl:,.2f}. ID: {result.order_id}")
                            await reconcile_portfolio(kite, portfolio)
                            return "SOLD", ai_analysis.reasoning
                        else:
                            return "FAILED", f"SELL order failed with status: {result.status}"
            
            return "HOLD", ai_analysis.reasoning

    except Exception as e:
        log.error(f"Error analyzing {symbol}: {e}", exc_info=True)
        return "ERROR", str(e)
    
    return "HOLD", "Default action" # Default return if no other path is taken

async def screen_for_opportunities(kite: AsyncKiteClient) -> list:
    """
    Scans for new trading opportunities using the intelligent screener.
    """
    log.info("Screening for top 5 new opportunities...")
    
    if config.DYNAMIC_SCREENING:
        # This now returns the top 5 ranked opportunities directly
        return await get_top_opportunities(kite, top_n=5)
    else:
        # Fallback for static list remains simple, but we could enhance it too.
        # For now, it will just return the list without ranking.
        all_instruments = await kite.instruments(exchange="NSE")
        instrument_map = {item['tradingsymbol']: item for item in all_instruments}
        opportunities = []
        for symbol in config.BACKTEST_STOCKS:
            if symbol in instrument_map:
                opportunities.append({
                    "symbol": symbol,
                    "instrument_token": instrument_map[symbol]['instrument_token']
                })
        return opportunities

async def trading_loop(kite: AsyncKiteClient, portfolio: dict):
    last_review_time = datetime.now() - timedelta(seconds=config.POSITION_REVIEW_INTERVAL_SECONDS) # Ensure it runs on first cycle

    while AGENT_STATE["is_running"]:
        if not is_market_open():
            log.info("Market is closed. Sleeping for 1 minute.")
            await asyncio.sleep(60)
            continue

        log.info("--- New Trading Cycle ---")
        cycle_activity = {"trades": [], "skipped": {}, "holds": []}

        # Phase 1: Active Position Review (at defined interval)
        if config.ENABLE_POSITION_REVIEW and (datetime.now() - last_review_time).total_seconds() >= config.POSITION_REVIEW_INTERVAL_SECONDS:
            await review_open_positions(kite, portfolio)
            last_review_time = datetime.now()

        # Phase 2: Manage Holdings (TSL and AI-based)
        async with portfolio_context(portfolio, save_after=False) as p_data:
            holdings_copy = list(p_data["holdings"].items())
        
        if holdings_copy:
            log.info(f"Managing {len(holdings_copy)} holdings...")
            for symbol, position in holdings_copy:
                if 'instrument_token' not in position:
                    log.warning(f"Skipping analysis for {symbol} due to missing instrument_token.")
                    continue
                
                status, reason = await analyze_and_trade_stock(kite, portfolio, symbol, position['instrument_token'], True)
                
                if status in ["BOUGHT", "SOLD"]:
                    cycle_activity["trades"].append(f"{status} {symbol}")
                elif status == "HOLD":
                    cycle_activity["holds"].append((symbol, reason))

        # Phase 3: Find & Analyze New Opportunities
        opportunities = await screen_for_opportunities(kite)
        if opportunities:
            async with portfolio_context(portfolio, save_after=False) as p_data:
                current_holdings = set(p_data["holdings"].keys())
            
            for stock in opportunities:
                if stock["symbol"] not in current_holdings and stock["symbol"] not in trade_cooldown_list:
                    status, reason = await analyze_and_trade_stock(kite, portfolio, stock["symbol"], stock["instrument_token"], False)
                    
                    if status == "SKIPPED":
                        if reason not in cycle_activity["skipped"]:
                            cycle_activity["skipped"][reason] = []
                        cycle_activity["skipped"][reason].append(stock["symbol"])
                    elif status in ["BOUGHT", "SOLD"]:
                         cycle_activity["trades"].append(f"{status} {stock['symbol']}")
                    
                    time.sleep(2) # Add a 2-second delay to respect API rate limits

        # Phase 4: Report Cycle Summary
        metrics = await get_portfolio_metrics(kite, portfolio)
        summary_message = format_cycle_summary(cycle_activity, metrics)
        log.info(summary_message)
        await send_telegram_alert(summary_message)
        
        log.info(f"--- Cycle Complete. Sleeping for {config.CHECK_INTERVAL_SECONDS} seconds. ---")
        await asyncio.sleep(config.CHECK_INTERVAL_SECONDS)

# --- Main Application ---

async def main():
    """The main entry point for the AI Trading Agent."""
    log.info("--- Initializing AI Trading Agent ---")
    
    try:
        # --- Initialization ---
        analysis.initialize_llm_client()
        kite = AsyncKiteClient(KiteConnect(api_key=config.API_KEY, access_token=config.ACCESS_TOKEN))
        await kite.profile()
        portfolio = await load_portfolio()

        # --- Telegram Setup for Alerts ---
        # We only need the bot object to send messages, not the full application
        # for the main trading loop, which simplifies shutdown.
        application = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
        
        # --- Startup Message ---
        mode = "PAPER" if config.LIVE_PAPER_TRADING else "LIVE"
        startup_message = f"--- ✅ AI Trading Agent ONLINE ({mode}) ---\n"
        if not config.LIVE_PAPER_TRADING:
            startup_message += await reconcile_portfolio(kite, portfolio)
        
        metrics = await get_portfolio_metrics(kite, portfolio)
        portfolio_summary = f"--- Portfolio ---\nCash: ₹{metrics['available_cash']:,.2f}\nHoldings: {metrics['holdings_count']}"
        startup_message += f"\n{portfolio_summary}"
        
        await send_telegram_alert(startup_message)
        
        # --- Start Trading Loop ---
        await trading_loop(kite, portfolio)

    except (CriticalTradingError, asyncio.CancelledError) as e:
        log.warning(f"Agent is shutting down. Reason: {type(e).__name__}")
    except Exception as e:
        log.critical(f"An unexpected critical error occurred in main: {e}", exc_info=True)
        await send_telegram_alert(f"🚨 CRITICAL ERROR: Agent shutting down. Reason: {e}")
    finally:
        # --- Graceful Shutdown ---
        log.info("Initiating agent shutdown...")
        # No need to stop the application object as it's not running a loop
        
        # Disconnect ngrok tunnel if it's running
        try:
            tunnels = ngrok.get_tunnels()
            if tunnels:
                log.info("Disconnecting all ngrok tunnels...")
                ngrok.disconnect()
                log.info("Ngrok tunnels disconnected.")
        except Exception as ngrok_e:
            log.error(f"Error during ngrok disconnection: {ngrok_e}")
            
        log.info("Agent shutdown complete.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Shutdown requested by user. The application will now terminate.")
    except Exception as e:
        log.critical(f"The application is terminating due to an unhandled exception: {e}", exc_info=True)
    finally:
        # Ensure ngrok is disconnected if it's running
        tunnels = ngrok.get_tunnels()
        if tunnels:
            log.info("Disconnecting all ngrok tunnels...")
            ngrok.disconnect()
            log.info("Ngrok tunnels disconnected.")
        log.info("Agent shutdown process complete.")