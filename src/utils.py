# utils.py
import asyncio
from functools import wraps
from logger import log

def retry_api_call(retries=3, delay=5):
    """
    A decorator to retry an async function call if it fails.
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            for i in range(retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    log.warning(f"API call {func.__name__} failed with error: {e}. Retrying in {delay} seconds... (Attempt {i+1}/{retries})")
                    if i == retries - 1:
                        log.error(f"API call {func.__name__} failed after {retries} retries.")
                        # Re-raise the exception to be handled by the caller
                        raise
                    await asyncio.sleep(delay)
        return wrapper
    return decorator
