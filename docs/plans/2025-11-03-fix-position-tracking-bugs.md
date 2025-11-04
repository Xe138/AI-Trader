# Fix Position Tracking and P&L Calculation Bugs Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix three critical bugs in position tracking: (1) cash reset to initial value each day, (2) positions lost over weekends, (3) incorrect profit calculations showing trades as losses.

**Architecture:** Remove redundant `_write_results_to_db()` method that creates corrupt position records with cash=0 and holdings=[], and fix profit calculation logic to compare same-day position values instead of previous-day portfolio value.

**Tech Stack:** Python 3.12, SQLite3, pytest

**Root Cause Analysis:**

1. **Bug #1 & #2 (Cash reset + positions lost):**
   - `ModelDayExecutor._write_results_to_db()` calls non-existent methods (`get_positions()`, `get_last_trade()`, `get_current_prices()`)
   - These return empty values, creating corrupt records with `cash=0`, `holdings=[]`
   - `get_current_position_from_db()` then finds this corrupt record as "latest", causing reset

2. **Bug #3 (Incorrect profit calculations):**
   - Current logic compares portfolio value to **previous day's final value**
   - When you buy stocks, cash decreases and stock value increases equally → portfolio value unchanged → profit=0 shown
   - Should compare to **start of current day** (after price changes) to show actual gains/losses from trading

---

## Task 1: Write Failing Tests for Current Bugs

**Files:**
- Create: `tests/unit/test_position_tracking_bugs.py`

**Step 1: Write test demonstrating cash reset bug**

Create `tests/unit/test_position_tracking_bugs.py`:

```python
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


@pytest.fixture
def test_db_with_prices(tmp_path):
    """Create test database with price data."""
    db_path = str(tmp_path / "test.db")
    initialize_database(db_path)

    # Insert price data for testing
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

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

    return db_path


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
```

**Step 2: Run tests to verify they fail**

Run: `./venv/bin/python -m pytest tests/unit/test_position_tracking_bugs.py -v`

Expected: All 3 tests FAIL demonstrating the bugs

**Step 3: Commit failing tests**

```bash
git add tests/unit/test_position_tracking_bugs.py
git commit -m "test: add failing tests demonstrating position tracking bugs"
```

---

## Task 2: Remove Redundant `_write_results_to_db()` Method

**Files:**
- Modify: `api/model_day_executor.py:161-167` (remove call)
- Modify: `api/model_day_executor.py:435-558` (remove entire method)

**Step 1: Remove the call to `_write_results_to_db()`**

In `api/model_day_executor.py`, find the `execute_async()` method around line 161-167:

```python
# Commit and close connection before _write_results_to_db opens a new one
conn.commit()
conn.close()
conn = None  # Mark as closed

# Store positions (pass session_id) - this opens its own connection
self._write_results_to_db(agent, session_id)

# Update status to completed
```

Replace with:

```python
# Commit and close connection
conn.commit()
conn.close()
conn = None  # Mark as closed

# Note: Positions are written by trade tools (buy/sell) or no_trade_record
# No need to write positions here - that was creating duplicate/corrupt records

# Update status to completed
```

**Step 2: Delete the entire `_write_results_to_db()` method**

In `api/model_day_executor.py`, delete lines 435-558 (the entire method):

```python
# DELETE THIS ENTIRE METHOD (lines 435-558):
def _write_results_to_db(self, agent, session_id: int) -> None:
    """
    Write execution results to SQLite.
    ...
    """
    # ... entire method body ...
```

Also delete the helper method `_calculate_portfolio_value()` at lines 533-558:

```python
# DELETE THIS TOO (lines 533-558):
def _calculate_portfolio_value(
    self,
    positions: Dict[str, float],
    current_prices: Dict[str, float]
) -> float:
    """
    Calculate total portfolio value.
    ...
    """
    # ... entire method body ...
```

**Step 3: Run unit tests to see what breaks**

Run: `./venv/bin/python -m pytest tests/unit/test_model_day_executor.py -v`

Expected: Some tests FAIL because they mock non-existent methods

**Step 4: Commit the removal**

```bash
git add api/model_day_executor.py
git commit -m "fix: remove redundant _write_results_to_db() creating corrupt position records"
```

---

## Task 3: Fix Unit Tests That Mock Non-Existent Methods

**Files:**
- Modify: `tests/unit/test_model_day_executor.py:21-43`
- Modify: `tests/unit/test_model_day_executor.py:185-295`
- Modify: `tests/unit/test_model_day_executor_reasoning.py:240-266`

**Step 1: Update `create_mock_agent()` helper**

In `tests/unit/test_model_day_executor.py`, find the `create_mock_agent()` function (lines 21-43):

```python
def create_mock_agent(positions=None, last_trade=None, current_prices=None,
                     reasoning_steps=None, tool_usage=None, session_result=None,
                     conversation_history=None):
    """Helper to create properly mocked agent."""
    mock_agent = Mock()

    # Default values
    mock_agent.get_positions.return_value = positions or {"CASH": 10000.0}
    mock_agent.get_last_trade.return_value = last_trade
    mock_agent.get_current_prices.return_value = current_prices or {}
    # ...
```

Replace with (remove references to deleted methods):

```python
def create_mock_agent(reasoning_steps=None, tool_usage=None, session_result=None,
                     conversation_history=None):
    """Helper to create properly mocked agent."""
    mock_agent = Mock()

    # Note: Removed get_positions, get_last_trade, get_current_prices
    # These methods don't exist in BaseAgent and were only used by
    # the now-deleted _write_results_to_db() method

    mock_agent.get_reasoning_steps.return_value = reasoning_steps or []
    mock_agent.get_tool_usage.return_value = tool_usage or {}
    mock_agent.get_conversation_history.return_value = conversation_history or []

    # Async methods - use AsyncMock
    mock_agent.run_trading_session = AsyncMock(return_value=session_result or {"success": True})
    mock_agent.generate_summary = AsyncMock(return_value="Mock summary")
    mock_agent.summarize_message = AsyncMock(return_value="Mock message summary")

    # Mock model for summary generation
    mock_agent.model = Mock()

    return mock_agent
```

**Step 2: Update tests that verify position writes**

In `tests/unit/test_model_day_executor.py`, find `TestModelDayExecutorDataPersistence` class (lines 182-345).

The tests `test_writes_position_to_database` and `test_writes_holdings_to_database` need to be updated because positions are now written by trade tools, not by the executor.

Replace these tests with:

```python
@pytest.mark.unit
class TestModelDayExecutorDataPersistence:
    """Test result persistence to SQLite."""

    def test_creates_initial_position(self, clean_db):
        """Should create initial position record (action_id=0) on first day."""
        from api.model_day_executor import ModelDayExecutor
        from api.job_manager import JobManager
        from api.database import get_db_connection

        # Create job
        manager = JobManager(db_path=clean_db)
        job_id = manager.create_job(
            config_path="configs/test.json",
            date_range=["2025-01-16"],
            models=["gpt-5"]
        )

        # Mock successful execution (no trades)
        mock_agent = create_mock_agent(
            session_result={"success": True, "total_steps": 10}
        )

        with patch("api.model_day_executor.RuntimeConfigManager") as mock_runtime:
            mock_instance = Mock()
            mock_instance.create_runtime_config.return_value = "/tmp/runtime_test.json"
            mock_runtime.return_value = mock_instance

            executor = ModelDayExecutor(
                job_id=job_id,
                date="2025-01-16",
                model_sig="gpt-5",
                config_path="configs/test.json",
                db_path=clean_db
            )

            with patch.object(executor, '_initialize_agent', return_value=mock_agent):
                # Mock _handle_trading_result to avoid database writes
                with patch.object(executor, '_handle_trading_result', new_callable=AsyncMock):
                    executor.execute()

        # Verify initial position created (action_id=0)
        conn = get_db_connection(clean_db)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT job_id, date, model, action_id, action_type, cash, portfolio_value
            FROM positions
            WHERE job_id = ? AND date = ? AND model = ?
        """, (job_id, "2025-01-16", "gpt-5"))

        row = cursor.fetchone()
        assert row is not None, "Should create initial position record"
        assert row[0] == job_id
        assert row[1] == "2025-01-16"
        assert row[2] == "gpt-5"
        assert row[3] == 0, "Initial position should have action_id=0"
        assert row[4] == "no_trade"
        assert row[5] == 10000.0, "Initial cash should be $10,000"
        assert row[6] == 10000.0, "Initial portfolio value should be $10,000"

        conn.close()

    def test_writes_reasoning_logs(self, clean_db):
        """Should write AI reasoning logs to SQLite."""
        # This test remains the same as before (line 297-344)
        # ... (keep existing test)
```

**Step 3: Update `test_model_day_executor_reasoning.py`**

In `tests/unit/test_model_day_executor_reasoning.py`, find the test that calls `_write_results_to_db` directly (around line 240-266).

Delete or skip this test since the method no longer exists:

```python
@pytest.mark.skip(reason="Method _write_results_to_db() removed - positions written by trade tools")
def test_write_results_links_position_to_session(test_db):
    """DEPRECATED: This test verified _write_results_to_db() which has been removed."""
    # Delete this entire test or mark as skipped
    pass
```

**Step 4: Run tests to verify fixes**

Run: `./venv/bin/python -m pytest tests/unit/test_model_day_executor.py tests/unit/test_model_day_executor_reasoning.py -v`

Expected: All tests PASS

**Step 5: Commit test fixes**

```bash
git add tests/unit/test_model_day_executor.py tests/unit/test_model_day_executor_reasoning.py
git commit -m "test: update tests after removing _write_results_to_db()"
```

---

## Task 4: Fix Profit Calculation Logic (Bug #3)

**Files:**
- Modify: `agent_tools/tool_trade.py:144-157` (buy function)
- Modify: `agent_tools/tool_trade.py:287-300` (sell function)
- Modify: `tools/price_tools.py:417-430` (no_trade function)

**Background:**

Current profit calculation compares portfolio value to **previous day's final value**. This is incorrect because:
- When you buy stocks, cash ↓ and stock value ↑ equally → portfolio unchanged → profit=0
- But we're comparing to previous day's final value, which makes trades look like losses

**Correct approach:**

Profit should be calculated by comparing to the **start-of-day portfolio value** (same day, action_id=0). This shows actual gains/losses from price movements and trading decisions.

**Step 1: Fix profit calculation in buy function**

In `agent_tools/tool_trade.py`, find the profit calculation in `_buy_impl()` (around lines 144-157):

```python
# Get previous portfolio value for P&L calculation
cursor.execute("""
    SELECT portfolio_value
    FROM positions
    WHERE job_id = ? AND model = ? AND date < ?
    ORDER BY date DESC, action_id DESC
    LIMIT 1
""", (job_id, signature, today_date))

row = cursor.fetchone()
previous_value = row[0] if row else 10000.0  # Default initial value

daily_profit = portfolio_value - previous_value
daily_return_pct = (daily_profit / previous_value * 100) if previous_value > 0 else 0
```

Replace with:

```python
# Get start-of-day portfolio value (action_id=0 for today) for P&L calculation
cursor.execute("""
    SELECT portfolio_value
    FROM positions
    WHERE job_id = ? AND model = ? AND date = ? AND action_id = 0
    LIMIT 1
""", (job_id, signature, today_date))

row = cursor.fetchone()

if row:
    # Compare to start of day (action_id=0)
    start_of_day_value = row[0]
    daily_profit = portfolio_value - start_of_day_value
    daily_return_pct = (daily_profit / start_of_day_value * 100) if start_of_day_value > 0 else 0
else:
    # First action of first day - no baseline yet
    daily_profit = 0.0
    daily_return_pct = 0.0
```

**Step 2: Fix profit calculation in sell function**

In `agent_tools/tool_trade.py`, find the profit calculation in `_sell_impl()` (around lines 287-300):

```python
# Get previous portfolio value
cursor.execute("""
    SELECT portfolio_value
    FROM positions
    WHERE job_id = ? AND model = ? AND date < ?
    ORDER BY date DESC, action_id DESC
    LIMIT 1
""", (job_id, signature, today_date))

row = cursor.fetchone()
previous_value = row[0] if row else 10000.0

daily_profit = portfolio_value - previous_value
daily_return_pct = (daily_profit / previous_value * 100) if previous_value > 0 else 0
```

Replace with:

```python
# Get start-of-day portfolio value (action_id=0 for today) for P&L calculation
cursor.execute("""
    SELECT portfolio_value
    FROM positions
    WHERE job_id = ? AND model = ? AND date = ? AND action_id = 0
    LIMIT 1
""", (job_id, signature, today_date))

row = cursor.fetchone()

if row:
    # Compare to start of day (action_id=0)
    start_of_day_value = row[0]
    daily_profit = portfolio_value - start_of_day_value
    daily_return_pct = (daily_profit / start_of_day_value * 100) if start_of_day_value > 0 else 0
else:
    # First action of first day - no baseline yet
    daily_profit = 0.0
    daily_return_pct = 0.0
```

**Step 3: Fix profit calculation in no_trade function**

In `tools/price_tools.py`, find the profit calculation in `add_no_trade_record_to_db()` (around lines 417-430):

```python
# Get previous value for P&L
cursor.execute("""
    SELECT portfolio_value
    FROM positions
    WHERE job_id = ? AND model = ? AND date < ?
    ORDER BY date DESC, action_id DESC
    LIMIT 1
""", (job_id, modelname, today_date))

row = cursor.fetchone()
previous_value = row[0] if row else 10000.0

daily_profit = portfolio_value - previous_value
daily_return_pct = (daily_profit / previous_value * 100) if previous_value > 0 else 0
```

Replace with:

```python
# Get start-of-day portfolio value (action_id=0 for today) for P&L calculation
cursor.execute("""
    SELECT portfolio_value
    FROM positions
    WHERE job_id = ? AND model = ? AND date = ? AND action_id = 0
    LIMIT 1
""", (job_id, modelname, today_date))

row = cursor.fetchone()

if row:
    # Compare to start of day (action_id=0)
    start_of_day_value = row[0]
    daily_profit = portfolio_value - start_of_day_value
    daily_return_pct = (daily_profit / start_of_day_value * 100) if start_of_day_value > 0 else 0
else:
    # First action of first day - no baseline yet
    daily_profit = 0.0
    daily_return_pct = 0.0
```

**Step 4: Run bug tests to verify fix**

Run: `./venv/bin/python -m pytest tests/unit/test_position_tracking_bugs.py::TestPositionTrackingBugs::test_profit_calculation_accuracy -v`

Expected: Test PASSES

**Step 5: Commit profit calculation fixes**

```bash
git add agent_tools/tool_trade.py tools/price_tools.py
git commit -m "fix: correct profit calculation to compare against start-of-day value"
```

---

## Task 5: Verify All Bug Tests Pass

**Step 1: Run all bug tests**

Run: `./venv/bin/python -m pytest tests/unit/test_position_tracking_bugs.py -v`

Expected: All 3 tests PASS

**Step 2: Run full test suite**

Run: `./venv/bin/python -m pytest tests/ -v --cov=. --cov-report=term-missing --cov-report=html --tb=short`

Expected: All tests PASS, coverage maintained or improved

**Step 3: If any tests fail, debug and fix**

If tests fail:
1. Read the error message carefully
2. Check which assertion failed
3. Add debug prints to understand state
4. Fix the issue
5. Re-run tests
6. Commit the fix

**Step 4: Commit passing tests**

```bash
git add -A
git commit -m "test: verify all position tracking bugs are fixed"
```

---

## Task 6: Integration Test with Real Simulation

**Files:**
- Create: `tests/integration/test_position_tracking_e2e.py`

**Step 1: Write end-to-end integration test**

Create `tests/integration/test_position_tracking_e2e.py`:

```python
"""
End-to-end integration test for position tracking across multiple days.

Tests the complete flow: ModelDayExecutor → trade tools → database → position retrieval
"""

import pytest
from datetime import datetime
from api.database import get_db_connection, initialize_database
from api.job_manager import JobManager
from api.model_day_executor import ModelDayExecutor
from unittest.mock import patch, Mock, AsyncMock


def create_test_db_with_multi_day_prices(tmp_path):
    """Create test database with prices for multiple consecutive days."""
    db_path = str(tmp_path / "test.db")
    initialize_database(db_path)

    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    # Create price data for 5 consecutive trading days
    dates = ["2025-10-06", "2025-10-07", "2025-10-08", "2025-10-09", "2025-10-10"]
    base_price = 185.0

    for i, date in enumerate(dates):
        # Prices gradually increase each day
        open_price = base_price + (i * 2.0)
        close_price = base_price + (i * 2.0) + 1.5

        for symbol in ["NVDA", "AAPL", "MSFT"]:
            cursor.execute("""
                INSERT INTO price_data (symbol, date, open, high, low, close, volume, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                symbol, date, open_price, open_price + 3, open_price - 1,
                close_price, 1000000, datetime.utcnow().isoformat() + "Z"
            ))

    conn.commit()
    conn.close()

    return db_path


@pytest.mark.integration
class TestPositionTrackingEndToEnd:
    """End-to-end tests for position tracking across multiple days."""

    def test_multi_day_position_continuity(self, tmp_path):
        """
        Test that positions correctly carry over across multiple trading days.

        Scenario:
        - Day 1: Start with $10,000, buy 5 NVDA @ $185
        - Day 2: Cash should be $9,075, holdings should be 5 NVDA
        - Day 3: Buy 3 AAPL @ $189
        - Day 4: Should have 5 NVDA + 3 AAPL
        - Day 5: Sell 2 NVDA @ $193
        - Final: Should have 3 NVDA + 3 AAPL + increased cash
        """
        db_path = create_test_db_with_multi_day_prices(tmp_path)

        # Create job for 5-day simulation
        manager = JobManager(db_path=db_path)
        job_id = manager.create_job(
            config_path="configs/test.json",
            date_range=["2025-10-06", "2025-10-07", "2025-10-08", "2025-10-09", "2025-10-10"],
            models=["test-model"]
        )

        # Mock agent that makes specific trades each day
        def create_trading_agent(day, trades):
            """Create mock agent that executes specific trades."""
            mock_agent = Mock()
            mock_agent.get_conversation_history.return_value = []

            # Mock async methods
            async def run_session(date):
                # Execute trades for this day
                from agent_tools.tool_trade import _buy_impl, _sell_impl
                from tools.general_tools import get_config_value

                job_id = get_config_value("JOB_ID")
                session_id = get_config_value("SESSION_ID")

                for trade in trades:
                    if trade["action"] == "buy":
                        _buy_impl(
                            symbol=trade["symbol"],
                            amount=trade["amount"],
                            signature="test-model",
                            today_date=date,
                            job_id=job_id,
                            session_id=session_id
                        )
                    elif trade["action"] == "sell":
                        _sell_impl(
                            symbol=trade["symbol"],
                            amount=trade["amount"],
                            signature="test-model",
                            today_date=date,
                            job_id=job_id,
                            session_id=session_id
                        )

                return {"success": True}

            mock_agent.run_trading_session = AsyncMock(side_effect=run_session)
            mock_agent.generate_summary = AsyncMock(return_value="Mock summary")
            return mock_agent

        # Day 1: Buy 5 NVDA
        day1_trades = [{"action": "buy", "symbol": "NVDA", "amount": 5}]
        # Day 2: No trades
        day2_trades = []
        # Day 3: Buy 3 AAPL
        day3_trades = [{"action": "buy", "symbol": "AAPL", "amount": 3}]
        # Day 4: No trades
        day4_trades = []
        # Day 5: Sell 2 NVDA
        day5_trades = [{"action": "sell", "symbol": "NVDA", "amount": 2}]

        all_trades = [day1_trades, day2_trades, day3_trades, day4_trades, day5_trades]
        dates = ["2025-10-06", "2025-10-07", "2025-10-08", "2025-10-09", "2025-10-10"]

        # Execute each day
        for i, (date, trades) in enumerate(zip(dates, all_trades)):
            with patch("api.model_day_executor.RuntimeConfigManager") as mock_runtime:
                mock_instance = Mock()
                mock_instance.create_runtime_config.return_value = f"/tmp/runtime_{i}.json"
                mock_runtime.return_value = mock_instance

                executor = ModelDayExecutor(
                    job_id=job_id,
                    date=date,
                    model_sig="test-model",
                    config_path="configs/test.json",
                    db_path=db_path
                )

                mock_agent = create_trading_agent(i, trades)

                with patch.object(executor, '_initialize_agent', return_value=mock_agent):
                    result = executor.execute()
                    assert result["success"], f"Day {i+1} execution failed"

        # Verify final positions
        conn = get_db_connection(db_path)
        cursor = conn.cursor()

        # Get last position
        cursor.execute("""
            SELECT p.cash, p.portfolio_value
            FROM positions p
            WHERE p.job_id = ? AND p.model = ?
            ORDER BY p.date DESC, p.action_id DESC
            LIMIT 1
        """, (job_id, "test-model"))

        final_position = cursor.fetchone()

        # Get final holdings
        cursor.execute("""
            SELECT h.symbol, h.quantity
            FROM holdings h
            JOIN positions p ON h.position_id = p.id
            WHERE p.job_id = ? AND p.model = ?
            ORDER BY p.date DESC, p.action_id DESC, h.symbol
            LIMIT 10
        """, (job_id, "test-model"))

        holdings = {row[0]: row[1] for row in cursor.fetchall()}

        conn.close()

        # Verify final state
        assert "NVDA" in holdings, "Should have NVDA position"
        assert holdings["NVDA"] == 3, f"Expected 3 NVDA (bought 5, sold 2) but got {holdings['NVDA']}"

        assert "AAPL" in holdings, "Should have AAPL position"
        assert holdings["AAPL"] == 3, f"Expected 3 AAPL but got {holdings['AAPL']}"

        # Cash should be less than initial $10,000 (we bought more than sold)
        assert final_position[0] < 10000, f"Cash should be less than $10,000 but got ${final_position[0]}"

        # Portfolio value should be roughly $10,000 (prices didn't change much)
        # Allow some variation due to price movements
        assert 9800 < final_position[1] < 10200, \
            f"Portfolio value should be ~$10,000 but got ${final_position[1]}"
```

**Step 2: Run integration test**

Run: `./venv/bin/python -m pytest tests/integration/test_position_tracking_e2e.py -v`

Expected: Test PASSES

**Step 3: Commit integration test**

```bash
git add tests/integration/test_position_tracking_e2e.py
git commit -m "test: add e2e integration test for multi-day position tracking"
```

---

## Task 7: Update Documentation

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `docs/developer/database-schema.md`

**Step 1: Update CHANGELOG.md**

Add entry at the top of `CHANGELOG.md`:

```markdown
## [Unreleased]

### Fixed
- **Critical:** Fixed position tracking bugs causing cash reset and positions lost over weekends
  - Removed redundant `ModelDayExecutor._write_results_to_db()` that created corrupt records with cash=0 and holdings=[]
  - Fixed profit calculation to compare against start-of-day portfolio value instead of previous day's final value
  - Positions now correctly carry over between trading days and across weekends
  - Profit/loss calculations now accurately reflect trading gains/losses without treating trades as losses

### Changed
- Position tracking now exclusively handled by trade tools (`buy()`, `sell()`) and `add_no_trade_record_to_db()`
- Daily profit calculation compares to start-of-day (action_id=0) portfolio value for accurate P&L tracking
```

**Step 2: Update database schema documentation**

In `docs/developer/database-schema.md`, find the section on the `positions` table and update the `daily_profit` and `daily_return_pct` field descriptions:

```markdown
### positions

| Column | Type | Description |
|--------|------|-------------|
| ... | ... | ... |
| daily_profit | REAL | **Daily profit/loss compared to start-of-day portfolio value (action_id=0).** Calculated as: `current_portfolio_value - start_of_day_portfolio_value`. This shows the actual gain/loss from price movements and trading decisions, not affected by merely buying/selling stocks. |
| daily_return_pct | REAL | **Daily return percentage compared to start-of-day portfolio value.** Calculated as: `(daily_profit / start_of_day_portfolio_value) * 100` |
| ... | ... | ... |

**Important Notes:**

- **Position tracking flow:** Positions are written by trade tools (`buy()`, `sell()` in `agent_tools/tool_trade.py`) and no-trade records (`add_no_trade_record_to_db()` in `tools/price_tools.py`). Each trade creates a new position record.

- **Action ID sequence:**
  - `action_id=0`: Start-of-day position (created by `ModelDayExecutor._initialize_starting_position()` on first day only)
  - `action_id=1+`: Each trade or no-trade action increments the action_id

- **Profit calculation:** Daily profit is calculated by comparing current portfolio value to the **start-of-day** portfolio value (action_id=0 for the current date). This ensures that:
  - Buying stocks doesn't show as a loss (cash ↓, stock value ↑ equally)
  - Selling stocks doesn't show as a gain (cash ↑, stock value ↓ equally)
  - Only actual price movements and strategic trading show as profit/loss
```

**Step 3: Commit documentation updates**

```bash
git add CHANGELOG.md docs/developer/database-schema.md
git commit -m "docs: update changelog and schema docs for position tracking fixes"
```

---

## Task 8: Manual Testing with Real Simulation

**Step 1: Create test configuration**

Create `configs/position_tracking_test.json`:

```json
{
  "agent_type": "BaseAgent",
  "date_range": {
    "init_date": "2025-10-06",
    "end_date": "2025-10-10"
  },
  "models": [
    {
      "name": "position-test",
      "basemodel": "anthropic/claude-sonnet-4-20250514",
      "signature": "position-tracking-test",
      "enabled": true
    }
  ],
  "agent_config": {
    "max_steps": 15,
    "initial_cash": 10000.0,
    "stock_symbols": ["NVDA", "AAPL", "MSFT", "GOOGL", "META"]
  },
  "log_config": {
    "log_path": "./data/agent_data"
  }
}
```

**Step 2: Run simulation**

```bash
# Make sure MCP services are running
cd agent_tools
python start_mcp_services.py &
cd ..

# Run simulation in DEV mode (no API costs)
DEPLOYMENT_MODE=DEV python main.py configs/position_tracking_test.json
```

**Step 3: Verify results via API**

```bash
# Start API server
uvicorn api.main:app --reload &

# Get job results
curl http://localhost:8000/api/v1/jobs | jq '.'

# Get positions for the job
JOB_ID="<job-id-from-above>"
curl "http://localhost:8000/api/v1/jobs/${JOB_ID}/positions?model=position-tracking-test" | jq '.'
```

**Step 4: Verify position continuity**

Check the output JSON:
1. **Cash continuity:** Each day's starting cash should equal previous day's ending cash
2. **Holdings persistence:** Stock positions should persist across days unless sold
3. **Profit accuracy:** Profit should be 0 when buying/selling (no price change), and non-zero only when prices move

**Step 5: Document test results**

If all looks good, create a commit:

```bash
git add configs/position_tracking_test.json
git commit -m "test: add manual test config for position tracking verification"
```

---

## Task 9: Final Verification and Cleanup

**Step 1: Run complete test suite**

```bash
./venv/bin/python -m pytest tests/ -v --cov=. --cov-report=term-missing --cov-report=html --tb=short
```

Expected: All tests PASS, coverage ≥ 90%

**Step 2: Check for any remaining references to deleted methods**

```bash
git grep -n "get_positions\|get_last_trade\|get_current_prices\|_write_results_to_db\|_calculate_portfolio_value" -- '*.py'
```

Expected: Only references in:
- Test files (mocking for legacy tests)
- Comments explaining the removal
- This plan document

If any production code references these, they need to be removed.

**Step 3: Clean up any debug prints or temporary code**

Review all modified files for:
- Debug `print()` statements
- Commented-out code
- TODO comments that should be addressed

**Step 4: Final commit**

```bash
git add -A
git commit -m "fix: complete position tracking bug fixes - all tests passing"
```

**Step 5: Create summary report**

Create `docs/plans/2025-11-03-position-tracking-fixes-summary.md`:

```markdown
# Position Tracking Bug Fixes - Summary

**Date:** 2025-11-03

**Issue:** Three critical bugs in position tracking system:
1. Cash reset to initial value each trading day
2. Positions lost over non-continuous trading days (weekends)
3. Profit calculations showing trades as losses

## Root Causes

1. **Bugs #1 & #2:** `ModelDayExecutor._write_results_to_db()` called non-existent methods (`get_positions()`, `get_last_trade()`, `get_current_prices()`) on BaseAgent, resulting in corrupt position records with `cash=0` and `holdings=[]`. When `get_current_position_from_db()` retrieved positions for the next day, it found these corrupt records, causing cash resets and position losses.

2. **Bug #3:** Profit calculation compared portfolio value to **previous day's final value** instead of **start-of-day value**. Since buying/selling stocks doesn't change total portfolio value (cash ↓, stock value ↑ equally), this showed trades as having profit=0 or small rounding errors.

## Solution

1. **Removed redundant method:** Deleted `ModelDayExecutor._write_results_to_db()` and `_calculate_portfolio_value()` entirely. Position tracking is now exclusively handled by trade tools (`buy()`, `sell()`) and `add_no_trade_record_to_db()`.

2. **Fixed profit calculation:** Changed all profit calculations to compare against start-of-day portfolio value (action_id=0) instead of previous day's final value. This accurately reflects gains/losses from price movements and strategic trading.

## Files Modified

**Core Changes:**
- `api/model_day_executor.py`: Removed `_write_results_to_db()` call and method definitions
- `agent_tools/tool_trade.py`: Fixed profit calculation in `_buy_impl()` and `_sell_impl()`
- `tools/price_tools.py`: Fixed profit calculation in `add_no_trade_record_to_db()`

**Test Changes:**
- `tests/unit/test_position_tracking_bugs.py`: New tests demonstrating and verifying fixes
- `tests/unit/test_model_day_executor.py`: Updated mock helper and data persistence tests
- `tests/unit/test_model_day_executor_reasoning.py`: Skipped test for removed method
- `tests/integration/test_position_tracking_e2e.py`: New end-to-end integration test

**Documentation:**
- `CHANGELOG.md`: Added fix notes
- `docs/developer/database-schema.md`: Updated profit calculation documentation

## Verification

- All unit tests pass
- All integration tests pass
- Manual testing with 5-day simulation confirms position continuity
- Profit calculations accurate

## Impact

**Before:**
- Cash reset to $10,000 each trading day
- Positions lost after weekends
- Trades showed as $0 profit (misleading)

**After:**
- Cash carries over correctly between days
- Positions persist indefinitely until sold
- Profit accurately reflects price movements and trading strategy
```

**Step 6: Final commit**

```bash
git add docs/plans/2025-11-03-position-tracking-fixes-summary.md
git commit -m "docs: add summary report for position tracking bug fixes"
```

---

## Success Criteria

**All of the following must be true:**

✅ All tests in `tests/unit/test_position_tracking_bugs.py` PASS
✅ All existing unit tests continue to PASS
✅ Integration test demonstrates position continuity across 5 days
✅ Manual testing shows correct cash carry-over
✅ Manual testing shows positions persist over weekends
✅ Manual testing shows profit=0 for trades without price changes
✅ Code coverage maintained at ≥ 90%
✅ No references to deleted methods in production code
✅ Documentation updated
✅ CHANGELOG updated

---

## Rollback Plan

If issues are discovered after deployment:

1. **Revert commits:**
   ```bash
   git revert <commit-hash-range>
   ```

2. **Re-run tests to verify rollback:**
   ```bash
   ./venv/bin/python -m pytest tests/ -v
   ```

3. **Investigate root cause of rollback:**
   - Check logs
   - Review test failures
   - Identify what was missed

4. **Create new fix with additional tests**

---

## Notes for Future Maintainers

**Position Tracking Architecture:**

- **Single source of truth:** Trade tools (`buy()`, `sell()`) and `add_no_trade_record_to_db()` are the ONLY functions that write position records.

- **ModelDayExecutor responsibilities:**
  - Create initial position (action_id=0) on first day via `_initialize_starting_position()`
  - Manage trading sessions and reasoning logs
  - **Does NOT** write position records directly

- **Action ID sequence:**
  - `action_id=0`: Start-of-day baseline (created once, used for profit calculations)
  - `action_id=1+`: Incremented for each trade or no-trade action

- **Profit calculation:**
  - Always compare to start-of-day (action_id=0) portfolio value
  - Never compare to previous day's final value
  - This ensures trades don't show false profits/losses

**Testing:**

- `test_position_tracking_bugs.py` contains regression tests for these specific bugs
- If modifying position tracking, run these tests first
- Integration test (`test_position_tracking_e2e.py`) verifies multi-day continuity