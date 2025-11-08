"""Tests for period metrics calculations."""

from datetime import datetime
from api.routes.period_metrics import calculate_period_metrics


def test_calculate_period_metrics_basic():
    """Test basic period metrics calculation."""
    metrics = calculate_period_metrics(
        starting_value=10000.0,
        ending_value=10500.0,
        start_date="2025-01-16",
        end_date="2025-01-20",
        trading_days=3
    )

    assert metrics["starting_portfolio_value"] == 10000.0
    assert metrics["ending_portfolio_value"] == 10500.0
    assert metrics["period_return_pct"] == 5.0
    assert metrics["calendar_days"] == 5
    assert metrics["trading_days"] == 3
    # annualized_return = ((10500/10000) ** (365/5) - 1) * 100 = ~3422%
    assert 3400 < metrics["annualized_return_pct"] < 3450


def test_calculate_period_metrics_zero_return():
    """Test period metrics when no change."""
    metrics = calculate_period_metrics(
        starting_value=10000.0,
        ending_value=10000.0,
        start_date="2025-01-16",
        end_date="2025-01-16",
        trading_days=1
    )

    assert metrics["period_return_pct"] == 0.0
    assert metrics["annualized_return_pct"] == 0.0
    assert metrics["calendar_days"] == 1


def test_calculate_period_metrics_negative_return():
    """Test period metrics with loss."""
    metrics = calculate_period_metrics(
        starting_value=10000.0,
        ending_value=9500.0,
        start_date="2025-01-16",
        end_date="2025-01-23",
        trading_days=5
    )

    assert metrics["period_return_pct"] == -5.0
    assert metrics["calendar_days"] == 8
    # Negative annualized return
    assert metrics["annualized_return_pct"] < 0
