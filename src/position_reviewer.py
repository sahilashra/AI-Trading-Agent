# src/position_reviewer.py
from logger import log
import config
from datetime import datetime, timedelta, date
from technical_analysis import calculate_indicators
# from analysis import get_news_sentiment # Placeholder for future integration

def should_exit_position(symbol: str, position: dict, historical_data: list) -> (bool, str):
    """
    Reviews an open position to determine if it should be exited based on multiple criteria.
    
    Args:
        symbol (str): The stock symbol for the position.
        position (dict): The position details from the portfolio.
        historical_data (list): The historical candle data for the stock.

    Returns:
        A tuple (bool, str) indicating (should_exit, reason).
    """
    if not config.ENABLE_POSITION_REVIEW:
        return False, ""

    now_date = datetime.now().date()

    # 1. Time Stop: Exit if held for too long
    purchase_date_str = position.get('purchase_date')
    if purchase_date_str and isinstance(purchase_date_str, str):
        purchase_date = datetime.fromisoformat(purchase_date_str).date()
        holding_period = (now_date - purchase_date).days
        if holding_period > config.TIME_STOP_DAYS:
            log.warning(f"EXIT Signal for {symbol}: Time stop triggered after {holding_period} days.")
            return True, "TIME_STOP"

    # 2. Price Stagnation: Exit if price hasn't made a new high recently
    if 'peak_price' in position and purchase_date_str and isinstance(purchase_date_str, str):
        last_peak_date_str = position.get('last_peak_date', purchase_date_str)
        if last_peak_date_str and isinstance(last_peak_date_str, str):
            last_peak_date = datetime.fromisoformat(last_peak_date_str).date()
            days_since_peak = (now_date - last_peak_date).days
            if days_since_peak > config.PRICE_STAGNATION_THRESHOLD_DAYS:
                log.warning(f"EXIT Signal for {symbol}: Price stagnation for {days_since_peak} days.")
                return True, "PRICE_STAGNATION"

    # 3. Technical Reversal: Exit if technical indicators have turned bearish
    if len(historical_data) > 50: # Need enough data
        indicators = calculate_indicators(historical_data)
        # Example reversal logic: MACD crossover and RSI below 50
        if indicators.get('macd_line', 0) < indicators.get('macd_signal', 0) and indicators.get('rsi_14', 100) < 50:
            log.warning(f"EXIT Signal for {symbol}: Technicals have reversed (MACD crossover + RSI < 50).")
            return True, "TECHNICAL_REVERSAL"
            
    # 4. News Sentiment Deterioration (Placeholder)
    # In the future, you would call your news analysis module here.
    # current_sentiment = get_news_sentiment(symbol)
    # if current_sentiment < SOME_THRESHOLD:
    #     log.warning(f"EXIT Signal for {symbol}: News sentiment has deteriorated.")
    #     return True, "SENTIMENT_DETERIORATION"

    return False, ""

def update_position_peak_price(symbol: str, position: dict, current_price: float):
    """
    Updates the peak price seen for a position, used for stagnation checks.
    This should be called daily for each open position.
    """
    if current_price > position.get('peak_price', 0):
        position['peak_price'] = current_price
        position['last_peak_date'] = datetime.now().date().isoformat()
        log.info(f"New peak price for {symbol}: {current_price:.2f}")

if __name__ == '__main__':
    log.info("This module is intended to be imported, not run directly.")


async def review_open_positions(kite, portfolio):
    """
    Iterates through all open positions and reviews them for potential exit signals.
    This function is designed to be called periodically from the main trading loop.
    """
    # Local imports to prevent circular dependency
    from main import analyze_and_trade_stock
    from validators import AIDecision
    from state import portfolio_context

    log.info("--- Starting Open Position Review ---")
    
    async with portfolio_context(portfolio, save_after=True) as p_data:
        holdings_copy = list(p_data["holdings"].items())
        
        for symbol, position in holdings_copy:
            try:
                # 1. Fetch fresh data for the position
                from_date = datetime.now() - timedelta(days=config.TIME_STOP_DAYS + 5) # Fetch enough data
                to_date = datetime.now()
                hist_data = await kite.historical_data(position['instrument_token'], from_date, to_date, "day")
                
                if not hist_data:
                    log.warning(f"Could not fetch data for {symbol} during review. Skipping.")
                    continue
                
                current_price = hist_data[-1]['close']
                
                # 2. Update the peak price for stagnation tracking
                update_position_peak_price(symbol, position, current_price)
                
                # 3. Check for exit signals
                should_exit, reason = should_exit_position(symbol, position, hist_data)
                
                if should_exit:
                    log.info(f"Exit signal '{reason}' for {symbol}. Initiating sell.")
                    
                    # Create a synthetic AI decision to trigger the sell logic
                    ai_decision = AIDecision(
                        decision="SELL",
                        confidence=10,
                        reasoning=f"Position review triggered exit due to: {reason}"
                    )
                    
                    # Use the existing trade execution logic
                    # This avoids duplicating order placement and portfolio management code
                    status = await analyze_and_trade_stock(
                        kite=kite,
                        portfolio=portfolio, # Pass the main portfolio dict
                        symbol=symbol,
                        instrument_token=position['instrument_token'],
                        is_existing=True,
                        # We need to find a way to pass the decision directly
                        # For now, the logic inside analyze_and_trade_stock will handle it
                        # if we can ensure the sell decision is respected.
                        # This is a bit of a hack and could be improved.
                        # A better way would be to refactor analyze_and_trade_stock
                        # to accept an optional pre-made decision.
                    )
                    log.info(f"Sell action for {symbol} resulted in status: {status}")

            except Exception as e:
                log.error(f"Error reviewing position {symbol}: {e}", exc_info=True)
                
    log.info("--- Open Position Review Complete ---")
