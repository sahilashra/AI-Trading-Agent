# state.py
import asyncio

# --- Application State ---
AGENT_STATE = {"is_running": True}
portfolio = {"cash": 0, "holdings": {}, "watchlist": {}}
portfolio_lock = asyncio.Lock()

# --- Caches ---
historical_data_cache = {}
ltp_cache = {}
last_cache_invalidation_date = None
