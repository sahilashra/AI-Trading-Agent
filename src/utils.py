# utils.py
import asyncio
import threading
import uuid
import queue
from functools import wraps
from logger import log
from kiteconnect import KiteConnect
from typing import Callable, Any, Dict
from circuit_breaker import CircuitBreaker, with_circuit_breaker

# Global circuit breaker for all Kite Connect API calls
kite_breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=300)

def retry_api_call(retries=3, delay=5):
    """
    A decorator to retry an async function call with a circuit breaker if it fails.
    """
    def decorator(func):
        @wraps(func)
        @with_circuit_breaker(kite_breaker)
        async def wrapper(*args, **kwargs):
            for i in range(retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    log.warning(f"API call {func.__name__} failed with error: {e}. Retrying in {delay} seconds... (Attempt {i+1}/{retries})")
                    if i == retries - 1:
                        log.error(f"API call {func.__name__} failed after {retries} retries.")
                        raise
                    await asyncio.sleep(delay)
        return wrapper
    return decorator

class KiteWorker(threading.Thread):
    """
    A dedicated thread to handle all blocking KiteConnect API calls.
    """
    def __init__(self, kite: KiteConnect, request_queue: queue.Queue, response_dict: Dict):
        super().__init__()
        self.daemon = True  # Allows main program to exit even if this thread is running
        self._kite = kite
        self._request_queue = request_queue
        self._response_dict = response_dict
        self._stop_event = threading.Event()

    def run(self):
        log.info("KiteWorker thread started.")
        while not self._stop_event.is_set():
            try:
                # Use a timeout to periodically check the stop event
                request_id, func_name, args, kwargs = self._request_queue.get(timeout=1)
                
                try:
                    func = getattr(self._kite, func_name)
                    result = func(*args, **kwargs)
                    self._response_dict[request_id] = {"result": result, "error": None}
                except Exception as e:
                    log.error(f"KiteWorker error executing {func_name}: {e}")
                    self._response_dict[request_id] = {"result": None, "error": e}
                finally:
                    self._request_queue.task_done()

            except queue.Empty: # Use the correct exception for queue.Queue
                continue
            except Exception as e:
                log.error(f"KiteWorker encountered an unexpected error: {e}")

        log.info("KiteWorker thread stopped.")

    def stop(self):
        self._stop_event.set()

class AsyncKiteClient:
    """
    An async client that communicates with the KiteWorker thread.
    """
    def __init__(self, kite: KiteConnect):
        self._request_queue = queue.Queue() # Use the thread-safe queue
        self._response_dict = {}
        self._worker = KiteWorker(kite, self._request_queue, self._response_dict)
        self._worker.start()

    async def _execute(self, func_name: str, *args, **kwargs):
        request_id = str(uuid.uuid4())
        
        # Use run_in_executor to call the blocking put method from the event loop
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None, 
            lambda: self._request_queue.put((request_id, func_name, args, kwargs))
        )
        
        while request_id not in self._response_dict:
            await asyncio.sleep(0.01) # Yield control to the event loop

        response = self._response_dict.pop(request_id)
        if response["error"]:
            raise response["error"]
        return response["result"]

    def __getattr__(self, name: str) -> Callable[..., Any]:
        """
        Dynamically creates async methods for any KiteConnect method.
        """
        async def method(*args, **kwargs):
            return await self._execute(name, *args, **kwargs)
        return method

    def stop_worker(self):
        self._worker.stop()
