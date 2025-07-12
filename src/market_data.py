from kiteconnect import KiteConnect
from datetime import datetime, timedelta
from logger import log # Import the logger

def get_live_market_data(kite: KiteConnect, instrument_token: str, exchange: str = "NSE") -> dict:
    """
    Fetches the live quote for a given instrument from the Kite API.
    """
    instrument = f"{exchange}:{instrument_token}"
    try:
        quote_data = kite.quote(instrument)
        log.debug(f"Raw API response from kite.quote(): {quote_data}")
        return quote_data.get(instrument, {})
    except Exception as e:
        log.error(f"Could not fetch live market data for {instrument}: {e}")
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
