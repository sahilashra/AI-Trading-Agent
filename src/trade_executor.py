from kiteconnect import KiteConnect
from logger import log
import random
import string
from utils import retry_api_call

@retry_api_call()
async def place_market_order(kite: KiteConnect, symbol: str, transaction_type: str, quantity: int, variety: str = "regular"):
    """
    Places a CNC (delivery) market order on Zerodha Kite.
    The product type is hardcoded to CNC to prevent accidental intraday trades.
    """
    try:
        order_id = kite.place_order(
            tradingsymbol=symbol,
            exchange="NSE",
            transaction_type=transaction_type,
            quantity=quantity,
            product="CNC",  # Hardcoded for safety
            order_type="MARKET",
            validity="DAY",
            variety=variety
        )
        log.info(f"(LIVE) Placed {transaction_type} CNC order for {quantity} of {symbol}. Order ID: {order_id}")
        return order_id
    except Exception as e:
        log.error(f"(LIVE) Could not place order for {symbol}: {e}")
        # The decorator will handle the retry, so we re-raise the exception
        raise

async def place_paper_order(symbol: str, transaction_type: str, quantity: int):
    """
    Simulates placing a market order for paper trading.
    """
    sim_order_id = ''.join(random.choices(string.digits, k=12))
    log.info(f"(PAPER) Simulated {transaction_type} order for {quantity} of {symbol}. Sim Order ID: {sim_order_id}")
    return sim_order_id

if __name__ == '__main__':
    log.info("This module is intended to be imported, not run directly.")
