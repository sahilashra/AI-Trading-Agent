# src/screener.py
from logger import log
import config
from data.nifty100 import NIFTY_100_STOCKS
import asyncio
from datetime import datetime, timedelta

async def get_dynamic_universe(kite: "AsyncKiteClient") -> list:
    """
    Gets a dynamic list of tradable instruments based on index membership and liquidity.
    Returns a list of instrument tokens.
    """
    log.info(f"Starting dynamic screening for index: {config.SCREENER_INDEX}")
    
    # For now, we use a hardcoded list. This can be expanded later.
    if config.SCREENER_INDEX == "NIFTY100":
        stock_symbols = NIFTY_100_STOCKS
    else:
        # Default to the smaller, safer list if config is wrong
        stock_symbols = config.BACKTEST_STOCKS

    log.info(f"Found {len(stock_symbols)} stocks in the base index list.")

    # Get all instruments to map symbols to tokens
    try:
        all_instruments = await kite.instruments(exchange="NSE")
        instrument_map = {item['tradingsymbol']: item for item in all_instruments if item.get('instrument_type') == 'EQ'}
    except Exception as e:
        log.error(f"Failed to fetch instruments from broker: {e}")
        return []

    # --- Liquidity & Price Filtering ---
    liquid_universe = []
    from_date = datetime.now() - timedelta(days=60)
    to_date = datetime.now()

    for symbol in stock_symbols:
        instrument = instrument_map.get(symbol)
        if not instrument:
            continue

        try:
            # Fetch historical data to check volume and price
            hist_data = await kite.historical_data(instrument['instrument_token'], from_date, to_date, "day")
            if len(hist_data) < 20: # Need at least a month of data
                continue

            # Calculate average volume and last price
            total_volume = sum(d['volume'] for d in hist_data)
            avg_volume = total_volume / len(hist_data)
            last_price = hist_data[-1]['close']

            # Apply filters from config
            if last_price >= config.MIN_PRICE and avg_volume >= config.MIN_AVG_VOLUME:
                liquid_universe.append({
                    "symbol": symbol,
                    "instrument_token": instrument['instrument_token']
                })
        except Exception as e:
            log.warning(f"Could not process {symbol} for dynamic screening: {e}")
            await asyncio.sleep(0.1) # Avoid hitting rate limits

    log.info(f"Screening complete. Found {len(liquid_universe)} liquid stocks to analyze.")
    return liquid_universe
