from fastmcp import FastMCP
import sys
import os
from typing import Dict, List, Optional, Any, Tuple
# Add project root directory to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
from tools.price_tools import get_open_prices
import json
from tools.deployment_config import get_db_path
from api.database import get_db_connection
from datetime import datetime
mcp = FastMCP("TradeTools")


def get_current_position_from_db(job_id: str, model: str, date: str) -> Tuple[Dict[str, float], int]:
    """
    Query current position from SQLite database.

    Args:
        job_id: Job UUID
        model: Model signature
        date: Trading date (YYYY-MM-DD)

    Returns:
        Tuple of (position_dict, next_action_id)
        - position_dict: {symbol: quantity, "CASH": amount}
        - next_action_id: Next available action_id for this job+model

    Raises:
        Exception: If database query fails
    """
    db_path = get_db_path()
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    try:
        # Get most recent position on or before this date
        cursor.execute("""
            SELECT p.id, p.cash
            FROM positions p
            WHERE p.job_id = ? AND p.model = ? AND p.date <= ?
            ORDER BY p.date DESC, p.action_id DESC
            LIMIT 1
        """, (job_id, model, date))

        position_row = cursor.fetchone()

        if not position_row:
            # No position found - this shouldn't happen if ModelDayExecutor initializes properly
            raise Exception(f"No position found for job_id={job_id}, model={model}, date={date}")

        position_id = position_row[0]
        cash = position_row[1]

        # Build position dict starting with CASH
        position_dict = {"CASH": cash}

        # Get holdings for this position
        cursor.execute("""
            SELECT symbol, quantity
            FROM holdings
            WHERE position_id = ?
        """, (position_id,))

        for row in cursor.fetchall():
            symbol = row[0]
            quantity = row[1]
            position_dict[symbol] = quantity

        # Get next action_id
        cursor.execute("""
            SELECT COALESCE(MAX(action_id), -1) + 1 as next_action_id
            FROM positions
            WHERE job_id = ? AND model = ?
        """, (job_id, model))

        next_action_id = cursor.fetchone()[0]

        return position_dict, next_action_id

    finally:
        conn.close()


@mcp.tool()
def buy(symbol: str, amount: int, signature: str = None, today_date: str = None,
        job_id: str = None, session_id: int = None) -> Dict[str, Any]:
    """
    Buy stock function - writes to SQLite database.

    Args:
        symbol: Stock symbol (e.g., "AAPL", "MSFT")
        amount: Number of shares to buy (positive integer)
        signature: Model signature (injected by ContextInjector)
        today_date: Trading date YYYY-MM-DD (injected by ContextInjector)
        job_id: Job UUID (injected by ContextInjector)
        session_id: Trading session ID (injected by ContextInjector)

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

    db_path = get_db_path()
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

        # Step 5: Calculate portfolio value and P&L
        portfolio_value = cash_left
        for sym, qty in new_position.items():
            if sym != "CASH":
                try:
                    price = get_open_prices(today_date, [sym])[f'{sym}_price']
                    portfolio_value += qty * price
                except KeyError:
                    pass  # Symbol price not available, skip

        # Get previous portfolio value for P&L calculation
        cursor.execute("""
            SELECT portfolio_value
            FROM positions
            WHERE job_id = ? AND model = ? AND date < ?
            ORDER BY date DESC, action_id DESC
            LIMIT 1
        """, (job_id, signature, today_date))

        row = cursor.fetchone()
        previous_value = row[0] if row else 10000.0  # Default initial value

        daily_profit = portfolio_value - previous_value
        daily_return_pct = (daily_profit / previous_value * 100) if previous_value > 0 else 0

        # Step 6: Write to positions table
        created_at = datetime.utcnow().isoformat() + "Z"

        cursor.execute("""
            INSERT INTO positions (
                job_id, date, model, action_id, action_type, symbol,
                amount, price, cash, portfolio_value, daily_profit,
                daily_return_pct, session_id, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job_id, today_date, signature, next_action_id, "buy", symbol,
            amount, this_symbol_price, cash_left, portfolio_value, daily_profit,
            daily_return_pct, session_id, created_at
        ))

        position_id = cursor.lastrowid

        # Step 7: Write to holdings table
        for sym, qty in new_position.items():
            if sym != "CASH":
                cursor.execute("""
                    INSERT INTO holdings (position_id, symbol, quantity)
                    VALUES (?, ?, ?)
                """, (position_id, sym, qty))

        conn.commit()
        print(f"[buy] {signature} bought {amount} shares of {symbol} at ${this_symbol_price}")
        return new_position

    except Exception as e:
        conn.rollback()
        return {"error": f"Trade failed: {str(e)}", "symbol": symbol, "date": today_date}

    finally:
        conn.close()


@mcp.tool()
def sell(symbol: str, amount: int, signature: str = None, today_date: str = None,
         job_id: str = None, session_id: int = None) -> Dict[str, Any]:
    """
    Sell stock function - writes to SQLite database.

    Args:
        symbol: Stock symbol (e.g., "AAPL", "MSFT")
        amount: Number of shares to sell (positive integer)
        signature: Model signature (injected by ContextInjector)
        today_date: Trading date YYYY-MM-DD (injected by ContextInjector)
        job_id: Job UUID (injected by ContextInjector)
        session_id: Trading session ID (injected by ContextInjector)

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

    db_path = get_db_path()
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

        # Step 5: Calculate portfolio value and P&L
        portfolio_value = new_position["CASH"]
        for sym, qty in new_position.items():
            if sym != "CASH":
                try:
                    price = get_open_prices(today_date, [sym])[f'{sym}_price']
                    portfolio_value += qty * price
                except KeyError:
                    pass

        # Get previous portfolio value
        cursor.execute("""
            SELECT portfolio_value
            FROM positions
            WHERE job_id = ? AND model = ? AND date < ?
            ORDER BY date DESC, action_id DESC
            LIMIT 1
        """, (job_id, signature, today_date))

        row = cursor.fetchone()
        previous_value = row[0] if row else 10000.0

        daily_profit = portfolio_value - previous_value
        daily_return_pct = (daily_profit / previous_value * 100) if previous_value > 0 else 0

        # Step 6: Write to positions table
        created_at = datetime.utcnow().isoformat() + "Z"

        cursor.execute("""
            INSERT INTO positions (
                job_id, date, model, action_id, action_type, symbol,
                amount, price, cash, portfolio_value, daily_profit,
                daily_return_pct, session_id, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job_id, today_date, signature, next_action_id, "sell", symbol,
            amount, this_symbol_price, new_position["CASH"], portfolio_value, daily_profit,
            daily_return_pct, session_id, created_at
        ))

        position_id = cursor.lastrowid

        # Step 7: Write to holdings table
        for sym, qty in new_position.items():
            if sym != "CASH":
                cursor.execute("""
                    INSERT INTO holdings (position_id, symbol, quantity)
                    VALUES (?, ?, ?)
                """, (position_id, sym, qty))

        conn.commit()
        print(f"[sell] {signature} sold {amount} shares of {symbol} at ${this_symbol_price}")
        return new_position

    except Exception as e:
        conn.rollback()
        return {"error": f"Trade failed: {str(e)}", "symbol": symbol, "date": today_date}

    finally:
        conn.close()


if __name__ == "__main__":
    port = int(os.getenv("TRADE_HTTP_PORT", "8002"))
    mcp.run(transport="streamable-http", port=port)
