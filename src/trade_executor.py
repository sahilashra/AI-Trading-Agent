from logger import log
import random
import string
from utils import retry_api_call
import asyncio
import time
from state import portfolio_context
import config
from datetime import datetime

class OrderExecutionResult:
    """A structured result for order execution."""
    def __init__(self, status: str, order_id: str, filled_quantity: int = 0, average_price: float = 0.0):
        self.status = status  # e.g., "COMPLETE", "REJECTED", "FAILED", "PARTIAL"
        self.order_id = order_id
        self.filled_quantity = filled_quantity
        self.average_price = average_price

    def __repr__(self):
        return f"OrderExecutionResult(status={self.status}, order_id={self.order_id}, filled_quantity={self.filled_quantity}, average_price={self.average_price})"

@retry_api_call()
async def place_and_confirm_order(kite: "AsyncKiteClient", symbol: str, transaction_type: str, quantity: int, variety: str = "regular") -> OrderExecutionResult:
    """
    Places a CNC market order and polls until it's confirmed, rejected, or times out.
    Handles partial fills.
    """
    order_id = None
    try:
        order_id = await kite.place_order(
            tradingsymbol=symbol,
            exchange="NSE",
            transaction_type=transaction_type,
            quantity=quantity,
            product="CNC",
            order_type="MARKET",
            validity="DAY",
            variety=variety
        )
        log.info(f"(LIVE) Placed {transaction_type} order for {quantity} of {symbol}. Order ID: {order_id}. Now confirming...")
    except Exception as e:
        log.error(f"(LIVE) Could not place order for {symbol}: {e}")
        return OrderExecutionResult(status="FAILED", order_id=None)

    start_time = time.time()
    while time.time() - start_time < config.ORDER_TIMEOUT_SECONDS:
        try:
            orders = await kite.orders()
            order_history = [o for o in orders if o['order_id'] == order_id]

            if not order_history:
                await asyncio.sleep(config.ORDER_POLL_INTERVAL_SECONDS)
                continue

            order_info = order_history[0]
            status = order_info['status']
            filled_quantity = order_info.get('filled_quantity', 0)
            average_price = order_info.get('average_price', 0.0)

            if status == "COMPLETE":
                log.info(f"(LIVE) Order {order_id} for {symbol} is COMPLETE. Filled {filled_quantity} @ avg price {average_price:.2f}")
                return OrderExecutionResult("COMPLETE", order_id, filled_quantity, average_price)
            
            if status == "REJECTED":
                log.error(f"(LIVE) Order {order_id} for {symbol} was REJECTED. Reason: {order_info.get('status_message', 'N/A')}")
                return OrderExecutionResult("REJECTED", order_id)

            if status == "OPEN" and filled_quantity > 0:
                log.warning(f"(LIVE) Order {order_id} for {symbol} is partially filled. Filled: {filled_quantity}/{quantity}. Continuing to monitor.")

        except Exception as e:
            log.error(f"(LIVE) Error while polling for order {order_id}: {e}")
        
        await asyncio.sleep(config.ORDER_POLL_INTERVAL_SECONDS)

    # If loop finishes, it's a timeout
    log.error(f"(LIVE) Order {order_id} for {symbol} timed out after {config.ORDER_TIMEOUT_SECONDS}s.")
    # Check one last time for partial fills
    try:
        final_orders = await kite.orders()
        final_order_info = [o for o in final_orders if o['order_id'] == order_id]
        if final_order_info:
            filled_quantity = final_order_info[0].get('filled_quantity', 0)
            if filled_quantity > 0:
                log.warning(f"(LIVE) Order {order_id} for {symbol} timed out but was partially filled. Quantity: {filled_quantity}")
                return OrderExecutionResult("PARTIAL", order_id, filled_quantity, final_order_info[0].get('average_price', 0.0))
    except Exception as e:
        log.error(f"(LIVE) Could not perform final check on timed out order {order_id}: {e}")

    return OrderExecutionResult("FAILED", order_id, status="TIMEOUT")


async def place_paper_order(portfolio_data: dict, symbol: str, transaction_type: str, quantity: int, price: float, instrument_token: int) -> OrderExecutionResult:
    """
    Simulates placing a market order for paper trading.
    The portfolio dictionary is modified in place. The caller is responsible for locking and saving.
    Returns a successful OrderExecutionResult.
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
                    "instrument_token": instrument_token,
                    "purchase_date": datetime.now().date().isoformat(),
                    "exchange": "NSE", "product": "CNC"
                }
            log.info(f"(PAPER) Portfolio updated after BUY. New cash: ₹{portfolio_data['cash']:,.2f}")
            return OrderExecutionResult("COMPLETE", sim_order_id, quantity, price)
        else:
            log.error("(PAPER) Insufficient cash for simulated BUY order.")
            return OrderExecutionResult("REJECTED", sim_order_id)

    elif transaction_type == "SELL":
        if symbol in portfolio_data['holdings'] and portfolio_data['holdings'][symbol]['quantity'] >= quantity:
            portfolio_data['cash'] += quantity * price
            portfolio_data['holdings'][symbol]['quantity'] -= quantity
            if portfolio_data['holdings'][symbol]['quantity'] == 0:
                del portfolio_data['holdings'][symbol]
            log.info(f"(PAPER) Portfolio updated after SELL. New cash: ₹{portfolio_data['cash']:,.2f}")
            return OrderExecutionResult("COMPLETE", sim_order_id, quantity, price)
        else:
            log.error(f"(PAPER) Not enough holdings of {symbol} to simulate SELL order.")
            return OrderExecutionResult("REJECTED", sim_order_id)

    return OrderExecutionResult("FAILED", sim_order_id)


if __name__ == '__main__':
    log.info("This module is intended to be imported, not run directly.")
