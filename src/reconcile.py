# src/reconcile.py
import csv
import pandas as pd
from logger import log
import config
import json
from datetime import datetime

def load_internal_trade_log():
    """Loads the agent's internal trade log into a pandas DataFrame."""
    try:
        df = pd.read_csv(config.TRADE_LOG_FILE)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df['price'] = pd.to_numeric(df['price'], errors='coerce')
        df['quantity'] = pd.to_numeric(df['quantity'], errors='coerce')
        log.info(f"Successfully loaded internal trade log from {config.TRADE_LOG_FILE}")
        return df
    except FileNotFoundError:
        log.error(f"Internal trade log not found at {config.TRADE_LOG_FILE}")
        return pd.DataFrame()
    except Exception as e:
        log.error(f"Error loading internal trade log: {e}")
        return pd.DataFrame()

def load_broker_statement(file_path: str):
    """
    Loads a broker's trade statement (CSV) into a pandas DataFrame.
    NOTE: This function assumes a specific CSV format from the broker.
    It will likely need to be ADJUSTED for your broker's actual file format.
    
    Expected columns: trade_date, symbol, action (BUY/SELL), quantity, price
    """
    try:
        df = pd.read_csv(file_path)
        # --- IMPORTANT: Adjust these column names for your broker's CSV ---
        df.rename(columns={
            'trade_date': 'timestamp',
            'symbol': 'symbol',
            'action': 'action',
            'quantity': 'quantity',
            'price': 'price'
        }, inplace=True)
        
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df['price'] = pd.to_numeric(df['price'], errors='coerce')
        df['quantity'] = pd.to_numeric(df['quantity'], errors='coerce')
        
        log.info(f"Successfully loaded broker statement from {file_path}")
        return df
    except FileNotFoundError:
        log.error(f"Broker statement not found at {file_path}")
        return pd.DataFrame()
    except Exception as e:
        log.error(f"Error loading broker statement: {e}")
        return pd.DataFrame()

def compare_trades(internal_df, broker_df):
    """
    Compares the two DataFrames to find discrepancies.
    This is a simplified comparison logic.
    """
    if internal_df.empty or broker_df.empty:
        log.error("One or both trade logs are empty. Cannot compare.")
        return

    # Normalize data for comparison
    internal_df['action'] = internal_df['action'].str.upper()
    broker_df['action'] = broker_df['action'].str.upper()
    
    # Create a unique key for each trade to merge on
    internal_df['key'] = internal_df.apply(lambda row: f"{row['timestamp'].date()}-{row['symbol']}-{row['action']}-{row['quantity']}", axis=1)
    broker_df['key'] = broker_df.apply(lambda row: f"{row['timestamp'].date()}-{row['symbol']}-{row['action']}-{row['quantity']}", axis=1)

    # Merge the two dataframes
    merged_df = pd.merge(internal_df, broker_df, on='key', how='outer', suffixes=('_internal', '_broker'))

    # Find discrepancies
    missing_in_broker = merged_df[merged_df['timestamp_broker'].isnull()]
    missing_in_internal = merged_df[merged_df['timestamp_internal'].isnull()]
    
    price_mismatches = merged_df[
        (merged_df['price_internal'].notna()) & 
        (merged_df['price_broker'].notna()) &
        (abs(merged_df['price_internal'] - merged_df['price_broker']) > 0.01) # Tolerance for float differences
    ]

    report = []
    report.append("--- 🔍 Reconciliation Report ---")
    report.append(f"Report generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    if not missing_in_broker.empty:
        report.append("--- Trades in Internal Log but MISSING in Broker Statement ---")
        report.append(missing_in_broker[['timestamp_internal', 'symbol_internal', 'action_internal', 'quantity_internal', 'price_internal']].to_string())
    
    if not missing_in_internal.empty:
        report.append("\n--- Trades in Broker Statement but MISSING in Internal Log ---")
        report.append(missing_in_internal[['timestamp_broker', 'symbol_broker', 'action_broker', 'quantity_broker', 'price_broker']].to_string())

    if not price_mismatches.empty:
        report.append("\n--- Trades with Price Mismatches ---")
        report.append(price_mismatches[['key', 'price_internal', 'price_broker']].to_string())

    if missing_in_broker.empty and missing_in_internal.empty and price_mismatches.empty:
        report.append("✅ All trades match perfectly. No discrepancies found.")
    
    return "\n".join(report)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description="Reconcile internal trade logs with a broker's statement.")
    parser.add_argument("broker_file", type=str, help="The file path to the broker's CSV statement.")
    args = parser.parse_args()

    log.info("--- Starting Reconciliation Process ---")
    
    internal_trades = load_internal_trade_log()
    broker_trades = load_broker_statement(args.broker_file)
    
    reconciliation_report = compare_trades(internal_trades, broker_trades)
    
    if reconciliation_report:
        print(reconciliation_report)
        
        report_filename = f"reconciliation_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(report_filename, "w") as f:
            f.write(reconciliation_report)
        log.info(f"Reconciliation report saved to {report_filename}")

    log.info("--- Reconciliation Process Finished ---")
