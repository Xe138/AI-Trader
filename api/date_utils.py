"""
Date range utilities for simulation date management.

This module provides:
- Date range expansion
- Date range validation
- Trading day detection
"""

import os
from datetime import datetime, timedelta
from typing import List


def expand_date_range(start_date: str, end_date: str) -> List[str]:
    """
    Expand date range into list of all dates (inclusive).

    Args:
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)

    Returns:
        Sorted list of dates in range

    Raises:
        ValueError: If dates are invalid or start > end
    """
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")

    if start > end:
        raise ValueError(f"start_date ({start_date}) must be <= end_date ({end_date})")

    dates = []
    current = start

    while current <= end:
        dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)

    return dates


def validate_date_range(
    start_date: str,
    end_date: str,
    max_days: int = 30
) -> None:
    """
    Validate date range for simulation.

    Args:
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        max_days: Maximum allowed days in range

    Raises:
        ValueError: If validation fails
    """
    # Parse dates
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError as e:
        raise ValueError(f"Invalid date format: {e}")

    # Check order
    if start > end:
        raise ValueError(f"start_date ({start_date}) must be <= end_date ({end_date})")

    # Check range size
    days = (end - start).days + 1
    if days > max_days:
        raise ValueError(
            f"Date range too large: {days} days (max: {max_days}). "
            f"Reduce range or increase MAX_SIMULATION_DAYS."
        )

    # Check not in future
    today = datetime.now().date()
    if end.date() > today:
        raise ValueError(f"end_date ({end_date}) cannot be in the future")


def get_max_simulation_days() -> int:
    """
    Get maximum simulation days from environment.

    Returns:
        Maximum days allowed in simulation range
    """
    return int(os.getenv("MAX_SIMULATION_DAYS", "30"))
