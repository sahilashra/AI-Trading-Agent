# src/dashboard.py
import asyncio
import json
import os
import time
from datetime import datetime
from dotenv import load_dotenv

# --- Load .env first ---
# This is crucial for a standalone script that uses the config
dotenv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
load_dotenv(dotenv_path=dotenv_path)

import config
from logger import log

def clear_screen():
    """Clears the terminal screen."""
    os.system('cls' if os.name == 'nt' else 'clear')


def get_portfolio_file():
    """Gets the correct portfolio file path based on the trading mode."""
    return config.PAPER_PORTFOLIO_FILE if config.LIVE_PAPER_TRADING else config.PORTFOLIO_FILE

def read_portfolio_data():
    """Reads and returns the portfolio data from the JSON file."""
    portfolio_file = get_portfolio_file()
    try:
        with open(portfolio_file, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"cash": 0.0, "holdings": {}}
    except Exception as e:
        log.error(f"Error reading portfolio for dashboard: {e}")
        return {"cash": 0.0, "holdings": {}}

def read_last_log_lines(log_file_path, num_lines=10):
    """Reads the last N lines from the trading log file."""
    try:
        with open(log_file_path, 'r') as f:
            lines = f.readlines()
            return lines[-num_lines:]
    except FileNotFoundError:
        return ["Log file not found."]
    except Exception as e:
        return [f"Error reading log file: {e}"]

def display_dashboard(portfolio_data, log_lines):
    """Renders the CLI dashboard with robust handling for None values."""
    clear_screen()
    
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    mode = "PAPER TRADING" if config.LIVE_PAPER_TRADING else "LIVE TRADING"
    
    print("--- AI Trading Agent Dashboard ---")
    print(f"Last Updated: {now} | Mode: {mode}")
    print("-" * 40)

    # --- Portfolio Summary (with robust None checks) ---
    cash = portfolio_data.get('cash')
    cash_str = f"₹{cash:,.2f}" if cash is not None else "N/A"
    
    holdings = portfolio_data.get('holdings', {})
    holdings_count = len(holdings)
    
    print(f"Available Cash: {cash_str}")
    print(f"Open Positions: {holdings_count}")
    print("-" * 40)

    # --- Open Positions ---
    if not holdings:
        print("No open positions.")
    else:
        print(f"{'Symbol':<15} {'Qty':>8} {'Entry Price':>15} {'Purchase Date':>15}")
        print("-" * 60)
        for symbol, pos in holdings.items():
            # Robustly handle None for every field before formatting
            qty_val = pos.get('quantity')
            qty_str = str(qty_val) if qty_val is not None else "N/A"

            price_val = pos.get('entry_price')
            entry_price_str = f"₹{price_val:,.2f}" if price_val is not None else "N/A"

            date_val = pos.get('purchase_date')
            purchase_date_str = str(date_val) if date_val is not None else "N/A"
            
            print(f"{symbol:<15} {qty_str:>8} {entry_price_str:>15} {purchase_date_str:>15}")
    
    print("\n" + "-" * 40)
    
    # --- Recent Activity Log ---
    print("Recent Activity (from trading_agent.log):")
    for line in log_lines:
        if "ERROR" in line or "CRITICAL" in line:
            print(f"\033[91m>> {line.strip()}\033[0m")
        elif "WARNING" in line:
            print(f"\033[93m>> {line.strip()}\033[0m")
        else:
            print(f">> {line.strip()}")


    print("\nPress Ctrl+C to exit dashboard.")

async def main():
    """Main loop to refresh the dashboard periodically."""
    log_file = os.path.join(config.PROJECT_ROOT, 'logs', 'trading_agent.log')
    
    while True:
        try:
            portfolio = read_portfolio_data()
            logs = read_last_log_lines(log_file, num_lines=15)
            display_dashboard(portfolio, logs)
            await asyncio.sleep(5) # Refresh every 5 seconds
        except KeyboardInterrupt:
            print("\nDashboard shutting down.")
            break
        except Exception as e:
            print(f"\nAn error occurred in the dashboard: {e}")
            break

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
