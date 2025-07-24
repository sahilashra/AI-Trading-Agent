# src/screener.py
from logger import log
import config
from data.nifty100 import NIFTY_100_STOCKS
import asyncio
from datetime import datetime, timedelta

# src/screener.py
from logger import log
import config
from data.nifty100 import NIFTY_100_STOCKS
import asyncio
from datetime import datetime, timedelta
import pandas as pd
from technical_analysis import calculate_indicators

async def get_top_opportunities(kite: "AsyncKiteClient", top_n: int = 5) -> list:
    """
    Gets a dynamic list of tradable instruments, runs technical analysis,
    scores them, and returns the top N candidates.
    """
    log.info(f"Starting dynamic screening for index: {config.SCREENER_INDEX}")
    
    if config.SCREENER_INDEX == "NIFTY100":
        stock_symbols = NIFTY_100_STOCKS
    else:
        stock_symbols = config.BACKTEST_STOCKS

    log.info(f"Found {len(stock_symbols)} stocks in the base index list.")

    try:
        all_instruments = await kite.instruments(exchange="NSE")
        instrument_map = {item['tradingsymbol']: item for item in all_instruments if item.get('instrument_type') == 'EQ'}
    except Exception as e:
        log.error(f"Failed to fetch instruments from broker: {e}")
        return []

    # --- Pre-computation & Filtering ---
    candidate_stocks = []
    from_date = datetime.now() - timedelta(days=90) # Fetch enough data for indicators
    to_date = datetime.now()

    for symbol in stock_symbols:
        instrument = instrument_map.get(symbol)
        if not instrument:
            continue

        try:
            hist_data = await kite.historical_data(instrument['instrument_token'], from_date, to_date, "day")
            if len(hist_data) < 50: continue

            # Basic liquidity and price check first
            total_volume = sum(d['volume'] for d in hist_data[-20:])
            avg_volume = total_volume / 20
            last_price = hist_data[-1]['close']

            if not (last_price >= config.MIN_PRICE and avg_volume >= config.MIN_AVG_VOLUME):
                continue

            # --- Scoring Logic ---
            indicators = calculate_indicators(hist_data)
            
            # Condition 1: Price must be above the 50-day SMA (in an uptrend)
            if last_price <= indicators.sma_50:
                continue
            
            # Condition 2: RSI must be in a pullback zone (e.g., < 55)
            if indicators.rsi_14 >= 55:
                continue

            # If both conditions are met, it's a candidate.
            # We score based on how low the RSI is - a lower RSI is a better pullback.
            score = 100 - indicators.rsi_14 # Higher score for lower RSI
            
            candidate_stocks.append({
                "symbol": symbol,
                "instrument_token": instrument['instrument_token'],
                "score": score
            })
            log.info(f"Found opportunity: {symbol} (RSI: {indicators.rsi_14:.2f}, Score: {score:.2f})")

        except Exception as e:
            log.warning(f"Could not process {symbol} for dynamic screening: {e}")
            await asyncio.sleep(0.2) # Slightly longer sleep to be safe

    # --- Ranking & Selection ---
    if not candidate_stocks:
        log.info("Screening complete. No promising opportunities found.")
        return []

    # Sort candidates by score in descending order (higher score is better)
    sorted_candidates = sorted(candidate_stocks, key=lambda x: x['score'], reverse=True)
    
    top_candidates = sorted_candidates[:top_n]
    
    log.info(f"Screening complete. Found {len(candidate_stocks)} candidates. Returning top {len(top_candidates)}.")
    for cand in top_candidates:
        log.info(f"  - Top Candidate: {cand['symbol']} (Score: {cand['score']:.2f})")
        
    return top_candidates
