# circuit_breaker.py
import time
from functools import wraps
from logger import log
from errors import CriticalTradingError

class CircuitBreaker:
    """
    A circuit breaker to prevent repeated calls to a failing service.
    """
    def __init__(self, failure_threshold=5, recovery_timeout=300):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # Can be CLOSED, OPEN, HALF_OPEN

    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
            log.warning(f"Circuit breaker opened. Will not allow calls for {self.recovery_timeout} seconds.")

    def record_success(self):
        self.failure_count = 0
        self.last_failure_time = None
        if self.state == "HALF_OPEN":
            self.state = "CLOSED"
            log.info("Circuit breaker closed. Service has recovered.")

    def can_execute(self):
        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = "HALF_OPEN"
                log.info("Circuit breaker is now HALF_OPEN. Allowing a trial call.")
                return True
            return False
        return True

def with_circuit_breaker(breaker: CircuitBreaker):
    """
    A decorator to wrap a function with a circuit breaker.
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            if not breaker.can_execute():
                raise CriticalTradingError(f"Circuit breaker is open for {func.__name__}. Call rejected.")
            
            try:
                result = await func(*args, **kwargs)
                breaker.record_success()
                return result
            except Exception as e:
                breaker.record_failure()
                raise e # Re-raise the original exception
        return wrapper
    return decorator
