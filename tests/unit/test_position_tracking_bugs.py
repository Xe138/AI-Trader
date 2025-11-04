"""
Tests demonstrating position tracking bugs before fix.

These tests should FAIL before implementing fixes, and PASS after.
"""

import pytest
from datetime import datetime
from api.database import get_db_connection, initialize_database
from api.job_manager import JobManager
from agent_tools.tool_trade import _buy_impl
from tools.price_tools import add_no_trade_record_to_db
import os
from pathlib import Path


@pytest.fixture(scope="function")
def test_db_with_prices():
    """
    Create test database with price data using production database path.

    Note: Since agent_tools hardcode db_path="data/jobs.db", we must use
    the production database path for integration testing.
    """
    # Use production database path
    db_path = "data/jobs.db"

    # Ensure directory exists
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    # Initialize database
    initialize_database(db_path)

    # Clear existing test data if any
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    # Clean up any existing test data (in correct order for foreign keys)
    cursor.execute("DELETE FROM holdings WHERE position_id IN (SELECT id FROM positions WHERE model = 'claude-sonnet-4.5')")
    cursor.execute("DELETE FROM positions WHERE model = 'claude-sonnet-4.5'")
    cursor.execute("DELETE FROM trading_sessions WHERE model = 'claude-sonnet-4.5'")
    cursor.execute("DELETE FROM job_details WHERE model = 'claude-sonnet-4.5'")
    cursor.execute("DELETE FROM price_data WHERE symbol = 'NVDA' AND date IN ('2025-10-06', '2025-10-07')")

    # Mark any pending/running jobs as completed to allow new test jobs
    cursor.execute("UPDATE jobs SET status = 'completed' WHERE status IN ('pending', 'running')")

    # Insert price data for testing
    # 2025-10-06 prices
    cursor.execute("""
        INSERT INTO price_data (symbol, date, open, high, low, close, volume, created_at)
        VALUES ('NVDA', '2025-10-06', 185.5, 190.0, 185.0, 188.0, 1000000, ?)
    """, (datetime.utcnow().isoformat() + "Z",))

    # 2025-10-07 prices (Monday after weekend)
    cursor.execute("""
        INSERT INTO price_data (symbol, date, open, high, low, close, volume, created_at)
        VALUES ('NVDA', '2025-10-07', 186.23, 190.0, 186.0, 189.0, 1000000, ?)
    """, (datetime.utcnow().isoformat() + "Z",))

    conn.commit()
    conn.close()

    yield db_path

    # Cleanup after test
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM holdings WHERE position_id IN (SELECT id FROM positions WHERE model = 'claude-sonnet-4.5')")
    cursor.execute("DELETE FROM positions WHERE model = 'claude-sonnet-4.5'")
    cursor.execute("DELETE FROM trading_sessions WHERE model = 'claude-sonnet-4.5'")
    cursor.execute("DELETE FROM job_details WHERE model = 'claude-sonnet-4.5'")
    cursor.execute("DELETE FROM price_data WHERE symbol = 'NVDA' AND date IN ('2025-10-06', '2025-10-07')")

    # Mark any pending/running jobs as completed
    cursor.execute("UPDATE jobs SET status = 'completed' WHERE status IN ('pending', 'running')")

    conn.commit()
    conn.close()


@pytest.mark.unit
class TestPositionTrackingBugs:
    """Tests demonstrating the three critical bugs."""

    def test_cash_not_reset_between_days(self, test_db_with_prices):
        """
        Bug #1: Cash should carry over from previous day, not reset to initial value.

        Scenario:
        - Day 1: Start with $10,000, buy 5 NVDA @ $185.50 = $927.50, cash left = $9,072.50
        - Day 2: Should start with $9,072.50 cash, not $10,000
        """
        # Create job
        manager = JobManager(db_path=test_db_with_prices)
        job_id = manager.create_job(
            config_path="configs/test.json",
            date_range=["2025-10-06", "2025-10-07"],
            models=["claude-sonnet-4.5"]
        )

        # Day 1: Initial position (action_id=0)
        conn = get_db_connection(test_db_with_prices)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO trading_sessions (job_id, date, model, started_at)
            VALUES (?, ?, ?, ?)
        """, (job_id, "2025-10-06", "claude-sonnet-4.5", datetime.utcnow().isoformat() + "Z"))
        session_id_day1 = cursor.lastrowid

        cursor.execute("""
            INSERT INTO positions (
                job_id, date, model, action_id, action_type,
                cash, portfolio_value, session_id, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job_id, "2025-10-06", "claude-sonnet-4.5", 0, "no_trade",
            10000.0, 10000.0, session_id_day1, datetime.utcnow().isoformat() + "Z"
        ))

        conn.commit()
        conn.close()

        # Day 1: Buy 5 NVDA @ $185.50
        result = _buy_impl(
            symbol="NVDA",
            amount=5,
            signature="claude-sonnet-4.5",
            today_date="2025-10-06",
            job_id=job_id,
            session_id=session_id_day1
        )

        assert "error" not in result
        assert result["CASH"] == 9072.5  # 10000 - (5 * 185.5)

        # Day 2: Create new session
        conn = get_db_connection(test_db_with_prices)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO trading_sessions (job_id, date, model, started_at)
            VALUES (?, ?, ?, ?)
        """, (job_id, "2025-10-07", "claude-sonnet-4.5", datetime.utcnow().isoformat() + "Z"))
        session_id_day2 = cursor.lastrowid
        conn.commit()
        conn.close()

        # Day 2: Check starting cash (should be $9,072.50, not $10,000)
        from agent_tools.tool_trade import get_current_position_from_db

        position, next_action_id = get_current_position_from_db(
            job_id=job_id,
            model="claude-sonnet-4.5",
            date="2025-10-07"
        )

        # BUG: This will fail before fix - cash resets to $10,000 or $0
        assert position["CASH"] == 9072.5, f"Expected cash $9,072.50 but got ${position['CASH']}"
        assert position["NVDA"] == 5, f"Expected 5 NVDA shares but got {position.get('NVDA', 0)}"

    def test_positions_persist_over_weekend(self, test_db_with_prices):
        """
        Bug #2: Positions should persist over non-trading days (weekends).

        Scenario:
        - Friday 2025-10-06: Buy 5 NVDA
        - Monday 2025-10-07: Should still have 5 NVDA
        """
        # Create job
        manager = JobManager(db_path=test_db_with_prices)
        job_id = manager.create_job(
            config_path="configs/test.json",
            date_range=["2025-10-06", "2025-10-07"],
            models=["claude-sonnet-4.5"]
        )

        # Friday: Initial position + buy
        conn = get_db_connection(test_db_with_prices)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO trading_sessions (job_id, date, model, started_at)
            VALUES (?, ?, ?, ?)
        """, (job_id, "2025-10-06", "claude-sonnet-4.5", datetime.utcnow().isoformat() + "Z"))
        session_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO positions (
                job_id, date, model, action_id, action_type,
                cash, portfolio_value, session_id, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job_id, "2025-10-06", "claude-sonnet-4.5", 0, "no_trade",
            10000.0, 10000.0, session_id, datetime.utcnow().isoformat() + "Z"
        ))

        conn.commit()
        conn.close()

        _buy_impl(
            symbol="NVDA",
            amount=5,
            signature="claude-sonnet-4.5",
            today_date="2025-10-06",
            job_id=job_id,
            session_id=session_id
        )

        # Monday: Check positions persist
        from agent_tools.tool_trade import get_current_position_from_db

        position, _ = get_current_position_from_db(
            job_id=job_id,
            model="claude-sonnet-4.5",
            date="2025-10-07"
        )

        # BUG: This will fail before fix - positions lost, holdings=[]
        assert "NVDA" in position, "NVDA position should persist over weekend"
        assert position["NVDA"] == 5, f"Expected 5 NVDA shares but got {position.get('NVDA', 0)}"

    def test_profit_calculation_accuracy(self, test_db_with_prices):
        """
        Bug #3: Profit should reflect actual gains/losses, not show trades as losses.

        Scenario:
        - Start with $10,000 cash, portfolio value = $10,000
        - Buy 5 NVDA @ $185.50 = $927.50
        - New position: cash = $9,072.50, 5 NVDA worth $927.50
        - Portfolio value = $9,072.50 + $927.50 = $10,000 (unchanged)
        - Expected profit = $0 (no price change yet, just traded)

        Current bug: Shows profit = -$927.50 or similar (treating trade as loss)
        """
        # Create job
        manager = JobManager(db_path=test_db_with_prices)
        job_id = manager.create_job(
            config_path="configs/test.json",
            date_range=["2025-10-06"],
            models=["claude-sonnet-4.5"]
        )

        # Create session and initial position
        conn = get_db_connection(test_db_with_prices)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO trading_sessions (job_id, date, model, started_at)
            VALUES (?, ?, ?, ?)
        """, (job_id, "2025-10-06", "claude-sonnet-4.5", datetime.utcnow().isoformat() + "Z"))
        session_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO positions (
                job_id, date, model, action_id, action_type,
                cash, portfolio_value, daily_profit, daily_return_pct,
                session_id, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job_id, "2025-10-06", "claude-sonnet-4.5", 0, "no_trade",
            10000.0, 10000.0, None, None,
            session_id, datetime.utcnow().isoformat() + "Z"
        ))

        conn.commit()
        conn.close()

        # Buy 5 NVDA @ $185.50
        _buy_impl(
            symbol="NVDA",
            amount=5,
            signature="claude-sonnet-4.5",
            today_date="2025-10-06",
            job_id=job_id,
            session_id=session_id
        )

        # Check profit calculation
        conn = get_db_connection(test_db_with_prices)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT portfolio_value, daily_profit, daily_return_pct
            FROM positions
            WHERE job_id = ? AND model = ? AND date = ? AND action_id = 1
        """, (job_id, "claude-sonnet-4.5", "2025-10-06"))

        row = cursor.fetchone()
        conn.close()

        portfolio_value = row[0]
        daily_profit = row[1]
        daily_return_pct = row[2]

        # Portfolio value should be $10,000 (cash $9,072.50 + 5 NVDA @ $185.50)
        assert abs(portfolio_value - 10000.0) < 0.01, \
            f"Expected portfolio value $10,000 but got ${portfolio_value}"

        # BUG: This will fail before fix - shows profit as negative or zero when should be zero
        # Profit should be $0 (no price movement, just traded)
        assert abs(daily_profit) < 0.01, \
            f"Expected profit $0 (no price change) but got ${daily_profit}"
        assert abs(daily_return_pct) < 0.01, \
            f"Expected return 0% but got {daily_return_pct}%"
