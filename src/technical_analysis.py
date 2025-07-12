import pandas as pd
import pandas_ta as ta
from logger import log

def calculate_indicators(historical_data: list) -> dict:
    """
    Calculates technical indicators (RSI, SMA) from historical price data.

    Args:
        historical_data: A list of historical candle data from the Kite API.

    Returns:
        A dictionary containing the calculated indicator values.
    """
    if not historical_data or len(historical_data) < 50: # Need enough data for 50-day SMA
        log.warning("Not enough historical data to calculate all indicators.")
        return {}

    try:
        # Convert the list of dictionaries to a pandas DataFrame
        df = pd.DataFrame(historical_data)

        # Ensure the 'close' column is numeric
        df['close'] = pd.to_numeric(df['close'])

        # Use the pandas_ta extension
        df.ta.rsi(length=14, append=True)
        df.ta.sma(length=20, append=True)
        df.ta.sma(length=50, append=True)
        df.ta.macd(append=True)
        df.ta.bbands(length=20, append=True)
        df.ta.atr(length=14, append=True)

        # Get the latest values, checking for NaN
        latest_indicators = {
            "rsi_14": float(round(df['RSI_14'].iloc[-1], 2)) if pd.notna(df['RSI_14'].iloc[-1]) else None,
            "sma_20": float(round(df['SMA_20'].iloc[-1], 2)) if pd.notna(df['SMA_20'].iloc[-1]) else None,
            "sma_50": float(round(df['SMA_50'].iloc[-1], 2)) if pd.notna(df['SMA_50'].iloc[-1]) else None,
            "macd_line": float(round(df['MACD_12_26_9'].iloc[-1], 2)) if pd.notna(df['MACD_12_26_9'].iloc[-1]) else None,
            "macd_signal": float(round(df['MACDs_12_26_9'].iloc[-1], 2)) if pd.notna(df['MACDs_12_26_9'].iloc[-1]) else None,
            "bb_upper": float(round(df['BBU_20_2.0'].iloc[-1], 2)) if pd.notna(df['BBU_20_2.0'].iloc[-1]) else None,
            "bb_lower": float(round(df['BBL_20_2.0'].iloc[-1], 2)) if pd.notna(df['BBL_20_2.0'].iloc[-1]) else None,
            "atr_14": float(round(df['ATRr_14'].iloc[-1], 2)) if pd.notna(df['ATRr_14'].iloc[-1]) else None
        }
        
        # Remove any indicators that are still None
        latest_indicators = {k: v for k, v in latest_indicators.items() if v is not None}
        
        log.debug(f"Calculated Indicators for {historical_data[-1]['date']}: {latest_indicators}")
        return latest_indicators

    except Exception as e:
        log.error(f"Failed to calculate technical indicators: {e}")
        return {}

if __name__ == '__main__':
    log.info("This module is intended to be imported, not run directly.")