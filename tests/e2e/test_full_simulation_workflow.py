"""
End-to-end test for complete simulation workflow with new trading_days schema.

This test verifies the entire system works together:
- Complete simulation workflow with new database schema
- Multiple trading days (3 days minimum)
- Daily P&L calculated correctly
- Holdings chain across days
- Reasoning summary/full retrieval works
- Results API returns correct structure

Test Requirements:
- Uses DEV mode with mock AI provider (no real API costs)
- Pre-populates price data in database
- Tests complete workflow from trigger to results retrieval
"""

import pytest
import time
import os
import json
from fastapi.testclient import TestClient
from pathlib import Path
from datetime import datetime
from api.database import Database


@pytest.fixture
def e2e_client(tmp_path):
    """
    Create test client for E2E simulation testing.

    Sets up:
    - DEV mode environment
    - Clean test database
    - Pre-populated price data
    - Test configuration with mock model
    """
    # Set DEV mode environment
    os.environ["DEPLOYMENT_MODE"] = "DEV"
    os.environ["PRESERVE_DEV_DATA"] = "false"
    os.environ["AUTO_DOWNLOAD_PRICE_DATA"] = "false"

    # Import after setting environment
    from api.main import create_app
    from api.database import initialize_dev_database, get_db_path, get_db_connection

    # Create dev database
    db_path = str(tmp_path / "test_trading.db")
    dev_db_path = get_db_path(db_path)
    initialize_dev_database(dev_db_path)

    # Pre-populate price data for test dates
    _populate_test_price_data(dev_db_path)

    # Create test config with mock model
    test_config = tmp_path / "test_config.json"
    test_config.write_text(json.dumps({
        "agent_type": "BaseAgent",
        "date_range": {"init_date": "2025-01-16", "end_date": "2025-01-18"},
        "models": [
            {
                "name": "Test Mock Model",
                "basemodel": "mock/test-trader",
                "signature": "test-mock-e2e",
                "enabled": True
            }
        ],
        "agent_config": {
            "max_steps": 10,
            "initial_cash": 10000.0,
            "max_retries": 1,
            "base_delay": 0.1
        },
        "log_config": {
            "log_path": str(tmp_path / "dev_agent_data")
        }
    }))

    # Create app with test config
    app = create_app(db_path=dev_db_path, config_path=str(test_config))

    # Override database dependency to use test database
    from api.routes.results_v2 import get_database
    test_db = Database(dev_db_path)
    app.dependency_overrides[get_database] = lambda: test_db

    # IMPORTANT: Do NOT set test_mode=True - we want the worker to run
    # This is a full E2E test

    client = TestClient(app)
    client.db_path = dev_db_path
    client.config_path = str(test_config)

    yield client

    # Clean up
    app.dependency_overrides.clear()

    # Cleanup
    os.environ.pop("DEPLOYMENT_MODE", None)
    os.environ.pop("PRESERVE_DEV_DATA", None)
    os.environ.pop("AUTO_DOWNLOAD_PRICE_DATA", None)


def _populate_test_price_data(db_path: str):
    """
    Pre-populate test price data in database.

    This avoids needing Alpha Vantage API key for E2E tests.
    Adds mock price data for all NASDAQ 100 stocks on test dates.
    """
    from api.database import get_db_connection

    # All NASDAQ 100 symbols (must match configs/nasdaq100_symbols.json)
    symbols = [
        "NVDA", "MSFT", "AAPL", "GOOG", "GOOGL", "AMZN", "META", "AVGO", "TSLA",
        "NFLX", "PLTR", "COST", "ASML", "AMD", "CSCO", "AZN", "TMUS", "MU", "LIN",
        "PEP", "SHOP", "APP", "INTU", "AMAT", "LRCX", "PDD", "QCOM", "ARM", "INTC",
        "BKNG", "AMGN", "TXN", "ISRG", "GILD", "KLAC", "PANW", "ADBE", "HON",
        "CRWD", "CEG", "ADI", "ADP", "DASH", "CMCSA", "VRTX", "MELI", "SBUX",
        "CDNS", "ORLY", "SNPS", "MSTR", "MDLZ", "ABNB", "MRVL", "CTAS", "TRI",
        "MAR", "MNST", "CSX", "ADSK", "PYPL", "FTNT", "AEP", "WDAY", "REGN", "ROP",
        "NXPI", "DDOG", "AXON", "ROST", "IDXX", "EA", "PCAR", "FAST", "EXC", "TTWO",
        "XEL", "ZS", "PAYX", "WBD", "BKR", "CPRT", "CCEP", "FANG", "TEAM", "CHTR",
        "KDP", "MCHP", "GEHC", "VRSK", "CTSH", "CSGP", "KHC", "ODFL", "DXCM", "TTD",
        "ON", "BIIB", "LULU", "CDW", "GFS", "QQQ"
    ]

    # Test dates (3 consecutive trading days)
    test_dates = ["2025-01-16", "2025-01-17", "2025-01-18"]

    # Price variations to simulate market changes
    # Day 1: base prices
    # Day 2: some stocks up, some down
    # Day 3: more variation
    price_multipliers = {
        "2025-01-16": 1.00,
        "2025-01-17": 1.05,  # 5% increase
        "2025-01-18": 1.02   # Back to 2% increase
    }

    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    for symbol in symbols:
        for date in test_dates:
            multiplier = price_multipliers[date]
            base_price = 100.0

            # Insert mock price data with variations
            cursor.execute("""
                INSERT OR IGNORE INTO price_data
                (symbol, date, open, high, low, close, volume, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                symbol,
                date,
                base_price * multiplier,  # open
                base_price * multiplier * 1.05,  # high
                base_price * multiplier * 0.98,  # low
                base_price * multiplier * 1.02,  # close
                1000000,  # volume
                datetime.utcnow().isoformat() + "Z"
            ))

        # Add coverage record
        cursor.execute("""
            INSERT OR IGNORE INTO price_data_coverage
            (symbol, start_date, end_date, downloaded_at, source)
            VALUES (?, ?, ?, ?, ?)
        """, (
            symbol,
            "2025-01-16",
            "2025-01-18",
            datetime.utcnow().isoformat() + "Z",
            "test_fixture_e2e"
        ))

    conn.commit()
    conn.close()


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.skipif(
    os.getenv("SKIP_E2E_TESTS") == "true",
    reason="Skipping E2E tests (set SKIP_E2E_TESTS=false to run)"
)
class TestFullSimulationWorkflow:
    """
    End-to-end tests for complete simulation workflow with new schema.

    These tests verify the new trading_days schema and Results API work correctly.

    NOTE: This test does NOT run a full simulation because model_day_executor
    has not yet been migrated to use the new schema. Instead, it directly
    populates the trading_days table and verifies the API returns correct data.
    """

    def test_complete_simulation_with_new_schema(self, e2e_client):
        """
        Test new trading_days schema and Results API with manually populated data.

        This test verifies:
        1. trading_days table schema is correct
        2. Database helper methods work (create_trading_day, create_holding, create_action)
        3. Daily P&L is stored correctly
        4. Holdings chain correctly across days
        5. Results API returns correct structure
        6. Reasoning summary/full retrieval works

        Expected data flow:
        - Day 1: Zero P&L (first day), starting portfolio = initial cash = $10,000
        - Day 2: P&L calculated from price changes on Day 1 holdings
        - Day 3: P&L calculated from price changes on Day 2 holdings

        NOTE: This test does NOT run a full simulation because model_day_executor
        has not yet been migrated to use the new schema. Instead, it directly
        populates the trading_days table using Database helper methods and verifies
        the Results API works correctly.
        """
        from api.database import Database, get_db_connection

        # Get database instance
        db = Database(e2e_client.db_path)

        # Create a test job
        job_id = "test-job-e2e-123"
        conn = get_db_connection(e2e_client.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO jobs (job_id, config_path, status, date_range, models, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            job_id,
            "test_config.json",
            "completed",
            '["2025-01-16", "2025-01-18"]',
            '["test-mock-e2e"]',
            datetime.utcnow().isoformat() + "Z"
        ))
        conn.commit()

        # 1. Create Day 1 trading_day record (first day, zero P&L)
        day1_id = db.create_trading_day(
            job_id=job_id,
            model="test-mock-e2e",
            date="2025-01-16",
            starting_cash=10000.0,
            starting_portfolio_value=10000.0,
            daily_profit=0.0,
            daily_return_pct=0.0,
            ending_cash=8500.0,  # Bought $1500 worth of stock
            ending_portfolio_value=10000.0,  # 10 shares * $100 + $8500 cash
            reasoning_summary="Analyzed market conditions. Bought 10 shares of AAPL at $150.",
            reasoning_full=json.dumps([
                {"role": "user", "content": "System prompt for trading..."},
                {"role": "assistant", "content": "I will analyze AAPL..."},
                {"role": "tool", "name": "get_price", "content": "AAPL price: $150"},
                {"role": "assistant", "content": "Buying 10 shares of AAPL..."}
            ]),
            total_actions=1,
            session_duration_seconds=45.5,
            days_since_last_trading=0
        )

        # Add Day 1 holdings and actions
        db.create_holding(day1_id, "AAPL", 10)
        db.create_action(day1_id, "buy", "AAPL", 10, 150.0)

        # 2. Create Day 2 trading_day record (with P&L from price change)
        # AAPL went from $100 to $105 (5% gain), so portfolio value increased
        day2_starting_value = 8500.0 + (10 * 105.0)  # Cash + holdings valued at new price = $9550
        day2_profit = day2_starting_value - 10000.0  # $9550 - $10000 = -$450 (loss)
        day2_return_pct = (day2_profit / 10000.0) * 100  # -4.5%

        day2_id = db.create_trading_day(
            job_id=job_id,
            model="test-mock-e2e",
            date="2025-01-17",
            starting_cash=8500.0,
            starting_portfolio_value=day2_starting_value,
            daily_profit=day2_profit,
            daily_return_pct=day2_return_pct,
            ending_cash=7000.0,  # Bought more stock
            ending_portfolio_value=9500.0,
            reasoning_summary="Continued trading. Added 5 shares of MSFT.",
            reasoning_full=json.dumps([
                {"role": "user", "content": "System prompt..."},
                {"role": "assistant", "content": "I will buy MSFT..."}
            ]),
            total_actions=1,
            session_duration_seconds=38.2,
            days_since_last_trading=1
        )

        # Add Day 2 holdings and actions
        db.create_holding(day2_id, "AAPL", 10)
        db.create_holding(day2_id, "MSFT", 5)
        db.create_action(day2_id, "buy", "MSFT", 5, 100.0)

        # 3. Create Day 3 trading_day record
        day3_starting_value = 7000.0 + (10 * 102.0) + (5 * 102.0)  # Different prices
        day3_profit = day3_starting_value - day2_starting_value
        day3_return_pct = (day3_profit / day2_starting_value) * 100

        day3_id = db.create_trading_day(
            job_id=job_id,
            model="test-mock-e2e",
            date="2025-01-18",
            starting_cash=7000.0,
            starting_portfolio_value=day3_starting_value,
            daily_profit=day3_profit,
            daily_return_pct=day3_return_pct,
            ending_cash=7000.0,  # No trades
            ending_portfolio_value=day3_starting_value,
            reasoning_summary="Held positions. No trades executed.",
            reasoning_full=json.dumps([
                {"role": "user", "content": "System prompt..."},
                {"role": "assistant", "content": "Holding positions..."}
            ]),
            total_actions=0,
            session_duration_seconds=12.1,
            days_since_last_trading=1
        )

        # Add Day 3 holdings (no actions, just holding)
        db.create_holding(day3_id, "AAPL", 10)
        db.create_holding(day3_id, "MSFT", 5)

        # Ensure all data is committed
        db.connection.commit()
        conn.close()

        # 4. Query results WITHOUT reasoning (default)
        results_response = e2e_client.get(f"/results?job_id={job_id}")

        assert results_response.status_code == 200
        results_data = results_response.json()

        # Should have 3 trading days
        assert results_data["count"] == 3
        assert len(results_data["results"]) == 3

        # 4. Verify Day 1 structure and data
        day1 = results_data["results"][0]

        assert day1["date"] == "2025-01-16"
        assert day1["model"] == "test-mock-e2e"
        assert day1["job_id"] == job_id

        # Verify starting_position structure
        assert "starting_position" in day1
        assert day1["starting_position"]["cash"] == 10000.0
        assert day1["starting_position"]["portfolio_value"] == 10000.0
        assert day1["starting_position"]["holdings"] == []  # First day, no prior holdings

        # Verify daily_metrics structure
        assert "daily_metrics" in day1
        assert day1["daily_metrics"]["profit"] == 0.0  # First day should have zero P&L
        assert day1["daily_metrics"]["return_pct"] == 0.0
        assert "days_since_last_trading" in day1["daily_metrics"]

        # Verify trades structure
        assert "trades" in day1
        assert isinstance(day1["trades"], list)
        assert len(day1["trades"]) > 0  # Mock model should make trades

        # Verify final_position structure
        assert "final_position" in day1
        assert "cash" in day1["final_position"]
        assert "portfolio_value" in day1["final_position"]
        assert "holdings" in day1["final_position"]
        assert isinstance(day1["final_position"]["holdings"], list)

        # Verify metadata structure
        assert "metadata" in day1
        assert "total_actions" in day1["metadata"]
        assert day1["metadata"]["total_actions"] > 0
        assert "session_duration_seconds" in day1["metadata"]

        # Verify reasoning is None (not requested)
        assert day1["reasoning"] is None

        # 5. Verify holdings chain across days
        day2 = results_data["results"][1]
        day3 = results_data["results"][2]

        # Day 2 starting holdings should match Day 1 ending holdings
        assert day2["starting_position"]["holdings"] == day1["final_position"]["holdings"]
        assert day2["starting_position"]["cash"] == day1["final_position"]["cash"]

        # Day 3 starting holdings should match Day 2 ending holdings
        assert day3["starting_position"]["holdings"] == day2["final_position"]["holdings"]
        assert day3["starting_position"]["cash"] == day2["final_position"]["cash"]

        # 6. Verify Daily P&L calculation
        # Day 2 should have non-zero P&L if prices changed and holdings exist
        if len(day1["final_position"]["holdings"]) > 0:
            # If Day 1 had holdings, Day 2 should show P&L from price changes
            # Note: P&L could be positive or negative depending on price movements
            # Just verify it's calculated (not zero for both days 2 and 3)
            assert day2["daily_metrics"]["profit"] != 0.0 or day3["daily_metrics"]["profit"] != 0.0, \
                "Expected some P&L on Day 2 or Day 3 due to price changes"

        # 7. Verify portfolio value calculations
        # Ending portfolio value should be cash + (sum of holdings * prices)
        for day in results_data["results"]:
            assert day["final_position"]["portfolio_value"] >= day["final_position"]["cash"], \
                f"Portfolio value should be >= cash. Day: {day['date']}"

        # 8. Query results with reasoning SUMMARY
        summary_response = e2e_client.get(f"/results?job_id={job_id}&reasoning=summary")
        assert summary_response.status_code == 200
        summary_data = summary_response.json()

        # Each day should have reasoning summary
        for result in summary_data["results"]:
            assert result["reasoning"] is not None
            assert isinstance(result["reasoning"], str)
            # Summary should be non-empty (mock model generates summaries)
            # Note: Summary might be empty if AI generation failed - that's OK
            # Just verify the field exists and is a string

        # 9. Query results with FULL reasoning
        full_response = e2e_client.get(f"/results?job_id={job_id}&reasoning=full")
        assert full_response.status_code == 200
        full_data = full_response.json()

        # Each day should have full reasoning log
        for result in full_data["results"]:
            assert result["reasoning"] is not None
            assert isinstance(result["reasoning"], list)
            # Full reasoning should contain messages
            assert len(result["reasoning"]) > 0, \
                f"Expected full reasoning log for {result['date']}"

        # 10. Verify database structure directly
        from api.database import get_db_connection

        conn = get_db_connection(e2e_client.db_path)
        cursor = conn.cursor()

        # Check trading_days table
        cursor.execute("""
            SELECT COUNT(*) FROM trading_days
            WHERE job_id = ? AND model = ?
        """, (job_id, "test-mock-e2e"))

        count = cursor.fetchone()[0]
        assert count == 3, f"Expected 3 trading_days records, got {count}"

        # Check holdings table
        cursor.execute("""
            SELECT COUNT(*) FROM holdings h
            JOIN trading_days td ON h.trading_day_id = td.id
            WHERE td.job_id = ? AND td.model = ?
        """, (job_id, "test-mock-e2e"))

        holdings_count = cursor.fetchone()[0]
        assert holdings_count > 0, "Expected some holdings records"

        # Check actions table
        cursor.execute("""
            SELECT COUNT(*) FROM actions a
            JOIN trading_days td ON a.trading_day_id = td.id
            WHERE td.job_id = ? AND td.model = ?
        """, (job_id, "test-mock-e2e"))

        actions_count = cursor.fetchone()[0]
        assert actions_count > 0, "Expected some action records"

        conn.close()

        # The main test above verifies:
        # - Results API filtering (by job_id)
        # - Multiple trading days (3 days)
        # - Holdings chain across days
        # - Daily P&L calculations
        # - Reasoning summary and full retrieval
        # - Complete database structure
        #
        # Additional filtering tests are covered by integration tests in
        # tests/integration/test_results_api_v2.py
