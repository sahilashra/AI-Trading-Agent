from kiteconnect import KiteConnect
from datetime import datetime, timedelta
from logger import log
import config

def get_live_market_data(kite: KiteConnect, instrument_token: str, exchange: str = "NSE") -> dict:
    """
    Fetches and validates the live quote for a given instrument from the Kite API.
    Includes staleness and sanity checks.
    """
    instrument = f"{exchange}:{instrument_token}"
    try:
        quote_data_full = kite.quote(instrument)
        log.debug(f"Raw API response from kite.quote(): {quote_data_full}")
        
        quote_data = quote_data_full.get(instrument)
        if not quote_data:
            log.error(f"[DATA_QUALITY_FLAG] No data returned for {instrument} in quote API call.")
            return {}

        # --- 1. Staleness Check ---
        last_trade_time = quote_data.get('timestamp')
        if last_trade_time:
            # Ensure last_trade_time is timezone-aware for correct comparison
            if last_trade_time.tzinfo is None:
                last_trade_time = last_trade_time.astimezone() # Use system's local timezone
            
            time_diff = datetime.now(last_trade_time.tzinfo) - last_trade_time
            if time_diff.total_seconds() > config.DATA_STALENESS_THRESHOLD_SECONDS:
                log.error(f"[DATA_QUALITY_FLAG] Stale data for {instrument}. Last trade was {time_diff.total_seconds():.0f}s ago. Discarding.")
                return {}

        # --- 2. Sanity Checks ---
        last_price = quote_data.get('last_price')
        prev_close = quote_data.get('ohlc', {}).get('close')

        if last_price and prev_close and prev_close > 0:
            price_change_pct = abs((last_price - prev_close) / prev_close) * 100
            if price_change_pct > config.MAX_DAY_PRICE_CHANGE_PERCENT:
                log.error(f"[DATA_QUALITY_FLAG] Unrealistic price change for {instrument}. Change: {price_change_pct:.2f}%. Discarding.")
                return {}

        # --- 3. Volume Check ---
        volume = quote_data.get('volume')
        if volume == 0:
            log.warning(f"[DATA_QUALITY_FLAG] Zero volume recorded for {instrument} today.")

        return quote_data

    except Exception as e:
        log.error(f"Could not fetch or validate live market data for {instrument}: {e}")
        return {}

def get_historical_data_for_test(kite: KiteConnect, instrument_token: str) -> dict:
    """
    Fetches the last daily candle for testing when the market is closed.
    It formats the historical data to mimic the live quote format.
    """
    try:
        # Fetch data for the last 7 days to ensure we get the last trading day
        to_date = datetime.now().date()
        from_date = to_date - timedelta(days=7)
        
        records = kite.historical_data(instrument_token, from_date, to_date, "day")
        
        if not records:
            log.error("No historical data found for the instrument.")
            return {}

        # Get the most recent candle
        last_candle = records[-1]
        
        # Normalize the historical data to look like the quote data format
        formatted_data = {
            "instrument_token": instrument_token,
            "last_price": last_candle["close"],
            "ohlc": {
                "open": last_candle["open"],
                "high": last_candle["high"],
                "low": last_candle["low"],
                "close": last_candle["close"] # In this context, it's today's close
            }
        }
        return formatted_data
    except Exception as e:
        log.error(f"Could not fetch historical market data: {e}")
        return {}


if __name__ == '__main__':
    log.info("This module is intended to be imported, not run directly.")
