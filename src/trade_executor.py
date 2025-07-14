from logger import log
import random
import string
from utils import retry_api_call
import asyncio
from state import portfolio_context

@retry_api_call()
async def place_market_order(kite: "AsyncKiteClient", symbol: str, transaction_type: str, quantity: int, variety: str = "regular"):
    """
    Places a CNC (delivery) market order on Zerodha Kite.
    The product type is hardcoded to CNC to prevent accidental intraday trades.
    """
    try:
        # This function is now correctly awaited in main.py
        order_id = await kite.place_order(
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
        raise

async def place_paper_order(portfolio_data: dict, symbol: str, transaction_type: str, quantity: int, price: float, instrument_token: int):
    """
    Simulates placing a market order for paper trading.
    The portfolio dictionary is modified in place. The caller is responsible for locking and saving.
    """
    sim_order_id = ''.join(random.choices(string.digits, k=12))
    log.info(f"(PAPER) Simulated {transaction_type} order for {quantity} of {symbol} @ ₹{price:.2f}. Sim Order ID: {sim_order_id}")

    if transaction_type == "BUY":
        cost = quantity * price
        if portfolio_data.get('cash', 0) >= cost:
            portfolio_data['cash'] -= cost
            if symbol in portfolio_data['holdings']:
                existing_qty = portfolio_data['holdings'][symbol]['quantity']
                existing_price = portfolio_data['holdings'][symbol]['entry_price']
                new_qty = existing_qty + quantity
                new_avg_price = ((existing_qty * existing_price) + (quantity * price)) / new_qty
                portfolio_data['holdings'][symbol]['quantity'] = new_qty
                portfolio_data['holdings'][symbol]['entry_price'] = new_avg_price
            else:
                portfolio_data['holdings'][symbol] = {
                    "quantity": quantity, "entry_price": price,
                    "instrument_token": instrument_token, # FIX: Use the correct token
                    "exchange": "NSE", "product": "CNC"
                }
            log.info(f"(PAPER) Portfolio updated after BUY. New cash: ₹{portfolio_data['cash']:,.2f}")
        else:
            log.error("(PAPER) Insufficient cash for simulated BUY order.")

    elif transaction_type == "SELL":
        if symbol in portfolio_data['holdings'] and portfolio_data['holdings'][symbol]['quantity'] >= quantity:
            portfolio_data['cash'] += quantity * price
            portfolio_data['holdings'][symbol]['quantity'] -= quantity
            if portfolio_data['holdings'][symbol]['quantity'] == 0:
                del portfolio_data['holdings'][symbol]
            log.info(f"(PAPER) Portfolio updated after SELL. New cash: ₹{portfolio_data['cash']:,.2f}")
        else:
            log.error(f"(PAPER) Not enough holdings of {symbol} to simulate SELL order.")

    return sim_order_id

if __name__ == '__main__':
    log.info("This module is intended to be imported, not run directly.")
