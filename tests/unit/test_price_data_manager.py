"""
Unit tests for api/price_data_manager.py

Tests price data management, coverage detection, download prioritization,
and rate limit handling.
"""

import pytest
import json
import os
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock, call
from pathlib import Path
import tempfile
import sqlite3

from api.price_data_manager import (
    PriceDataManager,
    RateLimitError,
    DownloadError
)
from api.database import initialize_database, get_db_connection


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
    """Create temporary symbols config for testing."""
    symbols_data = {
        "symbols": ["AAPL", "MSFT", "GOOGL"],
        "description": "Test symbols",
        "total_symbols": 3
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
    """Create PriceDataManager instance with temp database and config."""
    return PriceDataManager(
        db_path=temp_db,
        symbols_config=temp_symbols_config,
        api_key="test_api_key"
    )


@pytest.fixture
def populated_db(temp_db):
    """Create database with sample price data."""
    conn = get_db_connection(temp_db)
    cursor = conn.cursor()

    # Insert sample price data for multiple symbols and dates
    test_data = [
        ("AAPL", "2025-01-20", 150.0, 155.0, 149.0, 154.0, 1000000),
        ("AAPL", "2025-01-21", 154.0, 156.0, 153.0, 155.0, 1100000),
        ("MSFT", "2025-01-20", 380.0, 385.0, 379.0, 383.0, 2000000),
        ("MSFT", "2025-01-21", 383.0, 387.0, 382.0, 386.0, 2100000),
        ("GOOGL", "2025-01-20", 140.0, 142.0, 139.0, 141.0, 1500000),
        # Note: GOOGL missing 2025-01-21
    ]

    created_at = datetime.utcnow().isoformat() + "Z"

    for symbol, date, open_p, high, low, close, volume in test_data:
        cursor.execute("""
            INSERT INTO price_data (symbol, date, open, high, low, close, volume, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (symbol, date, open_p, high, low, close, volume, created_at))

    # Insert coverage data
    cursor.execute("""
        INSERT INTO price_data_coverage (symbol, start_date, end_date, downloaded_at, source)
        VALUES
            ('AAPL', '2025-01-20', '2025-01-21', ?, 'test'),
            ('MSFT', '2025-01-20', '2025-01-21', ?, 'test'),
            ('GOOGL', '2025-01-20', '2025-01-20', ?, 'test')
    """, (created_at, created_at, created_at))

    conn.commit()
    conn.close()

    return temp_db


class TestPriceDataManagerInit:
    """Test PriceDataManager initialization."""

    def test_init_with_defaults(self, temp_db):
        """Test initialization with default parameters."""
        with patch.dict(os.environ, {"ALPHAADVANTAGE_API_KEY": "env_key"}):
            manager = PriceDataManager(db_path=temp_db)
            assert manager.db_path == temp_db
            assert manager.api_key == "env_key"
            assert manager.symbols_config == "configs/nasdaq100_symbols.json"

    def test_init_with_custom_params(self, temp_db, temp_symbols_config):
        """Test initialization with custom parameters."""
        manager = PriceDataManager(
            db_path=temp_db,
            symbols_config=temp_symbols_config,
            api_key="custom_key"
        )
        assert manager.db_path == temp_db
        assert manager.api_key == "custom_key"
        assert manager.symbols_config == temp_symbols_config

    def test_load_symbols_success(self, manager):
        """Test successful symbol loading from config."""
        assert manager.symbols == ["AAPL", "MSFT", "GOOGL"]

    def test_load_symbols_file_not_found(self, temp_db):
        """Test handling of missing symbols config file uses fallback."""
        manager = PriceDataManager(
            db_path=temp_db,
            symbols_config="nonexistent.json",
            api_key="test_key"
        )
        # Should use fallback symbols list
        assert len(manager.symbols) > 0
        assert "AAPL" in manager.symbols

    def test_load_symbols_invalid_json(self, temp_db):
        """Test handling of invalid JSON in symbols config."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("invalid json{")
            bad_config = f.name

        try:
            with pytest.raises(json.JSONDecodeError):
                PriceDataManager(
                    db_path=temp_db,
                    symbols_config=bad_config,
                    api_key="test_key"
                )
        finally:
            os.unlink(bad_config)

    def test_missing_api_key(self, temp_db, temp_symbols_config):
        """Test initialization without API key."""
        with patch.dict(os.environ, {}, clear=True):
            manager = PriceDataManager(
                db_path=temp_db,
                symbols_config=temp_symbols_config
            )
            assert manager.api_key is None


class TestGetSymbolDates:
    """Test get_symbol_dates method."""

    def test_get_symbol_dates_with_data(self, manager, populated_db):
        """Test retrieving dates for symbol with data."""
        manager.db_path = populated_db
        dates = manager.get_symbol_dates("AAPL")
        assert dates == {"2025-01-20", "2025-01-21"}

    def test_get_symbol_dates_no_data(self, manager):
        """Test retrieving dates for symbol without data."""
        dates = manager.get_symbol_dates("TSLA")
        assert dates == set()

    def test_get_symbol_dates_partial_data(self, manager, populated_db):
        """Test retrieving dates for symbol with partial data."""
        manager.db_path = populated_db
        dates = manager.get_symbol_dates("GOOGL")
        assert dates == {"2025-01-20"}


class TestGetMissingCoverage:
    """Test get_missing_coverage method."""

    def test_missing_coverage_empty_db(self, manager):
        """Test missing coverage with empty database."""
        missing = manager.get_missing_coverage("2025-01-20", "2025-01-21")

        # All symbols should be missing all dates
        assert "AAPL" in missing
        assert "MSFT" in missing
        assert "GOOGL" in missing
        assert missing["AAPL"] == {"2025-01-20", "2025-01-21"}

    def test_missing_coverage_partial_db(self, manager, populated_db):
        """Test missing coverage with partial data."""
        manager.db_path = populated_db
        missing = manager.get_missing_coverage("2025-01-20", "2025-01-21")

        # AAPL and MSFT have all dates, GOOGL missing 2025-01-21
        assert "AAPL" not in missing or len(missing["AAPL"]) == 0
        assert "MSFT" not in missing or len(missing["MSFT"]) == 0
        assert "GOOGL" in missing
        assert missing["GOOGL"] == {"2025-01-21"}

    def test_missing_coverage_complete_db(self, manager, populated_db):
        """Test missing coverage when all data available."""
        manager.db_path = populated_db
        missing = manager.get_missing_coverage("2025-01-20", "2025-01-20")

        # All symbols have 2025-01-20
        for symbol in ["AAPL", "MSFT", "GOOGL"]:
            assert symbol not in missing or len(missing[symbol]) == 0

    def test_missing_coverage_single_date(self, manager, populated_db):
        """Test missing coverage for single date."""
        manager.db_path = populated_db
        missing = manager.get_missing_coverage("2025-01-21", "2025-01-21")

        # Only GOOGL missing 2025-01-21
        assert "GOOGL" in missing
        assert missing["GOOGL"] == {"2025-01-21"}


class TestPrioritizeDownloads:
    """Test prioritize_downloads method."""

    def test_prioritize_single_symbol(self, manager):
        """Test prioritization with single symbol missing data."""
        missing_coverage = {"AAPL": {"2025-01-20", "2025-01-21"}}
        requested_dates = {"2025-01-20", "2025-01-21"}

        prioritized = manager.prioritize_downloads(missing_coverage, requested_dates)
        assert prioritized == ["AAPL"]

    def test_prioritize_multiple_symbols_equal_impact(self, manager):
        """Test prioritization with equal impact symbols."""
        missing_coverage = {
            "AAPL": {"2025-01-20", "2025-01-21"},
            "MSFT": {"2025-01-20", "2025-01-21"}
        }
        requested_dates = {"2025-01-20", "2025-01-21"}

        prioritized = manager.prioritize_downloads(missing_coverage, requested_dates)
        # Both should be included (order may vary)
        assert set(prioritized) == {"AAPL", "MSFT"}
        assert len(prioritized) == 2

    def test_prioritize_by_impact(self, manager):
        """Test prioritization by date completion impact."""
        missing_coverage = {
            "AAPL": {"2025-01-20", "2025-01-21", "2025-01-22"},  # High impact (3 dates)
            "MSFT": {"2025-01-20"},                               # Low impact (1 date)
            "GOOGL": {"2025-01-21", "2025-01-22"}                 # Medium impact (2 dates)
        }
        requested_dates = {"2025-01-20", "2025-01-21", "2025-01-22"}

        prioritized = manager.prioritize_downloads(missing_coverage, requested_dates)

        # AAPL should be first (highest impact)
        assert prioritized[0] == "AAPL"
        # GOOGL should be second
        assert prioritized[1] == "GOOGL"
        # MSFT should be last (lowest impact)
        assert prioritized[2] == "MSFT"

    def test_prioritize_excludes_irrelevant_dates(self, manager):
        """Test that symbols with no impact on requested dates are excluded."""
        missing_coverage = {
            "AAPL": {"2025-01-20"},           # Relevant
            "MSFT": {"2025-01-25", "2025-01-26"}  # Not relevant
        }
        requested_dates = {"2025-01-20", "2025-01-21"}

        prioritized = manager.prioritize_downloads(missing_coverage, requested_dates)

        # Only AAPL should be included
        assert prioritized == ["AAPL"]


class TestGetAvailableTradingDates:
    """Test get_available_trading_dates method."""

    def test_available_dates_empty_db(self, manager):
        """Test with empty database returns no dates."""
        available = manager.get_available_trading_dates("2025-01-20", "2025-01-21")
        assert available == []

    def test_available_dates_complete_range(self, manager, populated_db):
        """Test with complete data for all symbols in range."""
        manager.db_path = populated_db
        available = manager.get_available_trading_dates("2025-01-20", "2025-01-20")
        assert available == ["2025-01-20"]

    def test_available_dates_partial_range(self, manager, populated_db):
        """Test with partial data (some symbols missing some dates)."""
        manager.db_path = populated_db
        available = manager.get_available_trading_dates("2025-01-20", "2025-01-21")

        # 2025-01-20 has all symbols, 2025-01-21 missing GOOGL
        assert available == ["2025-01-20"]

    def test_available_dates_filters_incomplete(self, manager, populated_db):
        """Test that dates with incomplete symbol coverage are filtered."""
        manager.db_path = populated_db
        available = manager.get_available_trading_dates("2025-01-21", "2025-01-21")

        # 2025-01-21 is missing GOOGL, so not complete
        assert available == []


class TestDownloadSymbol:
    """Test _download_symbol method (Alpha Vantage API calls)."""

    @patch('api.price_data_manager.requests.get')
    def test_download_success(self, mock_get, manager):
        """Test successful symbol download."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "Meta Data": {"2. Symbol": "AAPL"},
            "Time Series (Daily)": {
                "2025-01-20": {
                    "1. open": "150.00",
                    "2. high": "155.00",
                    "3. low": "149.00",
                    "4. close": "154.00",
                    "5. volume": "1000000"
                }
            }
        }
        mock_get.return_value = mock_response

        data = manager._download_symbol("AAPL")

        assert data["Meta Data"]["2. Symbol"] == "AAPL"
        assert "2025-01-20" in data["Time Series (Daily)"]
        mock_get.assert_called_once()

    @patch('api.price_data_manager.requests.get')
    def test_download_rate_limit(self, mock_get, manager):
        """Test rate limit detection."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "Note": "Thank you for using Alpha Vantage! Our standard API call frequency is 25 calls per day."
        }
        mock_get.return_value = mock_response

        with pytest.raises(RateLimitError):
            manager._download_symbol("AAPL")

    @patch('api.price_data_manager.requests.get')
    def test_download_http_error(self, mock_get, manager):
        """Test HTTP error handling."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = Exception("Server error")
        mock_get.return_value = mock_response

        with pytest.raises(DownloadError):
            manager._download_symbol("AAPL")

    @patch('api.price_data_manager.requests.get')
    def test_download_invalid_response(self, mock_get, manager):
        """Test handling of invalid API response."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}  # Missing required fields
        mock_get.return_value = mock_response

        with pytest.raises(DownloadError, match="Invalid response format"):
            manager._download_symbol("AAPL")

    def test_download_missing_api_key(self, manager):
        """Test download without API key."""
        manager.api_key = None

        with pytest.raises(DownloadError, match="API key not configured"):
            manager._download_symbol("AAPL")


class TestStoreSymbolData:
    """Test _store_symbol_data method."""

    def test_store_symbol_data_success(self, manager):
        """Test successful data storage."""
        data = {
            "Meta Data": {"2. Symbol": "AAPL"},
            "Time Series (Daily)": {
                "2025-01-20": {
                    "1. open": "150.00",
                    "2. high": "155.00",
                    "3. low": "149.00",
                    "4. close": "154.00",
                    "5. volume": "1000000"
                },
                "2025-01-21": {
                    "1. open": "154.00",
                    "2. high": "156.00",
                    "3. low": "153.00",
                    "4. close": "155.00",
                    "5. volume": "1100000"
                }
            }
        }
        requested_dates = {"2025-01-20", "2025-01-21"}

        stored_dates = manager._store_symbol_data("AAPL", data, requested_dates)

        # Returns list, not set
        assert set(stored_dates) == {"2025-01-20", "2025-01-21"}

        # Verify data in database
        conn = get_db_connection(manager.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM price_data WHERE symbol = 'AAPL'")
        count = cursor.fetchone()[0]
        assert count == 2
        conn.close()

    def test_store_filters_by_requested_dates(self, manager):
        """Test that only requested dates are stored."""
        data = {
            "Meta Data": {"2. Symbol": "AAPL"},
            "Time Series (Daily)": {
                "2025-01-20": {
                    "1. open": "150.00",
                    "2. high": "155.00",
                    "3. low": "149.00",
                    "4. close": "154.00",
                    "5. volume": "1000000"
                },
                "2025-01-21": {
                    "1. open": "154.00",
                    "2. high": "156.00",
                    "3. low": "153.00",
                    "4. close": "155.00",
                    "5. volume": "1100000"
                }
            }
        }
        requested_dates = {"2025-01-20"}  # Only request one date

        stored_dates = manager._store_symbol_data("AAPL", data, requested_dates)

        # Returns list, not set
        assert set(stored_dates) == {"2025-01-20"}

        # Verify only one date in database
        conn = get_db_connection(manager.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM price_data WHERE symbol = 'AAPL'")
        count = cursor.fetchone()[0]
        assert count == 1
        conn.close()


class TestUpdateCoverage:
    """Test _update_coverage method."""

    def test_update_coverage_new_symbol(self, manager):
        """Test coverage tracking for new symbol."""
        manager._update_coverage("AAPL", "2025-01-20", "2025-01-21")

        conn = get_db_connection(manager.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT symbol, start_date, end_date, source
            FROM price_data_coverage
            WHERE symbol = 'AAPL'
        """)
        row = cursor.fetchone()
        conn.close()

        assert row is not None
        assert row[0] == "AAPL"
        assert row[1] == "2025-01-20"
        assert row[2] == "2025-01-21"
        assert row[3] == "alpha_vantage"

    def test_update_coverage_existing_symbol(self, manager, populated_db):
        """Test coverage update for existing symbol."""
        manager.db_path = populated_db

        # Update with new range
        manager._update_coverage("AAPL", "2025-01-22", "2025-01-23")

        conn = get_db_connection(manager.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM price_data_coverage WHERE symbol = 'AAPL'
        """)
        count = cursor.fetchone()[0]
        conn.close()

        # Should have 2 coverage records now
        assert count == 2


class TestDownloadMissingDataPrioritized:
    """Test download_missing_data_prioritized method (integration)."""

    @patch.object(PriceDataManager, '_download_symbol')
    @patch.object(PriceDataManager, '_store_symbol_data')
    @patch.object(PriceDataManager, '_update_coverage')
    def test_download_all_success(self, mock_update, mock_store, mock_download, manager):
        """Test successful download of all missing symbols."""
        missing_coverage = {
            "AAPL": {"2025-01-20"},
            "MSFT": {"2025-01-20"}
        }
        requested_dates = {"2025-01-20"}

        mock_download.return_value = {"Meta Data": {}, "Time Series (Daily)": {}}
        mock_store.return_value = {"2025-01-20"}

        result = manager.download_missing_data_prioritized(missing_coverage, requested_dates)

        assert result["success"] is True
        assert len(result["downloaded"]) == 2
        assert result["rate_limited"] is False
        assert mock_download.call_count == 2

    @patch.object(PriceDataManager, '_download_symbol')
    def test_download_rate_limited_mid_process(self, mock_download, manager):
        """Test graceful handling of rate limit during downloads."""
        missing_coverage = {
            "AAPL": {"2025-01-20"},
            "MSFT": {"2025-01-20"},
            "GOOGL": {"2025-01-20"}
        }
        requested_dates = {"2025-01-20"}

        # First call succeeds, second raises rate limit
        mock_download.side_effect = [
            {"Meta Data": {"2. Symbol": "AAPL"}, "Time Series (Daily)": {"2025-01-20": {}}},
            RateLimitError("Rate limit reached")
        ]

        with patch.object(manager, '_store_symbol_data', return_value={"2025-01-20"}):
            with patch.object(manager, '_update_coverage'):
                result = manager.download_missing_data_prioritized(missing_coverage, requested_dates)

        assert result["success"] is True  # Partial success
        assert len(result["downloaded"]) == 1
        assert result["rate_limited"] is True
        assert len(result["failed"]) == 2  # MSFT and GOOGL not downloaded

    @patch.object(PriceDataManager, '_download_symbol')
    def test_download_all_failed(self, mock_download, manager):
        """Test handling when all downloads fail."""
        missing_coverage = {"AAPL": {"2025-01-20"}}
        requested_dates = {"2025-01-20"}

        mock_download.side_effect = DownloadError("Network error")

        result = manager.download_missing_data_prioritized(missing_coverage, requested_dates)

        assert result["success"] is False
        assert len(result["downloaded"]) == 0
        assert len(result["failed"]) == 1
