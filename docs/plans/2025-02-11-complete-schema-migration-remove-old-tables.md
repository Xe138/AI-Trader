# Complete Schema Migration and Remove Old Tables Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Complete migration from old schema (trading_sessions, positions, reasoning_logs) to new schema (trading_days, holdings, actions) and remove all old-schema code.

**Architecture:** Two-phase migration: (1) Fix trade tools and model_day_executor to use new schema exclusively, (2) Remove all old-schema code including /reasoning endpoint, old tables, and tests.

**Tech Stack:** Python 3.11, SQLite, FastAPI, pytest

---

## Phase 1: Complete Migration to New Schema

### Task 1: Fix Trade Tools - Write to Actions Table

**Files:**
- Modify: `agent_tools/tool_trade.py:172-200` (buy function)
- Modify: `agent_tools/tool_trade.py:320-348` (sell function)
- Test: `tests/unit/test_trade_tools_new_schema.py` (create new)

**Context:** Trade tools currently write to old `positions` table and old `holdings` table with `position_id` FK. Need to write to new `actions` table with `trading_day_id` FK instead.

**Step 1: Write failing test for buy action**

Create `tests/unit/test_trade_tools_new_schema.py`:

```python
"""Test trade tools write to new schema (actions table)."""

import pytest
import sqlite3
from agent_tools.tool_trade import _buy_impl
from api.database import Database
from tools.deployment_config import get_db_path


@pytest.fixture
def test_db():
    """Create test database with new schema."""
    db_path = ":memory:"
    db = Database(db_path)

    # Create jobs table (prerequisite)
    db.connection.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            job_id TEXT PRIMARY KEY,
            status TEXT,
            created_at TEXT
        )
    """)

    db.connection.execute("""
        INSERT INTO jobs (job_id, status, created_at)
        VALUES ('test-job-123', 'running', '2025-01-15T10:00:00Z')
    """)

    # Create trading_days record
    trading_day_id = db.create_trading_day(
        job_id='test-job-123',
        model='test-model',
        date='2025-01-15',
        starting_cash=10000.0,
        starting_portfolio_value=10000.0,
        daily_profit=0.0,
        daily_return_pct=0.0,
        days_since_last_trading=0
    )

    db.connection.commit()

    yield db, trading_day_id

    db.connection.close()


def test_buy_writes_to_actions_table(test_db, monkeypatch):
    """Test buy() writes action record to actions table."""
    db, trading_day_id = test_db

    # Mock get_db_path to return our test db
    monkeypatch.setattr('agent_tools.tool_trade.get_db_connection',
                       lambda x: db.connection)

    # Mock runtime config
    monkeypatch.setenv('RUNTIME_ENV_PATH', '/tmp/test_runtime.json')

    # Create mock runtime config file
    import json
    with open('/tmp/test_runtime.json', 'w') as f:
        json.dump({
            'TODAY_DATE': '2025-01-15',
            'SIGNATURE': 'test-model',
            'JOB_ID': 'test-job-123',
            'TRADING_DAY_ID': trading_day_id
        }, f)

    # Mock price data
    monkeypatch.setattr('agent_tools.tool_trade.get_close_price',
                       lambda sym, date: 150.0)

    # Execute buy
    result = _buy_impl(
        symbol='AAPL',
        amount=10,
        signature='test-model',
        today_date='2025-01-15',
        job_id='test-job-123',
        trading_day_id=trading_day_id
    )

    # Verify action record created
    cursor = db.connection.execute("""
        SELECT action_type, symbol, quantity, price, trading_day_id
        FROM actions
        WHERE trading_day_id = ?
    """, (trading_day_id,))

    row = cursor.fetchone()
    assert row is not None, "Action record should exist"
    assert row[0] == 'buy'
    assert row[1] == 'AAPL'
    assert row[2] == 10
    assert row[3] == 150.0
    assert row[4] == trading_day_id

    # Verify NO write to old positions table
    cursor = db.connection.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='positions'
    """)
    assert cursor.fetchone() is None, "Old positions table should not exist"


def test_sell_writes_to_actions_table(test_db, monkeypatch):
    """Test sell() writes action record to actions table."""
    db, trading_day_id = test_db

    # Setup: Create starting holdings
    db.create_holding(trading_day_id, 'AAPL', 10)
    db.connection.commit()

    # Mock dependencies
    monkeypatch.setattr('agent_tools.tool_trade.get_db_connection',
                       lambda x: db.connection)
    monkeypatch.setenv('RUNTIME_ENV_PATH', '/tmp/test_runtime.json')

    import json
    with open('/tmp/test_runtime.json', 'w') as f:
        json.dump({
            'TODAY_DATE': '2025-01-15',
            'SIGNATURE': 'test-model',
            'JOB_ID': 'test-job-123',
            'TRADING_DAY_ID': trading_day_id
        }, f)

    monkeypatch.setattr('agent_tools.tool_trade.get_close_price',
                       lambda sym, date: 160.0)

    # Execute sell
    result = _buy_impl(
        symbol='AAPL',
        amount=5,
        signature='test-model',
        today_date='2025-01-15',
        job_id='test-job-123',
        trading_day_id=trading_day_id
    )

    # Verify action record created
    cursor = db.connection.execute("""
        SELECT action_type, symbol, quantity, price
        FROM actions
        WHERE trading_day_id = ? AND action_type = 'sell'
    """, (trading_day_id,))

    row = cursor.fetchone()
    assert row is not None
    assert row[0] == 'sell'
    assert row[1] == 'AAPL'
    assert row[2] == 5
    assert row[3] == 160.0
```

**Step 2: Run test to verify it fails**

Run: `./venv/bin/python -m pytest tests/unit/test_trade_tools_new_schema.py -v`

Expected: FAIL - _buy_impl doesn't accept trading_day_id parameter, doesn't write to actions table

**Step 3: Modify buy function to write to actions table**

Edit `agent_tools/tool_trade.py`:

Find the `_buy_impl` function signature (around line 115) and add `trading_day_id` parameter:

```python
def _buy_impl(symbol: str, amount: int, signature: str = None, today_date: str = None,
              job_id: str = None, session_id: int = None, trading_day_id: int = None) -> Dict[str, Any]:
    """
    Internal buy implementation.

    Args:
        symbol: Stock symbol
        amount: Number of shares
        signature: Model signature (injected)
        today_date: Trading date (injected)
        job_id: Job ID (injected)
        session_id: Session ID (injected, DEPRECATED)
        trading_day_id: Trading day ID (injected)
    """
```

Replace the old write logic (lines 172-196) with new actions write:

```python
        # Step 6: Write to actions table (NEW SCHEMA)
        if trading_day_id is None:
            # Get trading_day_id from runtime config if not provided
            from tools.general_tools import get_config_value
            trading_day_id = get_config_value('TRADING_DAY_ID')

            if trading_day_id is None:
                raise ValueError("trading_day_id not found in runtime config")

        created_at = datetime.utcnow().isoformat() + "Z"

        cursor.execute("""
            INSERT INTO actions (
                trading_day_id, action_type, symbol, quantity, price, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            trading_day_id, "buy", symbol, amount, this_symbol_price, created_at
        ))

        # NOTE: Holdings are written by BaseAgent at end of day, not per-trade
        # This keeps the data model clean (one holdings snapshot per day)

        conn.commit()
        print(f"[buy] {signature} bought {amount} shares of {symbol} at ${this_symbol_price}")
        return new_position
```

Remove the old holdings write code (lines 190-196):

```python
        # DELETE THIS SECTION:
        # position_id = cursor.lastrowid
        #
        # # Step 7: Write to holdings table
        # for sym, qty in new_position.items():
        #     if sym != "CASH":
        #         cursor.execute("""
        #             INSERT INTO holdings (position_id, symbol, quantity)
        #             VALUES (?, ?, ?)
        #         """, (position_id, sym, qty))
```

Remove old positions table write (lines 175-186):

```python
        # DELETE THIS SECTION:
        # cursor.execute("""
        #     INSERT INTO positions (
        #         job_id, date, model, action_id, action_type, symbol,
        #         amount, price, cash, portfolio_value, daily_profit,
        #         daily_return_pct, session_id, created_at
        #     )
        #     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        # """, (...))
```

**Step 4: Apply same changes to sell function**

Edit `agent_tools/tool_trade.py` around line 280 (sell function):

Update `_sell_impl` signature to add `trading_day_id`:

```python
def _sell_impl(symbol: str, amount: int, signature: str = None, today_date: str = None,
               job_id: str = None, session_id: int = None, trading_day_id: int = None) -> Dict[str, Any]:
```

Replace sell write logic (around lines 320-348) with actions write:

```python
        # Step 6: Write to actions table (NEW SCHEMA)
        if trading_day_id is None:
            from tools.general_tools import get_config_value
            trading_day_id = get_config_value('TRADING_DAY_ID')

            if trading_day_id is None:
                raise ValueError("trading_day_id not found in runtime config")

        created_at = datetime.utcnow().isoformat() + "Z"

        cursor.execute("""
            INSERT INTO actions (
                trading_day_id, action_type, symbol, quantity, price, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            trading_day_id, "sell", symbol, amount, this_symbol_price, created_at
        ))

        conn.commit()
        print(f"[sell] {signature} sold {amount} shares of {symbol} at ${this_symbol_price}")
        return new_position
```

Remove old positions and holdings writes from sell function.

**Step 5: Update public buy/sell functions to pass trading_day_id**

Update the `buy()` MCP tool (around line 211):

```python
@mcp.tool()
def buy(symbol: str, amount: int, signature: str = None, today_date: str = None,
        job_id: str = None, session_id: int = None, trading_day_id: int = None) -> Dict[str, Any]:
    """
    Buy stock shares.

    Args:
        symbol: Stock symbol (e.g., "AAPL", "MSFT", "GOOGL")
        amount: Number of shares to buy (positive integer)

    Returns:
        Dict[str, Any]:
          - Success: {"CASH": remaining_cash, "SYMBOL": shares, ...}
          - Failure: {"error": error_message, ...}

    Note: signature, today_date, job_id, session_id, trading_day_id are
    automatically injected by the system. Do not provide these parameters.
    """
    return _buy_impl(symbol, amount, signature, today_date, job_id, session_id, trading_day_id)
```

Update the `sell()` MCP tool similarly (around line 375).

**Step 6: Update context injector to inject trading_day_id**

Edit `agent/context_injector.py` to add trading_day_id to injected params:

Find the `inject_parameters` method and add:

```python
def inject_parameters(self, tool_call):
    """Inject context into tool parameters."""
    params = tool_call.get('parameters', {})
    params['signature'] = self.signature
    params['today_date'] = self.today_date
    params['job_id'] = self.job_id
    params['session_id'] = self.session_id  # Deprecated but kept for compatibility
    params['trading_day_id'] = self.trading_day_id  # NEW
    tool_call['parameters'] = params
    return tool_call
```

Add trading_day_id to ContextInjector __init__:

```python
class ContextInjector:
    def __init__(self, signature: str, today_date: str, job_id: str,
                 session_id: int, trading_day_id: int):
        self.signature = signature
        self.today_date = today_date
        self.job_id = job_id
        self.session_id = session_id  # Deprecated
        self.trading_day_id = trading_day_id
```

**Step 7: Update BaseAgent to pass trading_day_id to context injector**

Edit `agent/base_agent/base_agent.py` around line 540:

```python
            # Create and inject context with correct values
            from agent.context_injector import ContextInjector
            context_injector = ContextInjector(
                signature=self.signature,
                today_date=today_date,
                job_id=job_id,
                session_id=0,  # Deprecated, use trading_day_id
                trading_day_id=trading_day_id  # NEW
            )
```

**Step 8: Update runtime config to include TRADING_DAY_ID**

Edit `api/runtime_manager.py` to write TRADING_DAY_ID:

Find `create_runtime_config` method and update to accept trading_day_id:

```python
def create_runtime_config(self, job_id: str, model_sig: str, date: str,
                         trading_day_id: int = None) -> str:
    """
    Create isolated runtime config for a model-day execution.

    Args:
        job_id: Job UUID
        model_sig: Model signature
        date: Trading date
        trading_day_id: Trading day record ID (optional, can be set later)
    """
    config_data = {
        "TODAY_DATE": date,
        "SIGNATURE": model_sig,
        "IF_TRADE": True,
        "JOB_ID": job_id,
        "TRADING_DAY_ID": trading_day_id  # NEW
    }

    # ... rest of method
```

**Step 9: Update model_day_executor to set TRADING_DAY_ID in runtime config**

Edit `api/model_day_executor.py` around line 530:

After creating trading_day record, update runtime config:

```python
            # Create trading_day record
            trading_day_id = db.create_trading_day(...)
            conn.commit()

            # Update runtime config with trading_day_id
            from tools.general_tools import write_config_value
            write_config_value('TRADING_DAY_ID', trading_day_id)
```

**Step 10: Run tests to verify they pass**

Run: `./venv/bin/python -m pytest tests/unit/test_trade_tools_new_schema.py -v`

Expected: PASS (both tests)

**Step 11: Commit**

```bash
git add agent_tools/tool_trade.py agent/context_injector.py agent/base_agent/base_agent.py api/runtime_manager.py api/model_day_executor.py tests/unit/test_trade_tools_new_schema.py
git commit -m "feat: migrate trade tools to write to actions table (new schema)"
```

---

### Task 2: Remove Old Schema Writes from model_day_executor

**Files:**
- Modify: `api/model_day_executor.py:291-437`
- Test: `tests/integration/test_model_day_executor_new_schema.py` (create new)

**Context:** model_day_executor currently writes to old trading_sessions and reasoning_logs tables. BaseAgent already writes to trading_days with reasoning, so these are duplicates.

**Step 1: Write test for model_day_executor with new schema**

Create `tests/integration/test_model_day_executor_new_schema.py`:

```python
"""Test model_day_executor uses new schema exclusively."""

import pytest
from api.model_day_executor import ModelDayExecutor
from api.database import Database


@pytest.mark.asyncio
async def test_executor_writes_only_to_new_schema(tmp_path, monkeypatch):
    """Verify executor writes to trading_days, not old tables."""

    # Create test database
    db_path = str(tmp_path / "test.db")
    db = Database(db_path)

    # Create test config
    config_path = str(tmp_path / "config.json")
    import json
    with open(config_path, 'w') as f:
        json.dump({
            "models": [{
                "signature": "test-model",
                "basemodel": "gpt-3.5-turbo",
                "enabled": True
            }],
            "agent_config": {
                "stock_symbols": ["AAPL"],
                "initial_cash": 10000.0,
                "max_steps": 10
            },
            "log_config": {"log_path": str(tmp_path / "logs")}
        }, f)

    # Mock agent initialization and execution
    from unittest.mock import AsyncMock, MagicMock
    mock_agent = MagicMock()
    mock_agent.run_trading_session = AsyncMock(return_value={"success": True})
    mock_agent.get_conversation_history = MagicMock(return_value=[])

    monkeypatch.setattr('api.model_day_executor.BaseAgent',
                       lambda **kwargs: mock_agent)

    # Execute
    executor = ModelDayExecutor(
        job_id='test-job-123',
        date='2025-01-15',
        model_sig='test-model',
        config_path=config_path,
        db_path=db_path
    )

    result = await executor.execute_async()

    # Verify: trading_days record exists
    cursor = db.connection.execute("""
        SELECT COUNT(*) FROM trading_days
        WHERE job_id = ? AND date = ? AND model = ?
    """, ('test-job-123', '2025-01-15', 'test-model'))

    count = cursor.fetchone()[0]
    assert count == 1, "Should have exactly one trading_days record"

    # Verify: NO trading_sessions records
    cursor = db.connection.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='trading_sessions'
    """)
    assert cursor.fetchone() is None, "trading_sessions table should not exist"

    # Verify: NO reasoning_logs records
    cursor = db.connection.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='reasoning_logs'
    """)
    assert cursor.fetchone() is None, "reasoning_logs table should not exist"
```

**Step 2: Run test to verify it fails**

Run: `./venv/bin/python -m pytest tests/integration/test_model_day_executor_new_schema.py -v`

Expected: FAIL - old tables still being created/written

**Step 3: Remove _create_trading_session method**

Edit `api/model_day_executor.py`:

Delete the `_create_trading_session` method (lines 291-312):

```python
    # DELETE THIS METHOD:
    # def _create_trading_session(self, cursor) -> int:
    #     """Create trading session record."""
    #     from datetime import datetime
    #     started_at = datetime.utcnow().isoformat() + "Z"
    #     cursor.execute("""
    #         INSERT INTO trading_sessions (...)
    #         VALUES (?, ?, ?, ?)
    #     """, (...))
    #     return cursor.lastrowid
```

**Step 4: Remove _store_reasoning_logs method**

Delete the `_store_reasoning_logs` method (lines 359-397):

```python
    # DELETE THIS METHOD:
    # async def _store_reasoning_logs(...):
    #     """Store reasoning logs with AI-generated summaries."""
    #     for idx, message in enumerate(conversation):
    #         ...
```

**Step 5: Remove _update_session_summary method**

Delete the `_update_session_summary` method (lines 399-437):

```python
    # DELETE THIS METHOD:
    # async def _update_session_summary(...):
    #     """Update session with overall summary."""
    #     ...
```

**Step 6: Remove _initialize_starting_position method**

Delete the `_initialize_starting_position` method (lines 314-357):

```python
    # DELETE THIS METHOD:
    # def _initialize_starting_position(...):
    #     """Initialize starting position if no prior positions exist."""
    #     ...
```

Note: This is no longer needed because PnLCalculator handles first-day case (returns 0 profit/return).

**Step 7: Remove calls to deleted methods in execute_async**

Edit `api/model_day_executor.py` in the `execute_async` method:

Remove the session creation (around line 123-127):

```python
            # DELETE THESE LINES:
            # # Create trading session at start
            # conn = get_db_connection(self.db_path)
            # cursor = conn.cursor()
            # session_id = self._create_trading_session(cursor)
            # conn.commit()
```

Remove the starting position initialization (around line 129-131):

```python
            # DELETE THESE LINES:
            # # Initialize starting position if this is first day
            # self._initialize_starting_position(cursor, session_id)
            # conn.commit()
```

Remove the reasoning logs storage (around line 160):

```python
            # DELETE THIS LINE:
            # await self._store_reasoning_logs(cursor, session_id, conversation, agent)
```

Remove the session summary update (around line 163):

```python
            # DELETE THIS LINE:
            # await self._update_session_summary(cursor, session_id, conversation, agent)
```

Update the docstring (lines 107-111) to reflect new schema:

```python
        """
        Execute trading session and persist results (async version).

        Returns:
            Result dict with success status and metadata

        Process:
            1. Update job_detail status to 'running'
            2. Create trading_day record with P&L metrics
            3. Initialize and run trading agent
            4. Agent writes actions and updates trading_day
            5. Update job_detail status to 'completed' or 'failed'
            6. Cleanup runtime config

        SQLite writes:
            - trading_days: Complete day record with P&L, reasoning, holdings
            - actions: Trade execution ledger
            - holdings: Ending positions snapshot
        """
```

**Step 8: Run test to verify it passes**

Run: `./venv/bin/python -m pytest tests/integration/test_model_day_executor_new_schema.py -v`

Expected: PASS

**Step 9: Commit**

```bash
git add api/model_day_executor.py tests/integration/test_model_day_executor_new_schema.py
git commit -m "refactor: remove old schema writes from model_day_executor"
```

---

### Task 3: Update get_current_position_from_db to Query New Schema

**Files:**
- Modify: `agent_tools/tool_trade.py:50-90`
- Test: `tests/unit/test_get_position_new_schema.py` (create new)

**Context:** `get_current_position_from_db()` currently queries old positions table. Need to query trading_days + holdings + actions instead.

**Step 1: Write failing test**

Create `tests/unit/test_get_position_new_schema.py`:

```python
"""Test get_current_position_from_db queries new schema."""

import pytest
from agent_tools.tool_trade import get_current_position_from_db
from api.database import Database


def test_get_position_from_new_schema():
    """Test position retrieval from trading_days + holdings."""

    # Create test database
    db = Database(":memory:")

    # Create trading_day with holdings
    trading_day_id = db.create_trading_day(
        job_id='test-job-123',
        model='test-model',
        date='2025-01-15',
        starting_cash=10000.0,
        starting_portfolio_value=10000.0,
        daily_profit=0.0,
        daily_return_pct=0.0,
        days_since_last_trading=0
    )

    # Add ending holdings
    db.create_holding(trading_day_id, 'AAPL', 10)
    db.create_holding(trading_day_id, 'MSFT', 5)

    # Update ending cash
    db.connection.execute("""
        UPDATE trading_days
        SET ending_cash = 8000.0
        WHERE id = ?
    """, (trading_day_id,))

    db.connection.commit()

    # Query position
    position, action_id = get_current_position_from_db(
        job_id='test-job-123',
        signature='test-model',
        today_date='2025-01-15'
    )

    # Verify
    assert position['AAPL'] == 10
    assert position['MSFT'] == 5
    assert position['CASH'] == 8000.0
    assert action_id == 2  # 2 holdings = 2 actions


def test_get_position_first_day():
    """Test position retrieval on first day (no prior data)."""

    db = Database(":memory:")

    # Query position (no data exists)
    position, action_id = get_current_position_from_db(
        job_id='test-job-123',
        signature='test-model',
        today_date='2025-01-15'
    )

    # Should return initial position
    assert position['CASH'] == 10000.0  # Default initial cash
    assert action_id == 0
```

**Step 2: Run test to verify it fails**

Run: `./venv/bin/python -m pytest tests/unit/test_get_position_new_schema.py -v`

Expected: FAIL - function queries old positions table

**Step 3: Rewrite get_current_position_from_db to query new schema**

Edit `agent_tools/tool_trade.py` around line 50:

```python
def get_current_position_from_db(
    job_id: str,
    signature: str,
    today_date: str,
    initial_cash: float = 10000.0
) -> Tuple[Dict[str, float], int]:
    """
    Get current position from database (new schema).

    Queries most recent trading_day record for this job+model up to today_date.
    Returns ending holdings and cash from that day.

    Args:
        job_id: Job UUID
        signature: Model signature
        today_date: Current trading date
        initial_cash: Initial cash if no prior data

    Returns:
        (position_dict, action_count) where:
          - position_dict: {"AAPL": 10, "MSFT": 5, "CASH": 8500.0}
          - action_count: Number of holdings (for action_id tracking)
    """
    from tools.deployment_config import get_db_path
    import sqlite3

    db_path = get_db_path("data/trading.db")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Query most recent trading_day up to today_date
    cursor.execute("""
        SELECT id, ending_cash
        FROM trading_days
        WHERE job_id = ? AND model = ? AND date <= ?
        ORDER BY date DESC
        LIMIT 1
    """, (job_id, signature, today_date))

    row = cursor.fetchone()

    if row is None:
        # First day - return initial position
        conn.close()
        return {"CASH": initial_cash}, 0

    trading_day_id, ending_cash = row

    # Query holdings for that day
    cursor.execute("""
        SELECT symbol, quantity
        FROM holdings
        WHERE trading_day_id = ?
    """, (trading_day_id,))

    holdings_rows = cursor.fetchall()
    conn.close()

    # Build position dict
    position = {"CASH": ending_cash}
    for symbol, quantity in holdings_rows:
        position[symbol] = quantity

    # Action count is number of holdings (used for action_id)
    action_count = len(holdings_rows)

    return position, action_count
```

**Step 4: Run test to verify it passes**

Run: `./venv/bin/python -m pytest tests/unit/test_get_position_new_schema.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add agent_tools/tool_trade.py tests/unit/test_get_position_new_schema.py
git commit -m "refactor: update get_current_position_from_db to query new schema"
```

---

## Phase 2: Remove Old Schema Code

### Task 4: Remove /reasoning Endpoint

**Files:**
- Modify: `api/main.py:118-161` (delete Pydantic models)
- Modify: `api/main.py:432-606` (delete endpoint)
- Test: `tests/unit/test_api_reasoning_endpoint.py` (delete file)
- Modify: `API_REFERENCE.md:666-1050` (delete documentation)

**Step 1: Write test for /results endpoint covering reasoning use case**

Create `tests/integration/test_results_replaces_reasoning.py`:

```python
"""Verify /results endpoint replaces /reasoning endpoint."""

import pytest
from fastapi.testclient import TestClient
from api.main import create_app
from api.database import Database


def test_results_with_full_reasoning_replaces_old_endpoint():
    """Test /results?reasoning=full provides same data as old /reasoning."""

    # Create test app
    app = create_app(db_path=":memory:")
    app.state.test_mode = True
    client = TestClient(app)

    # Setup: Create test data in new schema
    db = Database(":memory:")

    trading_day_id = db.create_trading_day(
        job_id='test-job-123',
        model='test-model',
        date='2025-01-15',
        starting_cash=10000.0,
        starting_portfolio_value=10000.0,
        daily_profit=0.0,
        daily_return_pct=0.0,
        days_since_last_trading=0
    )

    # Add actions
    db.create_action(trading_day_id, 'buy', 'AAPL', 10, 150.0)

    # Add holdings
    db.create_holding(trading_day_id, 'AAPL', 10)

    # Update with reasoning
    import json
    db.connection.execute("""
        UPDATE trading_days
        SET ending_cash = 8500.0,
            ending_portfolio_value = 10000.0,
            reasoning_summary = 'Bought AAPL based on earnings',
            reasoning_full = ?,
            total_actions = 1
        WHERE id = ?
    """, (json.dumps([
        {"role": "user", "content": "System prompt"},
        {"role": "assistant", "content": "I will buy AAPL"}
    ]), trading_day_id))

    db.connection.commit()

    # Query new endpoint
    response = client.get("/results?job_id=test-job-123&reasoning=full")

    assert response.status_code == 200
    data = response.json()

    # Verify structure matches old endpoint needs
    assert data['count'] == 1
    result = data['results'][0]

    assert result['date'] == '2025-01-15'
    assert result['model'] == 'test-model'
    assert result['trades'][0]['action_type'] == 'buy'
    assert result['trades'][0]['symbol'] == 'AAPL'
    assert isinstance(result['reasoning'], list)
    assert len(result['reasoning']) == 2


def test_reasoning_endpoint_returns_404():
    """Verify /reasoning endpoint is removed."""

    app = create_app(db_path=":memory:")
    client = TestClient(app)

    response = client.get("/reasoning?job_id=test-job-123")

    assert response.status_code == 404
```

**Step 2: Run test to verify new endpoint works**

Run: `./venv/bin/python -m pytest tests/integration/test_results_replaces_reasoning.py::test_results_with_full_reasoning_replaces_old_endpoint -v`

Expected: PASS (new endpoint already works)

Run: `./venv/bin/python -m pytest tests/integration/test_results_replaces_reasoning.py::test_reasoning_endpoint_returns_404 -v`

Expected: FAIL (old endpoint still exists)

**Step 3: Delete Pydantic models for old endpoint**

Edit `api/main.py`:

Delete these model classes (lines 118-161):

```python
# DELETE THESE CLASSES:
# class ReasoningMessage(BaseModel):
#     """Individual message in a reasoning conversation."""
#     ...
#
# class PositionSummary(BaseModel):
#     """Trading position summary."""
#     ...
#
# class TradingSessionResponse(BaseModel):
#     """Single trading session with positions and optional conversation."""
#     ...
#
# class ReasoningResponse(BaseModel):
#     """Response body for GET /reasoning."""
#     ...
```

**Step 4: Delete /reasoning endpoint**

Delete the endpoint function (lines 432-606):

```python
    # DELETE THIS ENTIRE FUNCTION:
    # @app.get("/reasoning", response_model=ReasoningResponse)
    # async def get_reasoning(...):
    #     """Query reasoning logs from trading sessions."""
    #     ...
```

**Step 5: Run test to verify endpoint removed**

Run: `./venv/bin/python -m pytest tests/integration/test_results_replaces_reasoning.py::test_reasoning_endpoint_returns_404 -v`

Expected: PASS

**Step 6: Delete old endpoint tests**

```bash
rm tests/unit/test_api_reasoning_endpoint.py
```

**Step 7: Remove /reasoning documentation from API_REFERENCE.md**

Edit `API_REFERENCE.md`:

Find and delete the `/reasoning` endpoint section (should be around lines 666-1050):

```markdown
<!-- DELETE THIS ENTIRE SECTION:
### GET /reasoning

Query reasoning logs and conversation history from trading sessions.
...
-->
```

**Step 8: Commit**

```bash
git add api/main.py API_REFERENCE.md tests/integration/test_results_replaces_reasoning.py
git rm tests/unit/test_api_reasoning_endpoint.py
git commit -m "feat: remove /reasoning endpoint (replaced by /results)"
```

---

### Task 5: Drop Old Database Tables

**Files:**
- Create: `api/migrations/002_drop_old_schema.py`
- Modify: `api/database.py:161-177` (remove table creation)
- Test: `tests/unit/test_old_schema_removed.py` (create new)

**Step 1: Write test verifying old tables don't exist**

Create `tests/unit/test_old_schema_removed.py`:

```python
"""Verify old schema tables are removed."""

import pytest
from api.database import Database


def test_old_tables_do_not_exist():
    """Verify trading_sessions, old positions, reasoning_logs don't exist."""

    db = Database(":memory:")

    # Query sqlite_master for old tables
    cursor = db.connection.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name IN (
            'trading_sessions', 'reasoning_logs'
        )
    """)

    tables = cursor.fetchall()

    assert len(tables) == 0, f"Old tables should not exist, found: {tables}"


def test_new_tables_exist():
    """Verify new schema tables exist."""

    db = Database(":memory:")

    cursor = db.connection.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name IN (
            'trading_days', 'holdings', 'actions'
        )
        ORDER BY name
    """)

    tables = [row[0] for row in cursor.fetchall()]

    assert 'trading_days' in tables
    assert 'holdings' in tables
    assert 'actions' in tables
```

**Step 2: Run test to verify it fails**

Run: `./venv/bin/python -m pytest tests/unit/test_old_schema_removed.py -v`

Expected: FAIL - old tables still exist

**Step 3: Create migration script to drop old tables**

Create `api/migrations/002_drop_old_schema.py`:

```python
"""Drop old schema tables (trading_sessions, positions, reasoning_logs)."""


def drop_old_schema(db):
    """
    Drop old schema tables that have been replaced by new schema.

    Old schema:
    - trading_sessions → replaced by trading_days
    - positions (action-centric) → replaced by trading_days + actions + holdings
    - reasoning_logs → replaced by trading_days.reasoning_full

    Args:
        db: Database instance
    """

    # Drop reasoning_logs (child table first)
    db.connection.execute("DROP TABLE IF EXISTS reasoning_logs")

    # Drop positions (note: this is the OLD action-centric positions table)
    # The new schema doesn't have a positions table at all
    db.connection.execute("DROP TABLE IF EXISTS positions")

    # Drop trading_sessions
    db.connection.execute("DROP TABLE IF EXISTS trading_sessions")

    db.connection.commit()

    print("✅ Dropped old schema tables: trading_sessions, positions, reasoning_logs")


if __name__ == "__main__":
    """Run migration standalone."""
    from api.database import Database
    from tools.deployment_config import get_db_path

    db_path = get_db_path("data/trading.db")
    db = Database(db_path)

    drop_old_schema(db)

    print(f"✅ Migration complete: {db_path}")
```

**Step 4: Remove old table creation from database.py**

Edit `api/database.py`:

Find and delete the trading_sessions table creation (around lines 161-172):

```python
        # DELETE THIS SECTION:
        # self.connection.execute("""
        #     CREATE TABLE IF NOT EXISTS trading_sessions (
        #         id INTEGER PRIMARY KEY AUTOINCREMENT,
        #         job_id TEXT NOT NULL,
        #         date TEXT NOT NULL,
        #         model TEXT NOT NULL,
        #         session_summary TEXT,
        #         started_at TEXT,
        #         completed_at TEXT,
        #         total_messages INTEGER,
        #         FOREIGN KEY (job_id) REFERENCES jobs(job_id)
        #     )
        # """)
```

Delete the reasoning_logs table creation (around lines 177-192):

```python
        # DELETE THIS SECTION:
        # self.connection.execute("""
        #     CREATE TABLE IF NOT EXISTS reasoning_logs (
        #         id INTEGER PRIMARY KEY AUTOINCREMENT,
        #         session_id INTEGER NOT NULL,
        #         message_index INTEGER NOT NULL,
        #         role TEXT NOT NULL,
        #         content TEXT NOT NULL,
        #         summary TEXT,
        #         tool_name TEXT,
        #         tool_input TEXT,
        #         timestamp TEXT,
        #         FOREIGN KEY (session_id) REFERENCES trading_sessions(id) ON DELETE CASCADE
        #     )
        # """)
```

Note: Don't delete the commented-out positions table code (lines 123-148) - that's already commented out and serves as reference.

**Step 5: Run migration**

Run: `./venv/bin/python api/migrations/002_drop_old_schema.py`

Expected: Output showing tables dropped

**Step 6: Run test to verify it passes**

Run: `./venv/bin/python -m pytest tests/unit/test_old_schema_removed.py -v`

Expected: PASS

**Step 7: Commit**

```bash
git add api/migrations/002_drop_old_schema.py api/database.py tests/unit/test_old_schema_removed.py
git commit -m "feat: drop old schema tables (trading_sessions, positions, reasoning_logs)"
```

---

### Task 6: Remove Old-Schema Tests

**Files:**
- Delete: `tests/integration/test_reasoning_e2e.py`
- Delete: `tests/unit/test_position_tracking_bugs.py`
- Modify: `tests/unit/test_database.py:290-610` (remove old-schema tests)

**Step 1: Identify tests to remove**

Run grep to find tests using old tables:

```bash
grep -l "trading_sessions\|reasoning_logs" tests/**/*.py
```

**Step 2: Delete test files using old schema**

```bash
git rm tests/integration/test_reasoning_e2e.py
git rm tests/unit/test_position_tracking_bugs.py
```

**Step 3: Remove old-schema tests from test_database.py**

Edit `tests/unit/test_database.py`:

Find and delete tests that write to old positions table (around lines 290-610):

Look for tests like:
- `test_get_last_position_for_model`
- `test_position_tracking_multiple_days`
- Any test that uses `INSERT INTO positions`

Delete these test functions entirely.

**Step 4: Run remaining tests to verify they pass**

Run: `./venv/bin/python -m pytest tests/unit/test_database.py -v`

Expected: PASS (all remaining tests)

**Step 5: Commit**

```bash
git add tests/unit/test_database.py
git commit -m "test: remove old-schema tests"
```

---

### Task 7: Update CHANGELOG with Breaking Changes

**Files:**
- Modify: `CHANGELOG.md`

**Step 1: Add breaking changes section**

Edit `CHANGELOG.md`:

Add to the `[Unreleased]` section:

```markdown
## [Unreleased]

### BREAKING CHANGES

#### Schema Migration: Old Tables Removed

The following database tables have been **removed** and replaced with new schema:

**Removed Tables:**
- `trading_sessions` → Replaced by `trading_days`
- `positions` (old action-centric version) → Replaced by `trading_days` + `actions` + `holdings`
- `reasoning_logs` → Replaced by `trading_days.reasoning_full` (JSON column)

**Migration Required:**
- If you have existing data in old tables, export it before upgrading
- New installations automatically use new schema
- Old data cannot be automatically migrated (different data model)

**Database Path:**
- Production: `data/trading.db`
- Development: `data/trading_dev.db`

#### API Endpoint Removed: /reasoning

The `/reasoning` endpoint has been **removed** and replaced by `/results` with reasoning parameter.

**Migration Guide:**

| Old Endpoint | New Endpoint |
|--------------|--------------|
| `GET /reasoning?job_id=X` | `GET /results?job_id=X&reasoning=summary` |
| `GET /reasoning?job_id=X&include_full_conversation=true` | `GET /results?job_id=X&reasoning=full` |

**Benefits of New Endpoint:**
- Day-centric structure (easier to understand portfolio progression)
- Daily P&L metrics included
- AI-generated reasoning summaries (2-3 sentences)
- Unified data model

**Response Structure Changes:**

Old `/reasoning` returned:
```json
{
  "sessions": [
    {
      "session_id": 1,
      "positions": [{"action_id": 0, "cash_after": 10000, ...}],
      "conversation": [...]
    }
  ]
}
```

New `/results?reasoning=full` returns:
```json
{
  "results": [
    {
      "date": "2025-01-15",
      "starting_position": {"holdings": [], "cash": 10000},
      "daily_metrics": {"profit": 0.0, "return_pct": 0.0},
      "trades": [{"action_type": "buy", "symbol": "AAPL", ...}],
      "final_position": {"holdings": [...], "cash": 8500},
      "reasoning": [...]
    }
  ]
}
```

### Added

- New schema: `trading_days`, `holdings`, `actions` tables
- Daily P&L calculation at start of each trading day
- AI-generated reasoning summaries during simulation
- Unified `/results` endpoint with reasoning parameter

### Changed

- Trade tools now write to `actions` table instead of `positions`
- `model_day_executor` simplified (removed duplicate writes)
- `get_current_position_from_db()` queries new schema

### Removed

- `/reasoning` endpoint (use `/results?reasoning=full` instead)
- Old database tables: `trading_sessions`, `positions`, `reasoning_logs`
- Pydantic models: `ReasoningMessage`, `PositionSummary`, `TradingSessionResponse`, `ReasoningResponse`
```

**Step 2: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: add breaking changes for schema migration"
```

---

### Task 8: Final Verification

**Files:**
- Test: Run full test suite
- Test: Run end-to-end simulation

**Step 1: Run full test suite**

Run: `./venv/bin/python -m pytest tests/ -v --tb=short`

Expected: All tests pass (old-schema tests removed)

**Step 2: Run end-to-end test with actual simulation**

Run: `DEPLOYMENT_MODE=DEV python main.py configs/default_config.json`

Expected:
- Simulation completes successfully
- Only new schema tables exist in database
- `/results` endpoint returns data
- `/reasoning` endpoint returns 404

**Step 3: Verify database schema**

Run:
```bash
sqlite3 data/trading_dev.db ".schema" | grep -E "(trading_sessions|positions|reasoning_logs|trading_days|holdings|actions)"
```

Expected:
- trading_days, holdings, actions tables exist
- trading_sessions, positions, reasoning_logs tables DO NOT exist

**Step 4: Test API endpoints**

```bash
# Start server
uvicorn api.main:app --reload

# In another terminal:
# Trigger simulation
curl -X POST http://localhost:8080/simulate/trigger \
  -H "Content-Type: application/json" \
  -d '{"end_date": "2025-01-15"}'

# Check results (should work)
curl http://localhost:8080/results?reasoning=summary

# Check old endpoint (should 404)
curl http://localhost:8080/reasoning
```

Expected:
- `/results` returns 200 with data
- `/reasoning` returns 404

**Step 5: Final commit**

```bash
git add -A
git commit -m "chore: verify schema migration complete"
```

---

## Summary

**Phase 1: Complete Migration**
- ✅ Task 1: Trade tools write to actions table
- ✅ Task 2: Remove old schema writes from model_day_executor
- ✅ Task 3: Update get_current_position_from_db to query new schema

**Phase 2: Remove Old Schema**
- ✅ Task 4: Remove /reasoning endpoint
- ✅ Task 5: Drop old database tables
- ✅ Task 6: Remove old-schema tests
- ✅ Task 7: Update CHANGELOG with breaking changes
- ✅ Task 8: Final verification

**Total Commits:** 8

**Estimated Time:** 3-4 hours for full implementation and testing

---

## Post-Implementation

After completing this plan:

1. **Run full regression tests** - `bash scripts/run_tests.sh`
2. **Test in DEV mode** - Verify simulations work end-to-end
3. **Review API documentation** - Ensure all references updated
4. **Deploy to production** - Fresh database will use new schema only

**Database Migration Note:** This is a **breaking change**. Old data in production cannot be automatically migrated because the data models are fundamentally different (action-centric vs day-centric). If preserving old data is required, export it before deploying this change.
