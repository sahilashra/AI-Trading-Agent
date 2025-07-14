# validators.py
from pydantic import BaseModel, Field, ValidationError
from typing import List, Optional, Dict
from datetime import date
from logger import log
from errors import DataValidationError

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

def validate_historical_data(data: List[dict]) -> List[HistoricalDataCandle]:
    """
    Validates a list of historical data candles.
    Filters out any invalid records.
    """
    validated_data = []
    for item in data:
        try:
            validated_data.append(HistoricalDataCandle.parse_obj(item))
        except ValidationError as e:
            log.warning(f"Skipping invalid historical data record: {item}. Error: {e}")
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
    purchase_date: Optional[date] = None # Date the holding was purchased
    instrument_token: int
    exchange: str
    product: str
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    peak_price: Optional[float] = None

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
