"""Test portfolio continuity across multiple jobs."""
import pytest
from api.database import db_connection
import tempfile
import os
from agent_tools.tool_trade import get_current_position_from_db
from api.database import get_db_connection


@pytest.fixture
def temp_db():
    """Create temporary database with schema."""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)

    with db_connection(path) as conn:
        cursor = conn.cursor()

        # Create trading_days table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trading_days (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                model TEXT NOT NULL,
                date TEXT NOT NULL,
                starting_cash REAL NOT NULL,
                ending_cash REAL NOT NULL,
                profit REAL NOT NULL,
                return_pct REAL NOT NULL,
                portfolio_value REAL NOT NULL,
                reasoning_summary TEXT,
                reasoning_full TEXT,
                completed_at TEXT,
                session_duration_seconds REAL,
                UNIQUE(job_id, model, date)
            )
        """)

        # Create holdings table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS holdings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trading_day_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                FOREIGN KEY (trading_day_id) REFERENCES trading_days(id) ON DELETE CASCADE
            )
        """)

        conn.commit()

    yield path

    if os.path.exists(path):
        os.remove(path)


def test_position_continuity_across_jobs(temp_db):
    """Test that position queries see history from previous jobs."""
    # Insert trading_day from job 1
    with db_connection(temp_db) as conn:
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO trading_days (
                job_id, model, date, starting_cash, ending_cash,
                profit, return_pct, portfolio_value, completed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "job-1-uuid",
            "deepseek-chat-v3.1",
            "2025-10-14",
            10000.0,
            5121.52,  # Negative cash from buying
            0.0,
            0.0,
            14993.945,
            "2025-11-07T01:52:53Z"
        ))

        trading_day_id = cursor.lastrowid

        # Insert holdings from job 1
        holdings = [
            ("ADBE", 5),
            ("AVGO", 5),
            ("CRWD", 5),
            ("GOOGL", 20),
            ("META", 5),
            ("MSFT", 5),
            ("NVDA", 10)
        ]

        for symbol, quantity in holdings:
            cursor.execute("""
                INSERT INTO holdings (trading_day_id, symbol, quantity)
                VALUES (?, ?, ?)
            """, (trading_day_id, symbol, quantity))

        conn.commit()

    # Mock get_db_connection to return our test db
    import agent_tools.tool_trade as trade_module
    original_get_db_connection = trade_module.get_db_connection

    def mock_get_db_connection(path):
        return get_db_connection(temp_db)

    trade_module.get_db_connection = mock_get_db_connection

    try:
        # Now query position for job 2 on next trading day
        position, _ = get_current_position_from_db(
            job_id="job-2-uuid",  # Different job
            model="deepseek-chat-v3.1",
            date="2025-10-15",
            initial_cash=10000.0
        )

        # Should see job 1's ending position, NOT initial $10k
        assert position["CASH"] == 5121.52
        assert position["ADBE"] == 5
        assert position["AVGO"] == 5
        assert position["CRWD"] == 5
        assert position["GOOGL"] == 20
        assert position["META"] == 5
        assert position["MSFT"] == 5
        assert position["NVDA"] == 10
    finally:
        # Restore original function
        trade_module.get_db_connection = original_get_db_connection


def test_position_returns_initial_state_for_first_day(temp_db):
    """Test that first trading day returns initial cash."""
    # Mock get_db_connection to return our test db
    import agent_tools.tool_trade as trade_module
    original_get_db_connection = trade_module.get_db_connection

    def mock_get_db_connection(path):
        return get_db_connection(temp_db)

    trade_module.get_db_connection = mock_get_db_connection

    try:
        # No previous trading days exist
        position, _ = get_current_position_from_db(
            job_id="new-job-uuid",
            model="new-model",
            date="2025-10-13",
            initial_cash=10000.0
        )

        # Should return initial position
        assert position == {"CASH": 10000.0}
    finally:
        # Restore original function
        trade_module.get_db_connection = original_get_db_connection


def test_position_uses_most_recent_prior_date(temp_db):
    """Test that position query uses the most recent date before current."""
    with db_connection(temp_db) as conn:
        cursor = conn.cursor()

        # Insert two trading days
        cursor.execute("""
            INSERT INTO trading_days (
                job_id, model, date, starting_cash, ending_cash,
                profit, return_pct, portfolio_value, completed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "job-1",
            "model-a",
            "2025-10-13",
            10000.0,
            9500.0,
            -500.0,
            -5.0,
            9500.0,
            "2025-11-07T01:00:00Z"
        ))

        cursor.execute("""
            INSERT INTO trading_days (
                job_id, model, date, starting_cash, ending_cash,
                profit, return_pct, portfolio_value, completed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "job-2",
            "model-a",
            "2025-10-14",
            9500.0,
            12000.0,
            2500.0,
            26.3,
            12000.0,
            "2025-11-07T02:00:00Z"
        ))

        conn.commit()

    # Mock get_db_connection to return our test db
    import agent_tools.tool_trade as trade_module
    original_get_db_connection = trade_module.get_db_connection

    def mock_get_db_connection(path):
        return get_db_connection(temp_db)

    trade_module.get_db_connection = mock_get_db_connection

    try:
        # Query for 2025-10-15 should use 2025-10-14's ending position
        position, _ = get_current_position_from_db(
            job_id="job-3",
            model="model-a",
            date="2025-10-15",
            initial_cash=10000.0
        )

        assert position["CASH"] == 12000.0  # From 2025-10-14, not 2025-10-13
    finally:
        # Restore original function
        trade_module.get_db_connection = original_get_db_connection
