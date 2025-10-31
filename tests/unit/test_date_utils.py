"""
Unit tests for api/date_utils.py

Tests date range expansion, validation, and utility functions.
"""

import pytest
from datetime import datetime, timedelta
from api.date_utils import (
    expand_date_range,
    validate_date_range,
    get_max_simulation_days
)


class TestExpandDateRange:
    """Test expand_date_range function."""

    def test_single_day(self):
        """Test single day range (start == end)."""
        result = expand_date_range("2025-01-20", "2025-01-20")
        assert result == ["2025-01-20"]

    def test_multi_day_range(self):
        """Test multiple day range."""
        result = expand_date_range("2025-01-20", "2025-01-22")
        assert result == ["2025-01-20", "2025-01-21", "2025-01-22"]

    def test_week_range(self):
        """Test week-long range."""
        result = expand_date_range("2025-01-20", "2025-01-26")
        assert len(result) == 7
        assert result[0] == "2025-01-20"
        assert result[-1] == "2025-01-26"

    def test_chronological_order(self):
        """Test dates are in chronological order."""
        result = expand_date_range("2025-01-20", "2025-01-25")
        for i in range(len(result) - 1):
            assert result[i] < result[i + 1]

    def test_invalid_order(self):
        """Test error when start > end."""
        with pytest.raises(ValueError, match="must be <= end_date"):
            expand_date_range("2025-01-25", "2025-01-20")

    def test_invalid_date_format(self):
        """Test error with invalid date format."""
        with pytest.raises(ValueError):
            expand_date_range("01-20-2025", "01-21-2025")

    def test_month_boundary(self):
        """Test range spanning month boundary."""
        result = expand_date_range("2025-01-30", "2025-02-02")
        assert result == ["2025-01-30", "2025-01-31", "2025-02-01", "2025-02-02"]

    def test_year_boundary(self):
        """Test range spanning year boundary."""
        result = expand_date_range("2024-12-30", "2025-01-02")
        assert len(result) == 4
        assert "2024-12-31" in result
        assert "2025-01-01" in result


class TestValidateDateRange:
    """Test validate_date_range function."""

    def test_valid_single_day(self):
        """Test valid single day range."""
        # Should not raise
        validate_date_range("2025-01-20", "2025-01-20", max_days=30)

    def test_valid_multi_day(self):
        """Test valid multi-day range."""
        # Should not raise
        validate_date_range("2025-01-20", "2025-01-25", max_days=30)

    def test_max_days_boundary(self):
        """Test exactly at max days limit."""
        # 30 days total (inclusive)
        start = "2025-01-01"
        end = "2025-01-30"
        # Should not raise
        validate_date_range(start, end, max_days=30)

    def test_exceeds_max_days(self):
        """Test exceeds max days limit."""
        start = "2025-01-01"
        end = "2025-02-01"  # 32 days
        with pytest.raises(ValueError, match="Date range too large: 32 days"):
            validate_date_range(start, end, max_days=30)

    def test_invalid_order(self):
        """Test start > end."""
        with pytest.raises(ValueError, match="must be <= end_date"):
            validate_date_range("2025-01-25", "2025-01-20", max_days=30)

    def test_future_date_rejected(self):
        """Test future dates are rejected."""
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        next_week = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")

        with pytest.raises(ValueError, match="cannot be in the future"):
            validate_date_range(tomorrow, next_week, max_days=30)

    def test_today_allowed(self):
        """Test today's date is allowed."""
        today = datetime.now().strftime("%Y-%m-%d")
        # Should not raise
        validate_date_range(today, today, max_days=30)

    def test_past_dates_allowed(self):
        """Test past dates are allowed."""
        # Should not raise
        validate_date_range("2020-01-01", "2020-01-10", max_days=30)

    def test_invalid_date_format(self):
        """Test invalid date format raises error."""
        with pytest.raises(ValueError, match="Invalid date format"):
            validate_date_range("01-20-2025", "01-21-2025", max_days=30)

    def test_custom_max_days(self):
        """Test custom max_days parameter."""
        # Should raise with max_days=5
        with pytest.raises(ValueError, match="Date range too large: 10 days"):
            validate_date_range("2025-01-01", "2025-01-10", max_days=5)


class TestGetMaxSimulationDays:
    """Test get_max_simulation_days function."""

    def test_default_value(self, monkeypatch):
        """Test default value when env var not set."""
        monkeypatch.delenv("MAX_SIMULATION_DAYS", raising=False)
        result = get_max_simulation_days()
        assert result == 30

    def test_env_var_override(self, monkeypatch):
        """Test environment variable override."""
        monkeypatch.setenv("MAX_SIMULATION_DAYS", "60")
        result = get_max_simulation_days()
        assert result == 60

    def test_env_var_string_to_int(self, monkeypatch):
        """Test env var is converted to int."""
        monkeypatch.setenv("MAX_SIMULATION_DAYS", "100")
        result = get_max_simulation_days()
        assert isinstance(result, int)
        assert result == 100
