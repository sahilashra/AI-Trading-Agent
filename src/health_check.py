# health_check.py
import asyncio
import json
from datetime import datetime
import psutil
import config
from logger import log
from errors import CriticalTradingError, MinorTradingError
from utils import kite_breaker
from state import (
    ltp_cache, historical_data_cache, last_cache_invalidation_date
)

async def health_check(kite: "AsyncKiteClient") -> dict:
    """
    Performs a comprehensive health check of the system.
    Returns a dictionary with health status and details.
    """
    health_status = {
        "overall": "HEALTHY",
        "timestamp": datetime.now().isoformat(),
        "checks": {}
    }
    
    issues = []
    
    # 1. API Connectivity Check
    try:
        profile = await asyncio.wait_for(kite.profile(), timeout=10.0)
        health_status["checks"]["api_connectivity"] = {
            "status": "PASS",
            "user": profile.get('user_name', 'Unknown')
        }
    except Exception as e:
        issues.append("API connectivity failed")
        health_status["checks"]["api_connectivity"] = {
            "status": "FAIL",
            "error": str(e)
        }
    
    # 2. Portfolio File Check
    try:
        with open(config.PORTFOLIO_FILE, 'r') as f:
            portfolio_data = json.load(f)
        health_status["checks"]["portfolio_file"] = {
            "status": "PASS",
            "holdings_count": len(portfolio_data.get("holdings", {})),
            "watchlist_count": len(portfolio_data.get("watchlist", {}))
        }
    except Exception as e:
        issues.append("Portfolio file check failed")
        health_status["checks"]["portfolio_file"] = {
            "status": "FAIL",
            "error": str(e)
        }
    
    # 3. Market Data Check
    try:
        test_data = await asyncio.wait_for(
            kite.ltp([f"{config.EXCHANGE}:{config.NIFTY_50_TOKEN}"]), 
            timeout=10.0
        )
        health_status["checks"]["market_data"] = {
            "status": "PASS",
            "nifty_price": test_data.get(f"{config.EXCHANGE}:{config.NIFTY_50_TOKEN}", {}).get("last_price", "N/A")
        }
    except Exception as e:
        issues.append("Market data check failed")
        health_status["checks"]["market_data"] = {
            "status": "FAIL",
            "error": str(e)
        }
    
    # 4. Memory Usage Check
    try:
        memory_usage = psutil.virtual_memory().percent
        health_status["checks"]["memory_usage"] = {
            "status": "PASS" if memory_usage < 80 else "WARN",
            "usage_percent": memory_usage
        }
        if memory_usage > 90:
            issues.append("High memory usage")
    except Exception as e:
        health_status["checks"]["memory_usage"] = {
            "status": "SKIP",
            "error": str(e)
        }
    
    # 5. Cache Health Check
    cache_health = {
        "ltp_cache_size": len(ltp_cache),
        "historical_cache_size": len(historical_data_cache),
        "last_cache_clear": last_cache_invalidation_date.isoformat() if last_cache_invalidation_date else "Never"
    }
    health_status["checks"]["cache_health"] = {
        "status": "PASS",
        **cache_health
    }
    
    # 6. Circuit Breaker Status
    health_status["checks"]["circuit_breaker"] = {
        "status": "PASS" if kite_breaker.state == "CLOSED" else "WARN",
        "state": kite_breaker.state,
        "failure_count": kite_breaker.failure_count
    }
    
    # Overall Health Assessment
    if issues:
        health_status["overall"] = "DEGRADED" if len(issues) <= 2 else "UNHEALTHY"
        health_status["issues"] = issues
    
    return health_status
