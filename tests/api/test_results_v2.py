"""Tests for results_v2 endpoint date validation."""

import pytest
from datetime import datetime, timedelta
from api.routes.results_v2 import validate_and_resolve_dates


def test_validate_no_dates_provided():
    """Test default to last 30 days when no dates provided."""
    start, end = validate_and_resolve_dates(None, None)

    # Should default to last 30 days
    end_dt = datetime.strptime(end, "%Y-%m-%d")
    start_dt = datetime.strptime(start, "%Y-%m-%d")

    assert (end_dt - start_dt).days == 30
    assert end_dt.date() <= datetime.now().date()


def test_validate_only_start_date():
    """Test single date when only start_date provided."""
    start, end = validate_and_resolve_dates("2025-01-16", None)

    assert start == "2025-01-16"
    assert end == "2025-01-16"


def test_validate_only_end_date():
    """Test single date when only end_date provided."""
    start, end = validate_and_resolve_dates(None, "2025-01-16")

    assert start == "2025-01-16"
    assert end == "2025-01-16"


def test_validate_both_dates():
    """Test date range when both provided."""
    start, end = validate_and_resolve_dates("2025-01-16", "2025-01-20")

    assert start == "2025-01-16"
    assert end == "2025-01-20"


def test_validate_invalid_date_format():
    """Test error on invalid date format."""
    with pytest.raises(ValueError, match="Invalid date format"):
        validate_and_resolve_dates("2025-1-16", "2025-01-20")


def test_validate_start_after_end():
    """Test error when start_date > end_date."""
    with pytest.raises(ValueError, match="start_date must be <= end_date"):
        validate_and_resolve_dates("2025-01-20", "2025-01-16")


def test_validate_future_date():
    """Test error when dates are in future."""
    future = (datetime.now() + timedelta(days=10)).strftime("%Y-%m-%d")

    with pytest.raises(ValueError, match="Cannot query future dates"):
        validate_and_resolve_dates(future, future)
