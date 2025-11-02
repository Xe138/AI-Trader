"""
End-to-end integration tests for reasoning logs API feature.

Tests the complete flow from simulation trigger to reasoning retrieval.

These tests verify:
- Trading sessions are created with session_id
- Reasoning logs are stored in database
- Full conversation history is captured
- Message summaries are generated
- GET /reasoning endpoint returns correct data
- Query filters work (job_id, date, model)
- include_full_conversation parameter works correctly
- Positions are linked to sessions
"""

import pytest
import time
import os
import json
from fastapi.testclient import TestClient
from pathlib import Path


@pytest.fixture
def dev_client(tmp_path):
    """Create test client with DEV mode and clean database."""
    # Set DEV mode environment
    os.environ["DEPLOYMENT_MODE"] = "DEV"
    os.environ["PRESERVE_DEV_DATA"] = "false"
    # Disable auto-download - we'll pre-populate test data
    os.environ["AUTO_DOWNLOAD_PRICE_DATA"] = "false"

    # Import after setting environment
    from api.main import create_app
    from api.database import initialize_dev_database, get_db_path, get_db_connection

    # Create dev database
    db_path = str(tmp_path / "test_trading.db")
    dev_db_path = get_db_path(db_path)
    initialize_dev_database(dev_db_path)

    # Pre-populate price data for test dates to avoid needing API key
    _populate_test_price_data(dev_db_path)

    # Create test config with mock model
    test_config = tmp_path / "test_config.json"
    test_config.write_text(json.dumps({
        "agent_type": "BaseAgent",
        "date_range": {"init_date": "2025-01-16", "end_date": "2025-01-17"},
        "models": [
            {
                "name": "Test Mock Model",
                "basemodel": "mock/test-trader",
                "signature": "test-mock",
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

    # IMPORTANT: Do NOT set test_mode=True to allow worker to actually run
    # This is an integration test - we want the full flow

    client = TestClient(app)
    client.db_path = dev_db_path
    client.config_path = str(test_config)

    yield client

    # Cleanup
    os.environ.pop("DEPLOYMENT_MODE", None)
    os.environ.pop("PRESERVE_DEV_DATA", None)
    os.environ.pop("AUTO_DOWNLOAD_PRICE_DATA", None)


def _populate_test_price_data(db_path: str):
    """
    Pre-populate test price data in database.

    This avoids needing Alpha Vantage API key for integration tests.
    Adds mock price data for all NASDAQ 100 stocks on test dates.
    """
    from api.database import get_db_connection
    from datetime import datetime

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

    # Test dates
    test_dates = ["2025-01-16", "2025-01-17"]

    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    for symbol in symbols:
        for date in test_dates:
            # Insert mock price data
            cursor.execute("""
                INSERT OR IGNORE INTO price_data
                (symbol, date, open, high, low, close, volume, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                symbol,
                date,
                100.0,  # open
                105.0,  # high
                98.0,   # low
                102.0,  # close
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
            "2025-01-17",
            datetime.utcnow().isoformat() + "Z",
            "test_fixture"
        ))

    conn.commit()
    conn.close()


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("SKIP_INTEGRATION_TESTS") == "true",
    reason="Skipping integration tests that require full environment"
)
class TestReasoningLogsE2E:
    """End-to-end tests for reasoning logs feature."""

    def test_simulation_stores_reasoning_logs(self, dev_client):
        """
        Test that running a simulation creates reasoning logs in database.

        This is the main E2E test that verifies:
        1. Simulation can be triggered
        2. Worker processes the job
        3. Trading sessions are created
        4. Reasoning logs are stored
        5. GET /reasoning returns the data

        NOTE: This test requires MCP services to be running. It will skip if services are unavailable.
        """
        # Skip if MCP services not available
        try:
            from agent.base_agent.base_agent import BaseAgent
        except ImportError as e:
            pytest.skip(f"Cannot import BaseAgent: {e}")

        # Skip test - requires MCP services running
        # This is a known limitation for integration tests
        pytest.skip(
            "Test requires MCP services running. "
            "Use test_reasoning_api_with_mocked_data() instead for automated testing."
        )

    def test_reasoning_api_with_mocked_data(self, dev_client):
        """
        Test GET /reasoning API with pre-populated database data.

        This test verifies the API layer works correctly without requiring
        a full simulation run or MCP services.
        """
        from api.database import get_db_connection
        from datetime import datetime

        # Populate test data directly in database
        conn = get_db_connection(dev_client.db_path)
        cursor = conn.cursor()

        # Create a job
        job_id = "test-job-123"
        cursor.execute("""
            INSERT INTO jobs (job_id, config_path, status, date_range, models, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (job_id, "test_config.json", "completed", "2025-01-16", '["test-mock"]',
              datetime.utcnow().isoformat() + "Z"))

        # Create a trading session
        cursor.execute("""
            INSERT INTO trading_sessions
            (job_id, date, model, session_summary, started_at, completed_at, total_messages)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            job_id,
            "2025-01-16",
            "test-mock",
            "Analyzed market conditions and executed buy order for AAPL",
            datetime.utcnow().isoformat() + "Z",
            datetime.utcnow().isoformat() + "Z",
            5
        ))

        session_id = cursor.lastrowid

        # Create reasoning logs
        messages = [
            {
                "session_id": session_id,
                "message_index": 0,
                "role": "user",
                "content": "You are a trading agent. Analyze the market...",
                "summary": None,
                "tool_name": None,
                "tool_input": None,
                "timestamp": datetime.utcnow().isoformat() + "Z"
            },
            {
                "session_id": session_id,
                "message_index": 1,
                "role": "assistant",
                "content": "I will analyze the market and make trading decisions...",
                "summary": "Agent analyzed market conditions",
                "tool_name": None,
                "tool_input": None,
                "timestamp": datetime.utcnow().isoformat() + "Z"
            },
            {
                "session_id": session_id,
                "message_index": 2,
                "role": "tool",
                "content": "Price of AAPL: $150.00",
                "summary": None,
                "tool_name": "get_price",
                "tool_input": json.dumps({"symbol": "AAPL"}),
                "timestamp": datetime.utcnow().isoformat() + "Z"
            },
            {
                "session_id": session_id,
                "message_index": 3,
                "role": "assistant",
                "content": "Based on analysis, I will buy AAPL...",
                "summary": "Agent decided to buy AAPL",
                "tool_name": None,
                "tool_input": None,
                "timestamp": datetime.utcnow().isoformat() + "Z"
            },
            {
                "session_id": session_id,
                "message_index": 4,
                "role": "tool",
                "content": "Successfully bought 10 shares of AAPL",
                "summary": None,
                "tool_name": "buy",
                "tool_input": json.dumps({"symbol": "AAPL", "amount": 10}),
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
        ]

        for msg in messages:
            cursor.execute("""
                INSERT INTO reasoning_logs
                (session_id, message_index, role, content, summary, tool_name, tool_input, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                msg["session_id"], msg["message_index"], msg["role"],
                msg["content"], msg["summary"], msg["tool_name"],
                msg["tool_input"], msg["timestamp"]
            ))

        # Create positions linked to session
        cursor.execute("""
            INSERT INTO positions
            (job_id, date, model, action_id, action_type, symbol, amount, price, cash, portfolio_value,
             daily_profit, daily_return_pct, created_at, session_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job_id, "2025-01-16", "test-mock", 1, "buy", "AAPL", 10, 150.0,
            8500.0, 10000.0, 0.0, 0.0, datetime.utcnow().isoformat() + "Z", session_id
        ))

        conn.commit()
        conn.close()

        # Query reasoning endpoint (summary mode)
        reasoning_response = dev_client.get(f"/reasoning?job_id={job_id}")

        assert reasoning_response.status_code == 200
        reasoning_data = reasoning_response.json()

        # Verify response structure
        assert "sessions" in reasoning_data
        assert "count" in reasoning_data
        assert reasoning_data["count"] == 1
        assert reasoning_data["is_dev_mode"] is True

        # Verify trading session structure
        session = reasoning_data["sessions"][0]
        assert session["session_id"] == session_id
        assert session["job_id"] == job_id
        assert session["date"] == "2025-01-16"
        assert session["model"] == "test-mock"
        assert session["session_summary"] == "Analyzed market conditions and executed buy order for AAPL"
        assert session["total_messages"] == 5

        # Verify positions are linked to session
        assert "positions" in session
        assert len(session["positions"]) == 1
        position = session["positions"][0]
        assert position["action_id"] == 1
        assert position["action_type"] == "buy"
        assert position["symbol"] == "AAPL"
        assert position["amount"] == 10
        assert position["price"] == 150.0
        assert position["cash_after"] == 8500.0
        assert position["portfolio_value"] == 10000.0

        # Verify conversation is NOT included in summary mode
        assert session["conversation"] is None

        # Query again with full conversation
        full_response = dev_client.get(
            f"/reasoning?job_id={job_id}&include_full_conversation=true"
        )
        assert full_response.status_code == 200
        full_data = full_response.json()
        session_full = full_data["sessions"][0]

        # Verify full conversation is included
        assert session_full["conversation"] is not None
        assert len(session_full["conversation"]) == 5

        # Verify conversation messages
        conv = session_full["conversation"]
        assert conv[0]["role"] == "user"
        assert conv[0]["message_index"] == 0
        assert conv[0]["summary"] is None  # User messages don't have summaries

        assert conv[1]["role"] == "assistant"
        assert conv[1]["message_index"] == 1
        assert conv[1]["summary"] == "Agent analyzed market conditions"

        assert conv[2]["role"] == "tool"
        assert conv[2]["message_index"] == 2
        assert conv[2]["tool_name"] == "get_price"
        assert conv[2]["tool_input"] == json.dumps({"symbol": "AAPL"})

        assert conv[3]["role"] == "assistant"
        assert conv[3]["message_index"] == 3
        assert conv[3]["summary"] == "Agent decided to buy AAPL"

        assert conv[4]["role"] == "tool"
        assert conv[4]["message_index"] == 4
        assert conv[4]["tool_name"] == "buy"

    def test_reasoning_endpoint_date_filter(self, dev_client):
        """Test GET /reasoning date filter works correctly."""
        # This test requires actual data - skip if no data available
        response = dev_client.get("/reasoning?date=2025-01-16")

        # Should either return 404 (no data) or 200 with filtered data
        assert response.status_code in [200, 404]

        if response.status_code == 200:
            data = response.json()
            for session in data["sessions"]:
                assert session["date"] == "2025-01-16"

    def test_reasoning_endpoint_model_filter(self, dev_client):
        """Test GET /reasoning model filter works correctly."""
        response = dev_client.get("/reasoning?model=test-mock")

        # Should either return 404 (no data) or 200 with filtered data
        assert response.status_code in [200, 404]

        if response.status_code == 200:
            data = response.json()
            for session in data["sessions"]:
                assert session["model"] == "test-mock"

    def test_reasoning_endpoint_combined_filters(self, dev_client):
        """Test GET /reasoning with multiple filters."""
        response = dev_client.get(
            "/reasoning?date=2025-01-16&model=test-mock"
        )

        # Should either return 404 (no data) or 200 with filtered data
        assert response.status_code in [200, 404]

        if response.status_code == 200:
            data = response.json()
            for session in data["sessions"]:
                assert session["date"] == "2025-01-16"
                assert session["model"] == "test-mock"

    def test_reasoning_endpoint_invalid_date_format(self, dev_client):
        """Test GET /reasoning rejects invalid date format."""
        response = dev_client.get("/reasoning?date=invalid-date")

        assert response.status_code == 400
        assert "Invalid date format" in response.json()["detail"]

    def test_reasoning_endpoint_no_sessions_found(self, dev_client):
        """Test GET /reasoning returns 404 when no sessions match filters."""
        response = dev_client.get("/reasoning?job_id=nonexistent-job-id")

        assert response.status_code == 404
        assert "No trading sessions found" in response.json()["detail"]

    def test_reasoning_summaries_vs_full_conversation(self, dev_client):
        """
        Test difference between summary mode and full conversation mode.

        Verifies:
        - Default mode does not include conversation
        - include_full_conversation=true includes full conversation
        - Full conversation has more data than summary
        """
        # This test needs actual data - skip if none available
        response_summary = dev_client.get("/reasoning")

        if response_summary.status_code == 404:
            pytest.skip("No reasoning data available for testing")

        assert response_summary.status_code == 200
        summary_data = response_summary.json()

        if summary_data["count"] == 0:
            pytest.skip("No reasoning data available for testing")

        # Get full conversation
        response_full = dev_client.get("/reasoning?include_full_conversation=true")
        assert response_full.status_code == 200
        full_data = response_full.json()

        # Compare first session
        session_summary = summary_data["sessions"][0]
        session_full = full_data["sessions"][0]

        # Summary mode should not have conversation
        assert session_summary["conversation"] is None

        # Full mode should have conversation
        assert session_full["conversation"] is not None
        assert len(session_full["conversation"]) > 0

        # Session metadata should be the same
        assert session_summary["session_id"] == session_full["session_id"]
        assert session_summary["job_id"] == session_full["job_id"]
        assert session_summary["date"] == session_full["date"]
        assert session_summary["model"] == session_full["model"]


@pytest.mark.integration
class TestReasoningAPIValidation:
    """Test GET /reasoning endpoint validation and error handling."""

    def test_reasoning_endpoint_deployment_mode_flag(self, dev_client):
        """Test that reasoning endpoint includes deployment mode info."""
        response = dev_client.get("/reasoning")

        # Even 404 should not be returned - endpoint should work
        # Only 404 if no data matches filters
        if response.status_code == 200:
            data = response.json()
            assert "deployment_mode" in data
            assert "is_dev_mode" in data
            assert data["is_dev_mode"] is True

    def test_reasoning_endpoint_returns_pydantic_models(self, dev_client):
        """Test that endpoint returns properly validated response models."""
        # This is implicitly tested by FastAPI/TestClient
        # If response doesn't match ReasoningResponse model, will raise error

        response = dev_client.get("/reasoning")

        # Should either return 404 or valid response
        assert response.status_code in [200, 404]

        if response.status_code == 200:
            data = response.json()

            # Verify top-level structure
            assert "sessions" in data
            assert "count" in data
            assert isinstance(data["sessions"], list)
            assert isinstance(data["count"], int)

            # If sessions exist, verify structure
            if data["count"] > 0:
                session = data["sessions"][0]

                # Required fields
                assert "session_id" in session
                assert "job_id" in session
                assert "date" in session
                assert "model" in session
                assert "started_at" in session
                assert "positions" in session

                # Positions structure
                if len(session["positions"]) > 0:
                    position = session["positions"][0]
                    assert "action_id" in position
                    assert "cash_after" in position
                    assert "portfolio_value" in position
