"""
Trade execution tool for MCP interface.

NOTE: This module uses the OLD positions table schema.
It is being replaced by the new trading_days schema.
Trade operations will be migrated to use the new schema in a future update.
"""

from fastmcp import FastMCP
import sys
import os
from typing import Dict, List, Optional, Any, Tuple
# Add project root directory to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
from tools.price_tools import get_open_prices
import json
from api.database import get_db_connection
from datetime import datetime, timezone
from tools.deployment_config import get_db_path
mcp = FastMCP("TradeTools")


def get_current_position_from_db(
    job_id: str,
    model: str,
    date: str,
    initial_cash: float = 10000.0
) -> Tuple[Dict[str, float], int]:
    """
    Get starting position for current trading day from database (new schema).

    Queries most recent trading_day record BEFORE the given date (previous day's ending).
    Returns ending holdings and cash from that previous day, which becomes the
    starting position for the current day.

    Args:
        job_id: Job UUID
        model: Model signature
        date: Current trading date (will query for date < this)
        initial_cash: Initial cash if no prior data (first trading day)

    Returns:
        (position_dict, action_count) where:
          - position_dict: {"AAPL": 10, "MSFT": 5, "CASH": 8500.0}
          - action_count: Number of holdings (for action_id tracking)
    """
    db_path = get_db_path("data/jobs.db")
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    try:
        # Query most recent trading_day BEFORE current date (previous day's ending position)
        cursor.execute("""
            SELECT id, ending_cash
            FROM trading_days
            WHERE job_id = ? AND model = ? AND date < ?
            ORDER BY date DESC
            LIMIT 1
        """, (job_id, model, date))

        row = cursor.fetchone()

        if row is None:
            # First day - return initial position
            return {"CASH": initial_cash}, 0

        trading_day_id, ending_cash = row

        # Query holdings for that day
        cursor.execute("""
            SELECT symbol, quantity
            FROM holdings
            WHERE trading_day_id = ?
        """, (trading_day_id,))

        holdings_rows = cursor.fetchall()

        # Build position dict
        position = {"CASH": ending_cash}
        for symbol, quantity in holdings_rows:
            position[symbol] = quantity

        # Action count is number of holdings (used for action_id)
        action_count = len(holdings_rows)

        return position, action_count

    finally:
        conn.close()


def _buy_impl(symbol: str, amount: int, signature: str = None, today_date: str = None,
              job_id: str = None, session_id: int = None, trading_day_id: int = None) -> Dict[str, Any]:
    """
    Internal buy implementation - accepts injected context parameters.

    Args:
        symbol: Stock symbol
        amount: Number of shares
        signature: Model signature (injected)
        today_date: Trading date (injected)
        job_id: Job ID (injected)
        session_id: Session ID (injected, DEPRECATED)
        trading_day_id: Trading day ID (injected)

    This function is not exposed to the AI model. It receives runtime context
    (signature, today_date, job_id, session_id, trading_day_id) from the ContextInjector.
    """
    # Validate required parameters
    if not job_id:
        return {"error": "Missing required parameter: job_id"}
    if not signature:
        return {"error": "Missing required parameter: signature"}
    if not today_date:
        return {"error": "Missing required parameter: today_date"}

    db_path = "data/jobs.db"
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    try:
        # Step 1: Get current position
        current_position, next_action_id = get_current_position_from_db(job_id, signature, today_date)

        # Step 2: Get stock price
        try:
            this_symbol_price = get_open_prices(today_date, [symbol])[f'{symbol}_price']
        except KeyError:
            return {"error": f"Symbol {symbol} not found on {today_date}", "symbol": symbol, "date": today_date}

        # Step 3: Validate sufficient cash
        cash_required = this_symbol_price * amount
        cash_available = current_position.get("CASH", 0)
        cash_left = cash_available - cash_required

        if cash_left < 0:
            return {
                "error": "Insufficient cash",
                "required_cash": cash_required,
                "cash_available": cash_available,
                "symbol": symbol,
                "date": today_date
            }

        # Step 4: Calculate new position
        new_position = current_position.copy()
        new_position["CASH"] = cash_left
        new_position[symbol] = new_position.get(symbol, 0) + amount

        # Step 5: Write to actions table (NEW SCHEMA)
        # NOTE: P&L is now calculated at the trading_days level, not per-trade
        if trading_day_id is None:
            # Get trading_day_id from runtime config if not provided
            from tools.general_tools import get_config_value
            trading_day_id = get_config_value('TRADING_DAY_ID')

            if trading_day_id is None:
                raise ValueError("trading_day_id not found in runtime config")

        created_at = datetime.now(timezone.utc).isoformat()

        cursor.execute("""
            INSERT INTO actions (
                trading_day_id, action_type, symbol, quantity, price, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            trading_day_id, "buy", symbol, amount, this_symbol_price, created_at
        ))

        # NOTE: Holdings are written by BaseAgent at end of day, not per-trade
        # This keeps the data model clean (one holdings snapshot per day)

        conn.commit()
        print(f"[buy] {signature} bought {amount} shares of {symbol} at ${this_symbol_price}")
        return new_position

    except Exception as e:
        conn.rollback()
        return {"error": f"Trade failed: {str(e)}", "symbol": symbol, "date": today_date}

    finally:
        conn.close()


@mcp.tool()
def buy(symbol: str, amount: int, signature: str = None, today_date: str = None,
        job_id: str = None, session_id: int = None, trading_day_id: int = None) -> Dict[str, Any]:
    """
    Buy stock shares.

    Args:
        symbol: Stock symbol (e.g., "AAPL", "MSFT", "GOOGL")
        amount: Number of shares to buy (positive integer)

    Returns:
        Dict[str, Any]:
          - Success: {"CASH": remaining_cash, "SYMBOL": shares, ...}
          - Failure: {"error": error_message, ...}

    Note: signature, today_date, job_id, session_id, trading_day_id are
    automatically injected by the system. Do not provide these parameters.
    """
    return _buy_impl(symbol, amount, signature, today_date, job_id, session_id, trading_day_id)


def _sell_impl(symbol: str, amount: int, signature: str = None, today_date: str = None,
               job_id: str = None, session_id: int = None, trading_day_id: int = None) -> Dict[str, Any]:
    """
    Sell stock function - writes to SQLite database.

    Args:
        symbol: Stock symbol (e.g., "AAPL", "MSFT")
        amount: Number of shares to sell (positive integer)
        signature: Model signature (injected by ContextInjector)
        today_date: Trading date YYYY-MM-DD (injected by ContextInjector)
        job_id: Job UUID (injected by ContextInjector)
        session_id: Trading session ID (injected by ContextInjector, DEPRECATED)
        trading_day_id: Trading day ID (injected by ContextInjector)

    Returns:
        Dict[str, Any]:
          - Success: {"CASH": amount, symbol: quantity, ...}
          - Failure: {"error": message, ...}
    """
    # Validate required parameters
    if not job_id:
        return {"error": "Missing required parameter: job_id"}
    if not signature:
        return {"error": "Missing required parameter: signature"}
    if not today_date:
        return {"error": "Missing required parameter: today_date"}

    db_path = "data/jobs.db"
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    try:
        # Step 1: Get current position
        current_position, next_action_id = get_current_position_from_db(job_id, signature, today_date)

        # Step 2: Validate position exists
        if symbol not in current_position:
            return {"error": f"No position for {symbol}", "symbol": symbol, "date": today_date}

        if current_position[symbol] < amount:
            return {
                "error": "Insufficient shares",
                "have": current_position[symbol],
                "want_to_sell": amount,
                "symbol": symbol,
                "date": today_date
            }

        # Step 3: Get stock price
        try:
            this_symbol_price = get_open_prices(today_date, [symbol])[f'{symbol}_price']
        except KeyError:
            return {"error": f"Symbol {symbol} not found on {today_date}", "symbol": symbol, "date": today_date}

        # Step 4: Calculate new position
        new_position = current_position.copy()
        new_position[symbol] -= amount
        new_position["CASH"] = new_position.get("CASH", 0) + (this_symbol_price * amount)

        # Step 5: Write to actions table (NEW SCHEMA)
        # NOTE: P&L is now calculated at the trading_days level, not per-trade
        if trading_day_id is None:
            from tools.general_tools import get_config_value
            trading_day_id = get_config_value('TRADING_DAY_ID')

            if trading_day_id is None:
                raise ValueError("trading_day_id not found in runtime config")

        created_at = datetime.now(timezone.utc).isoformat()

        cursor.execute("""
            INSERT INTO actions (
                trading_day_id, action_type, symbol, quantity, price, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            trading_day_id, "sell", symbol, amount, this_symbol_price, created_at
        ))

        conn.commit()
        print(f"[sell] {signature} sold {amount} shares of {symbol} at ${this_symbol_price}")
        return new_position

    except Exception as e:
        conn.rollback()
        return {"error": f"Trade failed: {str(e)}", "symbol": symbol, "date": today_date}

    finally:
        conn.close()


@mcp.tool()
def sell(symbol: str, amount: int, signature: str = None, today_date: str = None,
         job_id: str = None, session_id: int = None, trading_day_id: int = None) -> Dict[str, Any]:
    """
    Sell stock shares.

    Args:
        symbol: Stock symbol (e.g., "AAPL", "MSFT", "GOOGL")
        amount: Number of shares to sell (positive integer)

    Returns:
        Dict[str, Any]:
          - Success: {"CASH": remaining_cash, "SYMBOL": shares, ...}
          - Failure: {"error": error_message, ...}

    Note: signature, today_date, job_id, session_id, trading_day_id are
    automatically injected by the system. Do not provide these parameters.
    """
    return _sell_impl(symbol, amount, signature, today_date, job_id, session_id, trading_day_id)


if __name__ == "__main__":
    port = int(os.getenv("TRADE_HTTP_PORT", "8002"))
    mcp.run(transport="streamable-http", port=port)
