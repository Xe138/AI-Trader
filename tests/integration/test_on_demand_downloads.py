"""
Integration tests for on-demand price data downloads.

Tests the complete flow from missing coverage detection through download
and storage, including priority-based download strategy and rate limit handling.
"""

import pytest
import os
import tempfile
import json
from unittest.mock import patch, Mock
from datetime import datetime

from api.price_data_manager import PriceDataManager, RateLimitError, DownloadError
from api.database import initialize_database, get_db_connection, db_connection
from api.date_utils import expand_date_range


@pytest.fixture
def temp_db():
    """Create temporary database for testing."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.db', delete=False) as f:
        db_path = f.name

    initialize_database(db_path)
    yield db_path

    # Cleanup
    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture
def temp_symbols_config():
    """Create temporary symbols config with small symbol set."""
    symbols_data = {
        "symbols": ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"],
        "description": "Test symbols",
        "total_symbols": 5
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(symbols_data, f)
        config_path = f.name

    yield config_path

    # Cleanup
    if os.path.exists(config_path):
        os.unlink(config_path)


@pytest.fixture
def manager(temp_db, temp_symbols_config):
    """Create PriceDataManager instance."""
    return PriceDataManager(
        db_path=temp_db,
        symbols_config=temp_symbols_config,
        api_key="test_api_key"
    )


@pytest.fixture
def mock_alpha_vantage_response():
    """Create mock Alpha Vantage API response."""
    def create_response(symbol: str, dates: list):
        """Create response for given symbol and dates."""
        time_series = {}
        for date in dates:
            time_series[date] = {
                "1. open": "150.00",
                "2. high": "155.00",
                "3. low": "149.00",
                "4. close": "154.00",
                "5. volume": "1000000"
            }

        return {
            "Meta Data": {
                "1. Information": "Daily Prices",
                "2. Symbol": symbol,
                "3. Last Refreshed": dates[0] if dates else "2025-01-20"
            },
            "Time Series (Daily)": time_series
        }
    return create_response


class TestEndToEndDownload:
    """Test complete download workflow."""

    @patch('api.price_data_manager.requests.get')
    def test_download_missing_data_success(self, mock_get, manager, mock_alpha_vantage_response):
        """Test successful download of missing price data."""
        # Setup: Mock API responses for each symbol
        dates = ["2025-01-20", "2025-01-21"]

        def mock_response_factory(url, **kwargs):
            """Return appropriate mock response based on symbol in params."""
            symbol = kwargs.get('params', {}).get('symbol', 'AAPL')
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_alpha_vantage_response(symbol, dates)
            return mock_response

        mock_get.side_effect = mock_response_factory

        # Test: Request date range with no existing data
        missing = manager.get_missing_coverage("2025-01-20", "2025-01-21")

        # All symbols should be missing both dates
        assert len(missing) == 5
        for symbol in ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]:
            assert symbol in missing
            assert missing[symbol] == {"2025-01-20", "2025-01-21"}

        # Download missing data
        requested_dates = set(dates)
        result = manager.download_missing_data_prioritized(missing, requested_dates)

        # Should successfully download all symbols
        assert result["success"] is True
        assert len(result["downloaded"]) == 5
        assert result["rate_limited"] is False
        assert set(result["dates_completed"]) == requested_dates

        # Verify data in database
        available_dates = manager.get_available_trading_dates("2025-01-20", "2025-01-21")
        assert available_dates == ["2025-01-20", "2025-01-21"]

        # Verify coverage tracking
        with db_connection(manager.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM price_data_coverage")
            coverage_count = cursor.fetchone()[0]
            assert coverage_count == 5  # One record per symbol

    @patch('api.price_data_manager.requests.get')
    def test_download_with_partial_existing_data(self, mock_get, manager, mock_alpha_vantage_response):
        """Test download when some data already exists."""
        dates = ["2025-01-20", "2025-01-21", "2025-01-22"]

        # Prepopulate database with some data (AAPL and MSFT for first two dates)
        conn = get_db_connection(manager.db_path)
        cursor = conn.cursor()
        created_at = datetime.utcnow().isoformat() + "Z"

        for symbol in ["AAPL", "MSFT"]:
            for date in dates[:2]:  # Only first two dates
                cursor.execute("""
                    INSERT INTO price_data (symbol, date, open, high, low, close, volume, created_at)
                    VALUES (?, ?, 150.0, 155.0, 149.0, 154.0, 1000000, ?)
                """, (symbol, date, created_at))

            cursor.execute("""
                INSERT INTO price_data_coverage (symbol, start_date, end_date, downloaded_at, source)
                VALUES (?, ?, ?, ?, 'test')
            """, (symbol, dates[0], dates[1], created_at))

        conn.commit()
        conn.close()

        # Mock API for remaining downloads
        def mock_response_factory(url, **kwargs):
            symbol = kwargs.get('params', {}).get('symbol', 'GOOGL')
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_alpha_vantage_response(symbol, dates)
            return mock_response

        mock_get.side_effect = mock_response_factory

        # Check missing coverage
        missing = manager.get_missing_coverage(dates[0], dates[2])

        # AAPL and MSFT should be missing only date 3
        # GOOGL, AMZN, NVDA should be missing all dates
        assert missing["AAPL"] == {dates[2]}
        assert missing["MSFT"] == {dates[2]}
        assert missing["GOOGL"] == set(dates)

        # Download missing data
        requested_dates = set(dates)
        result = manager.download_missing_data_prioritized(missing, requested_dates)

        assert result["success"] is True
        assert len(result["downloaded"]) == 5

        # Verify all dates are now available
        available_dates = manager.get_available_trading_dates(dates[0], dates[2])
        assert set(available_dates) == set(dates)

    @patch('api.price_data_manager.requests.get')
    def test_priority_based_download_order(self, mock_get, manager, mock_alpha_vantage_response):
        """Test that downloads prioritize symbols that complete the most dates."""
        dates = ["2025-01-20", "2025-01-21", "2025-01-22"]

        # Prepopulate with specific pattern to create different priorities
        conn = get_db_connection(manager.db_path)
        cursor = conn.cursor()
        created_at = datetime.utcnow().isoformat() + "Z"

        # AAPL: Has date 1 only (missing 2 dates)
        cursor.execute("""
            INSERT INTO price_data (symbol, date, open, high, low, close, volume, created_at)
            VALUES ('AAPL', ?, 150.0, 155.0, 149.0, 154.0, 1000000, ?)
        """, (dates[0], created_at))

        # MSFT: Has date 1 and 2 (missing 1 date)
        for date in dates[:2]:
            cursor.execute("""
                INSERT INTO price_data (symbol, date, open, high, low, close, volume, created_at)
                VALUES ('MSFT', ?, 150.0, 155.0, 149.0, 154.0, 1000000, ?)
            """, (date, created_at))

        # GOOGL, AMZN, NVDA: No data (missing 3 dates)
        conn.commit()
        conn.close()

        # Track download order
        download_order = []

        def mock_response_factory(url, **kwargs):
            symbol = kwargs.get('params', {}).get('symbol')
            download_order.append(symbol)
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_alpha_vantage_response(symbol, dates)
            return mock_response

        mock_get.side_effect = mock_response_factory

        # Download missing data
        missing = manager.get_missing_coverage(dates[0], dates[2])
        requested_dates = set(dates)
        result = manager.download_missing_data_prioritized(missing, requested_dates)

        assert result["success"] is True

        # Verify symbols with highest impact were downloaded first
        # GOOGL, AMZN, NVDA should be first (3 dates each)
        # Then AAPL (2 dates)
        # Then MSFT (1 date)
        first_three = set(download_order[:3])
        assert first_three == {"GOOGL", "AMZN", "NVDA"}
        assert download_order[3] == "AAPL"
        assert download_order[4] == "MSFT"


class TestRateLimitHandling:
    """Test rate limit handling during downloads."""

    @patch('api.price_data_manager.requests.get')
    def test_rate_limit_stops_downloads(self, mock_get, manager, mock_alpha_vantage_response):
        """Test that rate limit error stops further downloads."""
        dates = ["2025-01-20"]

        # First symbol succeeds, second hits rate limit
        responses = [
            # AAPL succeeds (or whichever symbol is first in priority)
            Mock(status_code=200, json=lambda: mock_alpha_vantage_response("AAPL", dates)),
            # MSFT hits rate limit
            Mock(status_code=200, json=lambda: {"Note": "Thank you for using Alpha Vantage! Our standard API call frequency is 25 calls per day."}),
        ]

        mock_get.side_effect = responses

        missing = manager.get_missing_coverage("2025-01-20", "2025-01-20")
        requested_dates = {"2025-01-20"}

        result = manager.download_missing_data_prioritized(missing, requested_dates)

        # Partial success - one symbol downloaded
        assert result["success"] is True  # At least one succeeded
        assert len(result["downloaded"]) >= 1
        assert result["rate_limited"] is True
        assert len(result["failed"]) >= 1

        # Completed dates should be empty (need all symbols for complete date)
        assert len(result["dates_completed"]) == 0

    @patch('api.price_data_manager.requests.get')
    def test_graceful_handling_of_mixed_failures(self, mock_get, manager, mock_alpha_vantage_response):
        """Test handling of mix of successes, failures, and rate limits."""
        dates = ["2025-01-20"]

        call_count = [0]

        def response_factory(url, **kwargs):
            """Return different responses for different calls."""
            call_count[0] += 1
            mock_response = Mock()

            if call_count[0] == 1:
                # First call succeeds
                mock_response.status_code = 200
                mock_response.json.return_value = mock_alpha_vantage_response("AAPL", dates)
            elif call_count[0] == 2:
                # Second call fails with server error
                mock_response.status_code = 500
                mock_response.raise_for_status.side_effect = Exception("Server error")
            else:
                # Third call hits rate limit
                mock_response.status_code = 200
                mock_response.json.return_value = {"Note": "rate limit exceeded"}

            return mock_response

        mock_get.side_effect = response_factory

        missing = manager.get_missing_coverage("2025-01-20", "2025-01-20")
        requested_dates = {"2025-01-20"}

        result = manager.download_missing_data_prioritized(missing, requested_dates)

        # Should have handled errors gracefully
        assert "downloaded" in result
        assert "failed" in result
        assert len(result["downloaded"]) >= 1


class TestCoverageTracking:
    """Test coverage tracking functionality."""

    @patch('api.price_data_manager.requests.get')
    def test_coverage_updated_after_download(self, mock_get, manager, mock_alpha_vantage_response):
        """Test that coverage table is updated after successful download."""
        dates = ["2025-01-20", "2025-01-21"]

        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: mock_alpha_vantage_response("AAPL", dates)
        )

        # Download for single symbol
        data = manager._download_symbol("AAPL")
        stored_dates = manager._store_symbol_data("AAPL", data, set(dates))
        manager._update_coverage("AAPL", dates[0], dates[1])

        # Verify coverage was recorded
        with db_connection(manager.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT symbol, start_date, end_date, source
                FROM price_data_coverage
                WHERE symbol = 'AAPL'
            """)
            row = cursor.fetchone()

        assert row is not None
        assert row[0] == "AAPL"
        assert row[1] == dates[0]
        assert row[2] == dates[1]
        assert row[3] == "alpha_vantage"

    def test_coverage_gap_detection_accuracy(self, manager):
        """Test accuracy of coverage gap detection."""
        # Populate database with specific pattern
        conn = get_db_connection(manager.db_path)
        cursor = conn.cursor()
        created_at = datetime.utcnow().isoformat() + "Z"

        test_data = [
            ("AAPL", "2025-01-20"),
            ("AAPL", "2025-01-21"),
            ("AAPL", "2025-01-23"),  # Gap on 2025-01-22
            ("MSFT", "2025-01-20"),
            ("MSFT", "2025-01-22"),  # Gap on 2025-01-21
        ]

        for symbol, date in test_data:
            cursor.execute("""
                INSERT INTO price_data (symbol, date, open, high, low, close, volume, created_at)
                VALUES (?, ?, 150.0, 155.0, 149.0, 154.0, 1000000, ?)
            """, (symbol, date, created_at))

        conn.commit()
        conn.close()

        # Check for gaps in range
        missing = manager.get_missing_coverage("2025-01-20", "2025-01-23")

        # AAPL should be missing 2025-01-22
        assert "2025-01-22" in missing["AAPL"]
        assert "2025-01-20" not in missing["AAPL"]

        # MSFT should be missing 2025-01-21 and 2025-01-23
        assert "2025-01-21" in missing["MSFT"]
        assert "2025-01-23" in missing["MSFT"]
        assert "2025-01-20" not in missing["MSFT"]


class TestDataValidation:
    """Test data validation during download and storage."""

    @patch('api.price_data_manager.requests.get')
    def test_invalid_response_handling(self, mock_get, manager):
        """Test handling of invalid API responses."""
        # Mock response with missing required fields
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: {"invalid": "response"}
        )

        with pytest.raises(DownloadError, match="Invalid response format"):
            manager._download_symbol("AAPL")

    @patch('api.price_data_manager.requests.get')
    def test_empty_time_series_handling(self, mock_get, manager):
        """Test handling of empty time series data (should raise error for missing data)."""
        # API returns valid structure but no time series
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: {
                "Meta Data": {"2. Symbol": "AAPL"},
                # Missing "Time Series (Daily)" key
            }
        )

        with pytest.raises(DownloadError, match="Invalid response format"):
            manager._download_symbol("AAPL")

    def test_date_filtering_during_storage(self, manager):
        """Test that only requested dates are stored."""
        # Create mock data with dates outside requested range
        data = {
            "Meta Data": {"2. Symbol": "AAPL"},
            "Time Series (Daily)": {
                "2025-01-15": {"1. open": "145.00", "2. high": "150.00", "3. low": "144.00", "4. close": "149.00", "5. volume": "1000000"},
                "2025-01-20": {"1. open": "150.00", "2. high": "155.00", "3. low": "149.00", "4. close": "154.00", "5. volume": "1000000"},
                "2025-01-21": {"1. open": "154.00", "2. high": "156.00", "3. low": "153.00", "4. close": "155.00", "5. volume": "1100000"},
                "2025-01-25": {"1. open": "156.00", "2. high": "158.00", "3. low": "155.00", "4. close": "157.00", "5. volume": "1200000"},
            }
        }

        # Request only specific dates
        requested_dates = {"2025-01-20", "2025-01-21"}
        stored_dates = manager._store_symbol_data("AAPL", data, requested_dates)

        # Only requested dates should be stored
        assert set(stored_dates) == requested_dates

        # Verify in database
        with db_connection(manager.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT date FROM price_data WHERE symbol = 'AAPL' ORDER BY date")
            db_dates = [row[0] for row in cursor.fetchall()]

        assert db_dates == ["2025-01-20", "2025-01-21"]
