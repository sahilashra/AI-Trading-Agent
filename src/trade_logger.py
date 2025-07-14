# src/trade_logger.py
import csv
import os
from datetime import datetime
from threading import Lock
from logger import log
import config

class TradeLogger:
    """
    A thread-safe logger for recording all trades to a CSV file.
    """
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.lock = Lock()
        self._initialize_file()

    def _initialize_file(self):
        """Creates the log file and writes the header if it doesn't exist."""
        with self.lock:
            # Check if the file exists and is not empty
            if not os.path.exists(self.file_path) or os.path.getsize(self.file_path) == 0:
                try:
                    with open(self.file_path, 'w', newline='', encoding='utf-8') as f:
                        writer = csv.writer(f)
                        # Define the header row
                        writer.writerow([
                            "timestamp", "symbol", "action", "quantity",
                            "price", "pnl", "reason"
                        ])
                    log.info(f"Trade log created at {self.file_path}")
                except IOError as e:
                    log.error(f"Could not create trade log file: {e}")

    def log_trade(self, symbol: str, action: str, quantity: int, price: float, pnl: float = 0.0, reason: str = ""):
        """Logs a single trade to the CSV file."""
        with self.lock:
            try:
                with open(self.file_path, 'a', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        datetime.now().isoformat(),
                        symbol,
                        action.upper(),
                        quantity,
                        f"{price:.2f}",
                        f"{pnl:.2f}",
                        reason
                    ])
            except IOError as e:
                log.error(f"Could not write to trade log file: {e}")

# Create a singleton instance to be used across the application.
# This ensures all parts of the app write to the same log file.
trade_logger = TradeLogger(config.TRADE_LOG_FILE)
