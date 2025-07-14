import pandas as pd
import pandas_ta as ta
from logger import log
from validators import validate_historical_data, validate_indicators, CalculatedIndicators

def calculate_indicators(historical_data: list) -> CalculatedIndicators:
    """
    Calculates technical indicators from historical price data and validates the output.
    """
    # 1. Validate the incoming raw data
    validated_candles = validate_historical_data(historical_data)
    
    # Add a check to ensure there's enough data for the longest SMA (50)
    if not validated_candles or len(validated_candles) < 50:
        log.warning("Not enough valid historical data to calculate all indicators.")
        return CalculatedIndicators()

    try:
        # Convert the validated Pydantic objects back to a list of dicts for pandas
        df_data = [candle.model_dump() for candle in validated_candles]
        df = pd.DataFrame(df_data)

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
        latest_indicators_dict = {
            "rsi_14": float(round(df['RSI_14'].iloc[-1], 2)) if pd.notna(df['RSI_14'].iloc[-1]) else None,
            "sma_20": float(round(df['SMA_20'].iloc[-1], 2)) if pd.notna(df['SMA_20'].iloc[-1]) else None,
            "sma_50": float(round(df['SMA_50'].iloc[-1], 2)) if pd.notna(df['SMA_50'].iloc[-1]) else None,
            "macd_line": float(round(df['MACD_12_26_9'].iloc[-1], 2)) if pd.notna(df['MACD_12_26_9'].iloc[-1]) else None,
            "macd_signal": float(round(df['MACDs_12_26_9'].iloc[-1], 2)) if pd.notna(df['MACDs_12_26_9'].iloc[-1]) else None,
            "bb_upper": float(round(df['BBU_20_2.0'].iloc[-1], 2)) if pd.notna(df['BBU_20_2.0'].iloc[-1]) else None,
            "bb_lower": float(round(df['BBL_20_2.0'].iloc[-1], 2)) if pd.notna(df['BBL_20_2.0'].iloc[-1]) else None,
            "atr_14": float(round(df['ATRr_14'].iloc[-1], 2)) if pd.notna(df['ATRr_14'].iloc[-1]) else None
        }
        
        # 2. Validate the calculated indicators
        validated_indicators = validate_indicators(latest_indicators_dict)
        
        log.debug(f"Calculated Indicators for {validated_candles[-1].date}: {validated_indicators.dict()}")
        return validated_indicators

    except Exception as e:
        log.error(f"Failed to calculate technical indicators: {e}")
        return CalculatedIndicators()

if __name__ == '__main__':
    log.info("This module is intended to be imported, not run directly.")