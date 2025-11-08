"""New results API with day-centric structure."""

from fastapi import APIRouter, Query, Depends, HTTPException
from typing import Optional, Literal
import json
import os
from datetime import datetime, timedelta

from api.database import Database
from api.routes.period_metrics import calculate_period_metrics

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
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    date: Optional[str] = Query(None, deprecated=True),
    reasoning: Literal["none", "summary", "full"] = "none",
    db: Database = Depends(get_database)
):
    """Get trading results with optional date range and portfolio performance metrics.

    Args:
        job_id: Filter by simulation job ID
        model: Filter by model signature
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        date: DEPRECATED - Use start_date/end_date instead
        reasoning: Include reasoning logs (none/summary/full). Ignored for date ranges.
        db: Database instance (injected)

    Returns:
        JSON with day-centric trading results and performance metrics
    """

    # Check for deprecated parameter
    if date is not None:
        raise HTTPException(
            status_code=422,
            detail="Parameter 'date' has been removed. Use 'start_date' and/or 'end_date' instead."
        )

    # Validate and resolve dates
    try:
        resolved_start, resolved_end = validate_and_resolve_dates(start_date, end_date)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Determine if single-date or range query
    is_single_date = resolved_start == resolved_end

    # Build query with filters
    query = "SELECT * FROM trading_days WHERE date >= ? AND date <= ?"
    params = [resolved_start, resolved_end]

    if job_id:
        query += " AND job_id = ?"
        params.append(job_id)

    if model:
        query += " AND model = ?"
        params.append(model)

    query += " ORDER BY model ASC, date ASC"

    # Execute query
    cursor = db.connection.execute(query, params)
    rows = cursor.fetchall()

    # Check if empty
    if not rows:
        raise HTTPException(
            status_code=404,
            detail="No trading data found for the specified filters"
        )

    # Group by model
    model_data = {}
    for row in rows:
        model_sig = row[2]  # model column
        if model_sig not in model_data:
            model_data[model_sig] = []
        model_data[model_sig].append(row)

    # Format results
    formatted_results = []

    for model_sig, model_rows in model_data.items():
        if is_single_date:
            # Single-date format (detailed)
            for row in model_rows:
                formatted_results.append(format_single_date_result(row, db, reasoning))
        else:
            # Range format (lightweight with metrics)
            formatted_results.append(format_range_result(model_sig, model_rows, db))

    return {
        "count": len(formatted_results),
        "results": formatted_results
    }


def format_single_date_result(row, db: Database, reasoning: str) -> dict:
    """Format single-date result (detailed format)."""
    trading_day_id = row[0]

    result = {
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
        result["reasoning"] = row[10]  # reasoning_summary
    elif reasoning == "full":
        reasoning_full = row[11]  # reasoning_full
        result["reasoning"] = json.loads(reasoning_full) if reasoning_full else []
    else:
        result["reasoning"] = None

    return result


def format_range_result(model_sig: str, rows: list, db: Database) -> dict:
    """Format date range result (lightweight with period metrics)."""
    # Trim edges: use actual min/max dates from data
    actual_start = rows[0][3]  # date from first row
    actual_end = rows[-1][3]   # date from last row

    # Extract daily portfolio values
    daily_values = [
        {
            "date": row[3],
            "portfolio_value": row[9]  # ending_portfolio_value
        }
        for row in rows
    ]

    # Get starting and ending values
    starting_value = rows[0][5]  # starting_portfolio_value from first day
    ending_value = rows[-1][9]   # ending_portfolio_value from last day
    trading_days = len(rows)

    # Calculate period metrics
    metrics = calculate_period_metrics(
        starting_value=starting_value,
        ending_value=ending_value,
        start_date=actual_start,
        end_date=actual_end,
        trading_days=trading_days
    )

    return {
        "model": model_sig,
        "start_date": actual_start,
        "end_date": actual_end,
        "daily_portfolio_values": daily_values,
        "period_metrics": metrics
    }
