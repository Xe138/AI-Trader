"""New results API with day-centric structure."""

from fastapi import APIRouter, Query, Depends
from typing import Optional, Literal
import json

from api.database import Database

router = APIRouter()


def get_database() -> Database:
    """Dependency for database instance."""
    return Database()


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
