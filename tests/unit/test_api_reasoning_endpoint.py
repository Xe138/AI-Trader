"""
Unit tests for GET /reasoning API endpoint.

Coverage target: 95%+

Tests verify:
- Filtering by job_id, date, and model
- Full conversation vs summaries only
- Error handling (404, 400)
- Deployment mode info in responses
"""

import pytest
from datetime import datetime
from api.database import get_db_connection


@pytest.fixture
def sample_trading_session(clean_db):
    """Create a sample trading session with positions and reasoning logs."""
    conn = get_db_connection(clean_db)
    cursor = conn.cursor()

    # Create job
    cursor.execute("""
        INSERT INTO jobs (job_id, config_path, status, date_range, models, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        "test-job-123",
        "configs/test.json",
        "completed",
        '["2025-10-02"]',
        '["gpt-5"]',
        "2025-10-02T10:00:00Z"
    ))

    # Create trading session
    cursor.execute("""
        INSERT INTO trading_sessions (job_id, date, model, session_summary, started_at, completed_at, total_messages)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        "test-job-123",
        "2025-10-02",
        "gpt-5",
        "Analyzed AI infrastructure market. Bought NVDA and GOOGL based on secular AI trends.",
        "2025-10-02T10:00:00Z",
        "2025-10-02T10:05:23Z",
        4
    ))

    session_id = cursor.lastrowid

    # Create positions linked to session
    cursor.execute("""
        INSERT INTO positions (
            job_id, date, model, action_id, action_type, symbol, amount, price,
            cash, portfolio_value, daily_profit, daily_return_pct, session_id, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        "test-job-123", "2025-10-02", "gpt-5", 1, "buy", "NVDA", 10, 189.60,
        8104.00, 10000.00, 0.0, 0.0, session_id, "2025-10-02T10:05:00Z"
    ))

    cursor.execute("""
        INSERT INTO positions (
            job_id, date, model, action_id, action_type, symbol, amount, price,
            cash, portfolio_value, daily_profit, daily_return_pct, session_id, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        "test-job-123", "2025-10-02", "gpt-5", 2, "buy", "GOOGL", 6, 245.15,
        6633.10, 10104.00, 104.00, 1.04, session_id, "2025-10-02T10:05:10Z"
    ))

    # Create reasoning logs
    cursor.execute("""
        INSERT INTO reasoning_logs (session_id, message_index, role, content, summary, timestamp)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        session_id, 0, "user",
        "Please analyze and update today's (2025-10-02) positions.",
        None,
        "2025-10-02T10:00:00Z"
    ))

    cursor.execute("""
        INSERT INTO reasoning_logs (session_id, message_index, role, content, summary, timestamp)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        session_id, 1, "assistant",
        "Key intermediate steps\n\n- Read yesterday's positions...",
        "Analyzed market conditions and decided to buy NVDA (10 shares) and GOOGL (6 shares).",
        "2025-10-02T10:05:20Z"
    ))

    cursor.execute("""
        INSERT INTO reasoning_logs (session_id, message_index, role, content, summary, tool_name, tool_input, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        session_id, 2, "tool",
        "Successfully bought 10 shares of NVDA at $189.60",
        None,
        "trade",
        '{"action": "buy", "symbol": "NVDA", "amount": 10}',
        "2025-10-02T10:05:21Z"
    ))

    cursor.execute("""
        INSERT INTO reasoning_logs (session_id, message_index, role, content, summary, tool_name, tool_input, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        session_id, 3, "tool",
        "Successfully bought 6 shares of GOOGL at $245.15",
        None,
        "trade",
        '{"action": "buy", "symbol": "GOOGL", "amount": 6}',
        "2025-10-02T10:05:22Z"
    ))

    conn.commit()
    conn.close()

    return {
        "session_id": session_id,
        "job_id": "test-job-123",
        "date": "2025-10-02",
        "model": "gpt-5"
    }


@pytest.fixture
def multiple_sessions(clean_db):
    """Create multiple trading sessions for testing filters."""
    conn = get_db_connection(clean_db)
    cursor = conn.cursor()

    # Create job
    cursor.execute("""
        INSERT INTO jobs (job_id, config_path, status, date_range, models, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        "test-job-456",
        "configs/test.json",
        "completed",
        '["2025-10-03", "2025-10-04"]',
        '["gpt-5", "claude-4"]',
        "2025-10-03T10:00:00Z"
    ))

    # Session 1: gpt-5, 2025-10-03
    cursor.execute("""
        INSERT INTO trading_sessions (job_id, date, model, session_summary, started_at, completed_at, total_messages)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        "test-job-456", "2025-10-03", "gpt-5",
        "Session 1 summary", "2025-10-03T10:00:00Z", "2025-10-03T10:05:00Z", 2
    ))
    session1_id = cursor.lastrowid

    # Session 2: claude-4, 2025-10-03
    cursor.execute("""
        INSERT INTO trading_sessions (job_id, date, model, session_summary, started_at, completed_at, total_messages)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        "test-job-456", "2025-10-03", "claude-4",
        "Session 2 summary", "2025-10-03T10:00:00Z", "2025-10-03T10:05:00Z", 2
    ))
    session2_id = cursor.lastrowid

    # Session 3: gpt-5, 2025-10-04
    cursor.execute("""
        INSERT INTO trading_sessions (job_id, date, model, session_summary, started_at, completed_at, total_messages)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        "test-job-456", "2025-10-04", "gpt-5",
        "Session 3 summary", "2025-10-04T10:00:00Z", "2025-10-04T10:05:00Z", 2
    ))
    session3_id = cursor.lastrowid

    # Add positions for each session
    for session_id, date, model in [(session1_id, "2025-10-03", "gpt-5"),
                                     (session2_id, "2025-10-03", "claude-4"),
                                     (session3_id, "2025-10-04", "gpt-5")]:
        cursor.execute("""
            INSERT INTO positions (
                job_id, date, model, action_id, action_type, symbol, amount, price,
                cash, portfolio_value, session_id, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "test-job-456", date, model, 1, "buy", "AAPL", 5, 250.00,
            8750.00, 10000.00, session_id, f"{date}T10:05:00Z"
        ))

    conn.commit()
    conn.close()

    return {
        "job_id": "test-job-456",
        "session_ids": [session1_id, session2_id, session3_id]
    }


@pytest.mark.unit
class TestGetReasoningEndpoint:
    """Test GET /reasoning endpoint."""

    def test_get_reasoning_with_job_id_filter(self, client, sample_trading_session):
        """Should return sessions filtered by job_id."""
        response = client.get(f"/reasoning?job_id={sample_trading_session['job_id']}")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert len(data["sessions"]) == 1
        assert data["sessions"][0]["job_id"] == sample_trading_session["job_id"]
        assert data["sessions"][0]["date"] == sample_trading_session["date"]
        assert data["sessions"][0]["model"] == sample_trading_session["model"]
        assert data["sessions"][0]["session_summary"] is not None
        assert len(data["sessions"][0]["positions"]) == 2

    def test_get_reasoning_with_date_filter(self, client, multiple_sessions):
        """Should return sessions filtered by date."""
        response = client.get("/reasoning?date=2025-10-03")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2  # Both gpt-5 and claude-4 on 2025-10-03
        assert all(s["date"] == "2025-10-03" for s in data["sessions"])

    def test_get_reasoning_with_model_filter(self, client, multiple_sessions):
        """Should return sessions filtered by model."""
        response = client.get("/reasoning?model=gpt-5")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2  # gpt-5 on both dates
        assert all(s["model"] == "gpt-5" for s in data["sessions"])

    def test_get_reasoning_with_full_conversation(self, client, sample_trading_session):
        """Should include full conversation when requested."""
        response = client.get(
            f"/reasoning?job_id={sample_trading_session['job_id']}&include_full_conversation=true"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1

        session = data["sessions"][0]
        assert session["conversation"] is not None
        assert len(session["conversation"]) == 4  # 1 user + 1 assistant + 2 tool messages

        # Verify message structure
        messages = session["conversation"]
        assert messages[0]["role"] == "user"
        assert messages[0]["message_index"] == 0
        assert messages[0]["summary"] is None

        assert messages[1]["role"] == "assistant"
        assert messages[1]["message_index"] == 1
        assert messages[1]["summary"] is not None

        assert messages[2]["role"] == "tool"
        assert messages[2]["message_index"] == 2
        assert messages[2]["tool_name"] == "trade"
        assert messages[2]["tool_input"] is not None

    def test_get_reasoning_summaries_only(self, client, sample_trading_session):
        """Should not include conversation when include_full_conversation=false (default)."""
        response = client.get(f"/reasoning?job_id={sample_trading_session['job_id']}")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1

        session = data["sessions"][0]
        assert session["conversation"] is None
        assert session["session_summary"] is not None
        assert session["total_messages"] == 4

    def test_get_reasoning_no_results_returns_404(self, client, clean_db):
        """Should return 404 when no sessions match filters."""
        response = client.get("/reasoning?job_id=nonexistent-job")

        assert response.status_code == 404
        assert "No trading sessions found" in response.json()["detail"]

    def test_get_reasoning_invalid_date_returns_400(self, client, clean_db):
        """Should return 400 for invalid date format."""
        response = client.get("/reasoning?date=invalid-date")

        assert response.status_code == 400
        assert "Invalid date format" in response.json()["detail"]

    def test_get_reasoning_includes_deployment_mode(self, client, sample_trading_session):
        """Should include deployment mode info in response."""
        response = client.get(f"/reasoning?job_id={sample_trading_session['job_id']}")

        assert response.status_code == 200
        data = response.json()
        assert "deployment_mode" in data
        assert "is_dev_mode" in data
        assert isinstance(data["is_dev_mode"], bool)


@pytest.fixture
def client(clean_db):
    """Create FastAPI test client with clean database."""
    from fastapi.testclient import TestClient
    from api.main import create_app

    app = create_app(db_path=clean_db)
    app.state.test_mode = True  # Prevent background worker from starting

    return TestClient(app)
