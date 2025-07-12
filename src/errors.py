# errors.py

class TradingError(Exception):
    """Base exception class for all trading agent errors."""
    pass

class CriticalTradingError(TradingError):
    """
    Exception for critical errors that should halt the trading agent's operations.
    Examples: Invalid API keys, authentication failure, portfolio corruption.
    """
    pass

class MinorTradingError(TradingError):
    """
    Exception for non-critical, often transient errors that can be retried.
    Examples: Temporary network issues, API rate limits, non-critical data fetching failures.
    """
    pass

class DataValidationError(TradingError):
    """
    Exception for errors that occur during data validation.
    Example: Missing keys in portfolio data, incorrect data types.
    """
    pass
