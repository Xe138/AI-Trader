"""New results API with day-centric structure."""

from fastapi import APIRouter, Query, Depends
from typing import Optional, Literal
import json
import os
from datetime import datetime, timedelta

from api.database import Database

router = APIRouter()


def get_database() -> Database:
    """Dependency for database instance."""
    return Database()


def validate_and_resolve_dates(
    start_date: Optional[str],
    end_date: Optional[str]
) -> tuple[str, str]:
    """Validate and resolve date parameters.

    Args:
        start_date: Start date (YYYY-MM-DD) or None
        end_date: End date (YYYY-MM-DD) or None

    Returns:
        Tuple of (resolved_start_date, resolved_end_date)

    Raises:
        ValueError: If dates are invalid
    """
    # Default lookback days
    default_lookback = int(os.getenv("DEFAULT_RESULTS_LOOKBACK_DAYS", "30"))

    # Handle None cases
    if start_date is None and end_date is None:
        # Default to last N days
        end_dt = datetime.now()
        start_dt = end_dt - timedelta(days=default_lookback)
        return start_dt.strftime("%Y-%m-%d"), end_dt.strftime("%Y-%m-%d")

    if start_date is None:
        # Only end_date provided -> single date
        start_date = end_date

    if end_date is None:
        # Only start_date provided -> single date
        end_date = start_date

    # Validate date formats
    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")

        # Ensure strict YYYY-MM-DD format (e.g., reject "2025-1-16")
        if start_date != start_dt.strftime("%Y-%m-%d"):
            raise ValueError(f"Invalid date format. Expected YYYY-MM-DD")
        if end_date != end_dt.strftime("%Y-%m-%d"):
            raise ValueError(f"Invalid date format. Expected YYYY-MM-DD")
    except ValueError:
        raise ValueError(f"Invalid date format. Expected YYYY-MM-DD")

    # Validate order
    if start_dt > end_dt:
        raise ValueError("start_date must be <= end_date")

    # Validate not future
    now = datetime.now()
    if start_dt.date() > now.date() or end_dt.date() > now.date():
        raise ValueError("Cannot query future dates")

    return start_date, end_date


@router.get("/results")
async def get_results(
    job_id: Optional[str] = None,
    model: Optional[str] = None,
    date: Optional[str] = None,
    reasoning: Literal["none", "summary", "full"] = "none",
    db: Database = Depends(get_database)
):
    """Get trading results grouped by day.

    Args:
        job_id: Filter by simulation job ID
        model: Filter by model signature
        date: Filter by trading date (YYYY-MM-DD)
        reasoning: Include reasoning logs (none/summary/full)
        db: Database instance (injected)

    Returns:
        JSON with day-centric trading results and performance metrics
    """

    # Build query with filters
    query = "SELECT * FROM trading_days WHERE 1=1"
    params = []

    if job_id:
        query += " AND job_id = ?"
        params.append(job_id)

    if model:
        query += " AND model = ?"
        params.append(model)

    if date:
        query += " AND date = ?"
        params.append(date)

    query += " ORDER BY date ASC, model ASC"

    # Execute query
    cursor = db.connection.execute(query, params)

    # Format results
    formatted_results = []

    for row in cursor.fetchall():
        trading_day_id = row[0]

        # Build response object
        day_data = {
            "date": row[3],
            "model": row[2],
            "job_id": row[1],

            "starting_position": {
                "holdings": db.get_starting_holdings(trading_day_id),
                "cash": row[4],  # starting_cash
                "portfolio_value": row[5]  # starting_portfolio_value
            },

            "daily_metrics": {
                "profit": row[6],  # daily_profit
                "return_pct": row[7],  # daily_return_pct
                "days_since_last_trading": row[14] if len(row) > 14 else 1
            },

            "trades": db.get_actions(trading_day_id),

            "final_position": {
                "holdings": db.get_ending_holdings(trading_day_id),
                "cash": row[8],  # ending_cash
                "portfolio_value": row[9]  # ending_portfolio_value
            },

            "metadata": {
                "total_actions": row[12] if row[12] is not None else 0,
                "session_duration_seconds": row[13],
                "completed_at": row[16] if len(row) > 16 else None
            }
        }

        # Add reasoning if requested
        if reasoning == "summary":
            day_data["reasoning"] = row[10]  # reasoning_summary
        elif reasoning == "full":
            reasoning_full = row[11]  # reasoning_full
            day_data["reasoning"] = json.loads(reasoning_full) if reasoning_full else []
        else:
            day_data["reasoning"] = None

        formatted_results.append(day_data)

    return {
        "count": len(formatted_results),
        "results": formatted_results
    }
