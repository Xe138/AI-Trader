"""Period metrics calculation for date range queries."""

from datetime import datetime


def calculate_period_metrics(
    starting_value: float,
    ending_value: float,
    start_date: str,
    end_date: str,
    trading_days: int
) -> dict:
    """Calculate period return and annualized return.

    Args:
        starting_value: Portfolio value at start of period
        ending_value: Portfolio value at end of period
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        trading_days: Number of actual trading days in period

    Returns:
        Dict with period_return_pct, annualized_return_pct, calendar_days, trading_days
    """
    # Calculate calendar days (inclusive)
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    calendar_days = (end_dt - start_dt).days + 1

    # Calculate period return
    if starting_value == 0:
        period_return_pct = 0.0
    else:
        period_return_pct = ((ending_value - starting_value) / starting_value) * 100

    # Calculate annualized return
    if calendar_days == 0 or starting_value == 0 or ending_value <= 0:
        annualized_return_pct = 0.0
    else:
        # Formula: ((ending / starting) ** (365 / days) - 1) * 100
        annualized_return_pct = ((ending_value / starting_value) ** (365 / calendar_days) - 1) * 100

    return {
        "starting_portfolio_value": starting_value,
        "ending_portfolio_value": ending_value,
        "period_return_pct": round(period_return_pct, 2),
        "annualized_return_pct": round(annualized_return_pct, 2),
        "calendar_days": calendar_days,
        "trading_days": trading_days
    }
