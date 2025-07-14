# state.py
import asyncio
import json
from contextlib import asynccontextmanager
from logger import log
import config # Import config to get file paths

# --- Application State ---
AGENT_STATE = {"is_running": True}
portfolio = {"cash": 0, "holdings": {}, "watchlist": {}}
portfolio_lock = asyncio.Lock()

# --- Caches & Cooldowns ---
historical_data_cache = {}
ltp_cache = {}
last_cache_invalidation_date = None
trade_cooldown_list = set() # Set of symbols on a temporary cooldown


# --- Portfolio Management ---

def get_portfolio_file():
    """Returns the correct portfolio file path based on the trading mode."""
    if config.LIVE_PAPER_TRADING:
        return config.PAPER_PORTFOLIO_FILE
    else:
        return config.PORTFOLIO_FILE

async def _save_portfolio_nolock(data):
    """Saves the portfolio data to its file without acquiring the lock."""
    portfolio_file = get_portfolio_file()
    try:
        # Use run_in_executor to avoid blocking the event loop with file I/O
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: json.dump(data, open(portfolio_file, 'w'), indent=4)
        )
    except Exception as e:
        log.error(f"Error saving portfolio file: {e}")

@asynccontextmanager
async def portfolio_context(portfolio_data: dict, save_after=True):
    """Context manager for safe, atomic portfolio operations."""
    async with portfolio_lock:
        try:
            yield portfolio_data
        finally:
            if save_after:
                # The portfolio_data object is modified in place, so we save it.
                await _save_portfolio_nolock(portfolio_data)