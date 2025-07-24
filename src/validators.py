# validators.py
from pydantic import BaseModel, Field, ValidationError
from typing import List, Optional, Dict
from datetime import date
from logger import log
from errors import DataValidationError
import config

class HistoricalDataCandle(BaseModel):
    """
    Validates a single candle from the Kite historical data API.
    """
    date: date
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: int = Field(ge=0)

class CalculatedIndicators(BaseModel):
    """
    Validates the structure of the calculated technical indicators.
    All fields are optional as some may not be calculable with insufficient data.
    """
    rsi_14: Optional[float] = None
    sma_20: Optional[float] = None
    sma_50: Optional[float] = None
    ema_5: Optional[float] = None
    macd_line: Optional[float] = None
    macd_signal: Optional[float] = None
    bb_upper: Optional[float] = None
    bb_lower: Optional[float] = None
    atr_14: Optional[float] = None

def validate_historical_data(data: List[dict], symbol: str = "N/A") -> List[HistoricalDataCandle]:
    """
    Validates a list of historical data candles, including sanity checks.
    Filters out any invalid records.
    """
    validated_data = []
    last_close = None

    for item in data:
        try:
            candle = HistoricalDataCandle.parse_obj(item)
            
            # --- Sanity Checks ---
            # 1. Price change check (if we have a previous day's close)
            if last_close:
                price_change_pct = abs((candle.close - last_close) / last_close) * 100
                if price_change_pct > config.MAX_DAY_PRICE_CHANGE_PERCENT:
                    log.error(f"[DATA_QUALITY_FLAG] Unrealistic daily price change for {symbol} on {candle.date}. Change: {price_change_pct:.2f}%. Discarding candle.")
                    continue # Skip this invalid candle
            
            # 2. Volume check
            if candle.volume == 0:
                log.warning(f"[DATA_QUALITY_FLAG] Zero volume recorded for {symbol} on {candle.date}.")

            validated_data.append(candle)
            last_close = candle.close

        except ValidationError as e:
            log.warning(f"[DATA_QUALITY_FLAG] Skipping invalid historical data record for {symbol}: {item}. Error: {e}")
            continue
            
    return validated_data

def validate_indicators(data: dict) -> CalculatedIndicators:
    """
    Validates the calculated indicators dictionary.
    """
    try:
        return CalculatedIndicators.parse_obj(data)
    except ValidationError as e:
        log.error(f"Indicator validation failed. Data: {data}. Error: {e}")
        # Return an empty model on failure
        return CalculatedIndicators()

# --- AI Model Validation ---

class AIDecision(BaseModel):
    """
    Validates the structured response from the AI model.
    """
    decision: str = Field(..., pattern=r"^(BUY|SELL|HOLD)$") # Must be one of these
    confidence: int = Field(..., ge=1, le=10) # Confidence score from 1 to 10
    reasoning: str = Field(..., min_length=10) # Must provide some reasoning

# --- Portfolio Validation ---

class Holding(BaseModel):
    quantity: int = Field(ge=0)
    entry_price: float = Field(ge=0)
    purchase_date: Optional[date] = None
    instrument_token: int
    exchange: str
    product: str
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    # Fields for Position Reviewer
    peak_price: Optional[float] = 0.0
    last_peak_date: Optional[date] = None


class WatchlistItem(BaseModel):
    instrument_token: int
    added_date: str # Using string for simplicity, can be date

class Portfolio(BaseModel):
    cash: float # Allow negative cash balance
    holdings: Dict[str, Holding]
    watchlist: Dict[str, WatchlistItem]

def validate_portfolio_data(data: dict) -> Portfolio:
    """
    Validates the portfolio data using the Pydantic model.
    Raises a DataValidationError if validation fails.
    """
    try:
        return Portfolio.parse_obj(data)
    except ValidationError as e:
        log.error(f"Portfolio data validation failed: {e}")
        # Wrap Pydantic's error in our custom exception
        raise DataValidationError(f"Invalid portfolio structure: {e}") from e
