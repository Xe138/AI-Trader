"""Unit tests for tools/price_tools.py utility functions."""
import pytest
from datetime import datetime
from tools.price_tools import get_yesterday_date, all_nasdaq_100_symbols


@pytest.mark.unit
class TestGetYesterdayDate:
    """Test get_yesterday_date function."""

    def test_get_yesterday_date_weekday(self):
        """Should return previous day for weekdays."""
        # Thursday -> Wednesday
        result = get_yesterday_date("2025-01-16")
        assert result == "2025-01-15"

    def test_get_yesterday_date_monday(self):
        """Should skip weekend when today is Monday."""
        # Monday 2025-01-20 -> Friday 2025-01-17
        result = get_yesterday_date("2025-01-20")
        assert result == "2025-01-17"

    def test_get_yesterday_date_sunday(self):
        """Should skip to Friday when today is Sunday."""
        # Sunday 2025-01-19 -> Friday 2025-01-17
        result = get_yesterday_date("2025-01-19")
        assert result == "2025-01-17"

    def test_get_yesterday_date_saturday(self):
        """Should skip to Friday when today is Saturday."""
        # Saturday 2025-01-18 -> Friday 2025-01-17
        result = get_yesterday_date("2025-01-18")
        assert result == "2025-01-17"

    def test_get_yesterday_date_tuesday(self):
        """Should return Monday for Tuesday."""
        # Tuesday 2025-01-21 -> Monday 2025-01-20
        result = get_yesterday_date("2025-01-21")
        assert result == "2025-01-20"

    def test_get_yesterday_date_format(self):
        """Should maintain YYYY-MM-DD format."""
        result = get_yesterday_date("2025-03-15")
        # Verify format
        datetime.strptime(result, "%Y-%m-%d")
        assert result == "2025-03-14"


@pytest.mark.unit
class TestNasdaqSymbols:
    """Test NASDAQ 100 symbols list."""

    def test_all_nasdaq_100_symbols_exists(self):
        """Should have NASDAQ 100 symbols list."""
        assert all_nasdaq_100_symbols is not None
        assert isinstance(all_nasdaq_100_symbols, list)

    def test_all_nasdaq_100_symbols_count(self):
        """Should have approximately 100 symbols."""
        # Allow some variance for index changes
        assert 95 <= len(all_nasdaq_100_symbols) <= 105

    def test_all_nasdaq_100_symbols_contains_major_stocks(self):
        """Should contain major tech stocks."""
        major_stocks = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "META"]
        for stock in major_stocks:
            assert stock in all_nasdaq_100_symbols

    def test_all_nasdaq_100_symbols_no_duplicates(self):
        """Should not contain duplicate symbols."""
        assert len(all_nasdaq_100_symbols) == len(set(all_nasdaq_100_symbols))

    def test_all_nasdaq_100_symbols_all_uppercase(self):
        """All symbols should be uppercase."""
        for symbol in all_nasdaq_100_symbols:
            assert symbol.isupper()
            assert symbol.isalpha() or symbol.isalnum()
