# Daily P&L and Results API Refactor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Refactor database schema and API to provide day-centric trading results with accurate daily P&L calculations and consolidated reasoning endpoints.

**Architecture:** Replace action-centric `positions` table with normalized schema: `trading_days` as parent table containing daily metrics, `holdings` for portfolio snapshots, and `actions` for trade ledger. Calculate daily P&L at start of each trading day by valuing previous day's holdings at current prices. Generate AI reasoning summaries during simulation, store in database for API retrieval.

**Tech Stack:** Python 3.10+, SQLite, FastAPI, pytest, LangChain

---

## Task 1: Database Schema Migration

**Files:**
- Create: `api/migrations/001_trading_days_schema.py`
- Create: `tests/unit/test_trading_days_schema.py`
- Modify: `api/database.py`

**Step 1: Write failing test for trading_days table creation**

Create `tests/unit/test_trading_days_schema.py`:

```python
import pytest
import sqlite3
from api.database import Database
from api.migrations.001_trading_days_schema import create_trading_days_schema


class TestTradingDaysSchema:

    @pytest.fixture
    def db(self, tmp_path):
        """Create temporary test database."""
        db_path = tmp_path / "test.db"
        db = Database(str(db_path))
        return db

    def test_create_trading_days_table(self, db):
        """Test trading_days table is created with correct schema."""
        create_trading_days_schema(db)

        # Query schema
        cursor = db.connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='trading_days'"
        )
        schema = cursor.fetchone()[0]

        # Verify required columns
        assert "job_id TEXT NOT NULL" in schema
        assert "model TEXT NOT NULL" in schema
        assert "date TEXT NOT NULL" in schema
        assert "starting_cash REAL NOT NULL" in schema
        assert "starting_portfolio_value REAL NOT NULL" in schema
        assert "daily_profit REAL NOT NULL" in schema
        assert "daily_return_pct REAL NOT NULL" in schema
        assert "ending_cash REAL NOT NULL" in schema
        assert "ending_portfolio_value REAL NOT NULL" in schema
        assert "reasoning_summary TEXT" in schema
        assert "reasoning_full TEXT" in schema
        assert "UNIQUE(job_id, model, date)" in schema

    def test_create_holdings_table(self, db):
        """Test holdings table is created with correct schema."""
        create_trading_days_schema(db)

        cursor = db.connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='holdings'"
        )
        schema = cursor.fetchone()[0]

        assert "trading_day_id INTEGER NOT NULL" in schema
        assert "symbol TEXT NOT NULL" in schema
        assert "quantity INTEGER NOT NULL" in schema
        assert "FOREIGN KEY (trading_day_id) REFERENCES trading_days(id)" in schema
        assert "UNIQUE(trading_day_id, symbol)" in schema

    def test_create_actions_table(self, db):
        """Test actions table is created with correct schema."""
        create_trading_days_schema(db)

        cursor = db.connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='actions'"
        )
        schema = cursor.fetchone()[0]

        assert "trading_day_id INTEGER NOT NULL" in schema
        assert "action_type TEXT NOT NULL" in schema
        assert "symbol TEXT" in schema
        assert "quantity INTEGER" in schema
        assert "price REAL" in schema
        assert "FOREIGN KEY (trading_day_id) REFERENCES trading_days(id)" in schema
```

**Step 2: Run test to verify it fails**

Run: `./venv/bin/python -m pytest tests/unit/test_trading_days_schema.py -v`

Expected: FAIL with "ModuleNotFoundError: No module named 'api.migrations'"

**Step 3: Create migration module structure**

Create `api/migrations/__init__.py`:

```python
"""Database schema migrations."""
```

Create `api/migrations/001_trading_days_schema.py`:

```python
"""Migration: Create trading_days, holdings, and actions tables."""

import sqlite3
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from api.database import Database


def create_trading_days_schema(db: "Database") -> None:
    """Create new schema for day-centric trading results.

    Args:
        db: Database instance to apply migration to
    """

    # Create trading_days table
    db.connection.execute("""
        CREATE TABLE IF NOT EXISTS trading_days (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            model TEXT NOT NULL,
            date TEXT NOT NULL,

            -- Starting position (cash only, holdings from previous day)
            starting_cash REAL NOT NULL,
            starting_portfolio_value REAL NOT NULL,

            -- Daily performance metrics
            daily_profit REAL NOT NULL,
            daily_return_pct REAL NOT NULL,

            -- Ending state (cash only, holdings in separate table)
            ending_cash REAL NOT NULL,
            ending_portfolio_value REAL NOT NULL,

            -- Reasoning
            reasoning_summary TEXT,
            reasoning_full TEXT,

            -- Metadata
            total_actions INTEGER DEFAULT 0,
            session_duration_seconds REAL,
            days_since_last_trading INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,

            UNIQUE(job_id, model, date),
            FOREIGN KEY (job_id) REFERENCES jobs(job_id)
        )
    """)

    # Create index for lookups
    db.connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_trading_days_lookup
        ON trading_days(job_id, model, date)
    """)

    # Create holdings table (ending positions only)
    db.connection.execute("""
        CREATE TABLE IF NOT EXISTS holdings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trading_day_id INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            quantity INTEGER NOT NULL,

            FOREIGN KEY (trading_day_id) REFERENCES trading_days(id) ON DELETE CASCADE,
            UNIQUE(trading_day_id, symbol)
        )
    """)

    # Create index for holdings lookups
    db.connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_holdings_day
        ON holdings(trading_day_id)
    """)

    # Create actions table (trade ledger)
    db.connection.execute("""
        CREATE TABLE IF NOT EXISTS actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trading_day_id INTEGER NOT NULL,

            action_type TEXT NOT NULL,
            symbol TEXT,
            quantity INTEGER,
            price REAL,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (trading_day_id) REFERENCES trading_days(id) ON DELETE CASCADE
        )
    """)

    # Create index for actions lookups
    db.connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_actions_day
        ON actions(trading_day_id)
    """)

    db.connection.commit()


def drop_old_positions_table(db: "Database") -> None:
    """Drop deprecated positions table after migration complete.

    Args:
        db: Database instance
    """
    db.connection.execute("DROP TABLE IF EXISTS positions")
    db.connection.commit()
```

**Step 4: Run test to verify it passes**

Run: `./venv/bin/python -m pytest tests/unit/test_trading_days_schema.py -v`

Expected: PASS (all 3 tests)

**Step 5: Commit**

```bash
git add api/migrations/ tests/unit/test_trading_days_schema.py
git commit -m "feat: add trading_days schema migration"
```

---

## Task 2: Database Helper Methods

**Files:**
- Modify: `api/database.py`
- Create: `tests/unit/test_database_helpers.py`

**Step 1: Write failing tests for database helper methods**

Create `tests/unit/test_database_helpers.py`:

```python
import pytest
from datetime import datetime
from api.database import Database


class TestDatabaseHelpers:

    @pytest.fixture
    def db(self, tmp_path):
        """Create test database with schema."""
        from api.migrations.001_trading_days_schema import create_trading_days_schema

        db_path = tmp_path / "test.db"
        db = Database(str(db_path))

        # Create jobs table (prerequisite)
        db.connection.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                status TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        create_trading_days_schema(db)
        return db

    def test_create_trading_day(self, db):
        """Test creating a new trading day record."""
        # Insert job first
        db.connection.execute(
            "INSERT INTO jobs (job_id, status) VALUES (?, ?)",
            ("test-job", "running")
        )

        trading_day_id = db.create_trading_day(
            job_id="test-job",
            model="gpt-4",
            date="2025-01-15",
            starting_cash=10000.0,
            starting_portfolio_value=10000.0,
            daily_profit=0.0,
            daily_return_pct=0.0,
            ending_cash=9500.0,
            ending_portfolio_value=9500.0
        )

        assert trading_day_id is not None

        # Verify record created
        cursor = db.connection.execute(
            "SELECT * FROM trading_days WHERE id = ?",
            (trading_day_id,)
        )
        row = cursor.fetchone()
        assert row is not None

    def test_get_previous_trading_day(self, db):
        """Test retrieving previous trading day."""
        # Setup: Create job and two trading days
        db.connection.execute(
            "INSERT INTO jobs (job_id, status) VALUES (?, ?)",
            ("test-job", "running")
        )

        day1_id = db.create_trading_day(
            job_id="test-job",
            model="gpt-4",
            date="2025-01-15",
            starting_cash=10000.0,
            starting_portfolio_value=10000.0,
            daily_profit=0.0,
            daily_return_pct=0.0,
            ending_cash=9500.0,
            ending_portfolio_value=9500.0
        )

        day2_id = db.create_trading_day(
            job_id="test-job",
            model="gpt-4",
            date="2025-01-16",
            starting_cash=9500.0,
            starting_portfolio_value=9500.0,
            daily_profit=-500.0,
            daily_return_pct=-5.0,
            ending_cash=9700.0,
            ending_portfolio_value=9700.0
        )

        # Test: Get previous day from day2
        previous = db.get_previous_trading_day(
            job_id="test-job",
            model="gpt-4",
            current_date="2025-01-16"
        )

        assert previous is not None
        assert previous["date"] == "2025-01-15"
        assert previous["ending_cash"] == 9500.0

    def test_get_previous_trading_day_with_weekend_gap(self, db):
        """Test retrieving previous trading day across weekend."""
        db.connection.execute(
            "INSERT INTO jobs (job_id, status) VALUES (?, ?)",
            ("test-job", "running")
        )

        # Friday
        db.create_trading_day(
            job_id="test-job",
            model="gpt-4",
            date="2025-01-17",  # Friday
            starting_cash=10000.0,
            starting_portfolio_value=10000.0,
            daily_profit=0.0,
            daily_return_pct=0.0,
            ending_cash=9500.0,
            ending_portfolio_value=9500.0
        )

        # Test: Get previous from Monday (should find Friday)
        previous = db.get_previous_trading_day(
            job_id="test-job",
            model="gpt-4",
            current_date="2025-01-20"  # Monday
        )

        assert previous is not None
        assert previous["date"] == "2025-01-17"

    def test_get_ending_holdings(self, db):
        """Test retrieving ending holdings for a trading day."""
        db.connection.execute(
            "INSERT INTO jobs (job_id, status) VALUES (?, ?)",
            ("test-job", "running")
        )

        trading_day_id = db.create_trading_day(
            job_id="test-job",
            model="gpt-4",
            date="2025-01-15",
            starting_cash=10000.0,
            starting_portfolio_value=10000.0,
            daily_profit=0.0,
            daily_return_pct=0.0,
            ending_cash=9000.0,
            ending_portfolio_value=10000.0
        )

        # Add holdings
        db.create_holding(trading_day_id, "AAPL", 10)
        db.create_holding(trading_day_id, "MSFT", 5)

        # Test
        holdings = db.get_ending_holdings(trading_day_id)

        assert len(holdings) == 2
        assert {"symbol": "AAPL", "quantity": 10} in holdings
        assert {"symbol": "MSFT", "quantity": 5} in holdings

    def test_get_starting_holdings_first_day(self, db):
        """Test starting holdings for first trading day (should be empty)."""
        db.connection.execute(
            "INSERT INTO jobs (job_id, status) VALUES (?, ?)",
            ("test-job", "running")
        )

        trading_day_id = db.create_trading_day(
            job_id="test-job",
            model="gpt-4",
            date="2025-01-15",
            starting_cash=10000.0,
            starting_portfolio_value=10000.0,
            daily_profit=0.0,
            daily_return_pct=0.0,
            ending_cash=9500.0,
            ending_portfolio_value=9500.0
        )

        holdings = db.get_starting_holdings(trading_day_id)

        assert holdings == []

    def test_get_starting_holdings_from_previous_day(self, db):
        """Test starting holdings derived from previous day's ending."""
        db.connection.execute(
            "INSERT INTO jobs (job_id, status) VALUES (?, ?)",
            ("test-job", "running")
        )

        # Day 1
        day1_id = db.create_trading_day(
            job_id="test-job",
            model="gpt-4",
            date="2025-01-15",
            starting_cash=10000.0,
            starting_portfolio_value=10000.0,
            daily_profit=0.0,
            daily_return_pct=0.0,
            ending_cash=9000.0,
            ending_portfolio_value=10000.0
        )
        db.create_holding(day1_id, "AAPL", 10)

        # Day 2
        day2_id = db.create_trading_day(
            job_id="test-job",
            model="gpt-4",
            date="2025-01-16",
            starting_cash=9000.0,
            starting_portfolio_value=10000.0,
            daily_profit=0.0,
            daily_return_pct=0.0,
            ending_cash=8500.0,
            ending_portfolio_value=9500.0
        )

        # Test: Day 2 starting = Day 1 ending
        holdings = db.get_starting_holdings(day2_id)

        assert len(holdings) == 1
        assert holdings[0]["symbol"] == "AAPL"
        assert holdings[0]["quantity"] == 10

    def test_create_action(self, db):
        """Test creating an action record."""
        db.connection.execute(
            "INSERT INTO jobs (job_id, status) VALUES (?, ?)",
            ("test-job", "running")
        )

        trading_day_id = db.create_trading_day(
            job_id="test-job",
            model="gpt-4",
            date="2025-01-15",
            starting_cash=10000.0,
            starting_portfolio_value=10000.0,
            daily_profit=0.0,
            daily_return_pct=0.0,
            ending_cash=9500.0,
            ending_portfolio_value=9500.0
        )

        action_id = db.create_action(
            trading_day_id=trading_day_id,
            action_type="buy",
            symbol="AAPL",
            quantity=10,
            price=100.0
        )

        assert action_id is not None

        # Verify
        cursor = db.connection.execute(
            "SELECT * FROM actions WHERE id = ?",
            (action_id,)
        )
        row = cursor.fetchone()
        assert row is not None

    def test_get_actions(self, db):
        """Test retrieving all actions for a trading day."""
        db.connection.execute(
            "INSERT INTO jobs (job_id, status) VALUES (?, ?)",
            ("test-job", "running")
        )

        trading_day_id = db.create_trading_day(
            job_id="test-job",
            model="gpt-4",
            date="2025-01-15",
            starting_cash=10000.0,
            starting_portfolio_value=10000.0,
            daily_profit=0.0,
            daily_return_pct=0.0,
            ending_cash=9500.0,
            ending_portfolio_value=9500.0
        )

        db.create_action(trading_day_id, "buy", "AAPL", 10, 100.0)
        db.create_action(trading_day_id, "sell", "MSFT", 5, 50.0)

        actions = db.get_actions(trading_day_id)

        assert len(actions) == 2
```

**Step 2: Run test to verify it fails**

Run: `./venv/bin/python -m pytest tests/unit/test_database_helpers.py -v`

Expected: FAIL with "AttributeError: 'Database' object has no attribute 'create_trading_day'"

**Step 3: Implement database helper methods**

Modify `api/database.py` - add these methods to the Database class:

```python
def create_trading_day(
    self,
    job_id: str,
    model: str,
    date: str,
    starting_cash: float,
    starting_portfolio_value: float,
    daily_profit: float,
    daily_return_pct: float,
    ending_cash: float,
    ending_portfolio_value: float,
    reasoning_summary: str = None,
    reasoning_full: str = None,
    total_actions: int = 0,
    session_duration_seconds: float = None,
    days_since_last_trading: int = 1
) -> int:
    """Create a new trading day record.

    Returns:
        trading_day_id
    """
    cursor = self.connection.execute(
        """
        INSERT INTO trading_days (
            job_id, model, date,
            starting_cash, starting_portfolio_value,
            daily_profit, daily_return_pct,
            ending_cash, ending_portfolio_value,
            reasoning_summary, reasoning_full,
            total_actions, session_duration_seconds,
            days_since_last_trading,
            completed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (
            job_id, model, date,
            starting_cash, starting_portfolio_value,
            daily_profit, daily_return_pct,
            ending_cash, ending_portfolio_value,
            reasoning_summary, reasoning_full,
            total_actions, session_duration_seconds,
            days_since_last_trading
        )
    )
    self.connection.commit()
    return cursor.lastrowid


def get_previous_trading_day(
    self,
    job_id: str,
    model: str,
    current_date: str
) -> dict:
    """Get the most recent trading day before current_date.

    Handles weekends/holidays by finding actual previous trading day.

    Returns:
        dict with keys: id, date, ending_cash, ending_portfolio_value
        or None if no previous day exists
    """
    cursor = self.connection.execute(
        """
        SELECT id, date, ending_cash, ending_portfolio_value
        FROM trading_days
        WHERE job_id = ? AND model = ? AND date < ?
        ORDER BY date DESC
        LIMIT 1
        """,
        (job_id, model, current_date)
    )

    row = cursor.fetchone()
    if row:
        return {
            "id": row[0],
            "date": row[1],
            "ending_cash": row[2],
            "ending_portfolio_value": row[3]
        }
    return None


def get_ending_holdings(self, trading_day_id: int) -> list:
    """Get ending holdings for a trading day.

    Returns:
        List of dicts with keys: symbol, quantity
    """
    cursor = self.connection.execute(
        """
        SELECT symbol, quantity
        FROM holdings
        WHERE trading_day_id = ?
        ORDER BY symbol
        """,
        (trading_day_id,)
    )

    return [{"symbol": row[0], "quantity": row[1]} for row in cursor.fetchall()]


def get_starting_holdings(self, trading_day_id: int) -> list:
    """Get starting holdings from previous day's ending holdings.

    Returns:
        List of dicts with keys: symbol, quantity
        Empty list if first trading day
    """
    # Get previous trading day
    cursor = self.connection.execute(
        """
        SELECT td_prev.id
        FROM trading_days td_current
        JOIN trading_days td_prev ON
            td_prev.job_id = td_current.job_id AND
            td_prev.model = td_current.model AND
            td_prev.date < td_current.date
        WHERE td_current.id = ?
        ORDER BY td_prev.date DESC
        LIMIT 1
        """,
        (trading_day_id,)
    )

    row = cursor.fetchone()
    if not row:
        # First trading day - no previous holdings
        return []

    previous_day_id = row[0]

    # Get previous day's ending holdings
    return self.get_ending_holdings(previous_day_id)


def create_holding(
    self,
    trading_day_id: int,
    symbol: str,
    quantity: int
) -> int:
    """Create a holding record.

    Returns:
        holding_id
    """
    cursor = self.connection.execute(
        """
        INSERT INTO holdings (trading_day_id, symbol, quantity)
        VALUES (?, ?, ?)
        """,
        (trading_day_id, symbol, quantity)
    )
    self.connection.commit()
    return cursor.lastrowid


def create_action(
    self,
    trading_day_id: int,
    action_type: str,
    symbol: str = None,
    quantity: int = None,
    price: float = None
) -> int:
    """Create an action record.

    Returns:
        action_id
    """
    cursor = self.connection.execute(
        """
        INSERT INTO actions (trading_day_id, action_type, symbol, quantity, price)
        VALUES (?, ?, ?, ?, ?)
        """,
        (trading_day_id, action_type, symbol, quantity, price)
    )
    self.connection.commit()
    return cursor.lastrowid


def get_actions(self, trading_day_id: int) -> list:
    """Get all actions for a trading day.

    Returns:
        List of dicts with keys: action_type, symbol, quantity, price, created_at
    """
    cursor = self.connection.execute(
        """
        SELECT action_type, symbol, quantity, price, created_at
        FROM actions
        WHERE trading_day_id = ?
        ORDER BY created_at
        """,
        (trading_day_id,)
    )

    return [
        {
            "action_type": row[0],
            "symbol": row[1],
            "quantity": row[2],
            "price": row[3],
            "created_at": row[4]
        }
        for row in cursor.fetchall()
    ]
```

**Step 4: Run test to verify it passes**

Run: `./venv/bin/python -m pytest tests/unit/test_database_helpers.py -v`

Expected: PASS (all tests)

**Step 5: Commit**

```bash
git add api/database.py tests/unit/test_database_helpers.py
git commit -m "feat: add database helper methods for trading_days schema"
```

---

## Task 3: Daily P&L Calculation Logic

**Files:**
- Create: `agent/pnl_calculator.py`
- Create: `tests/unit/test_pnl_calculator.py`

**Step 1: Write failing tests for P&L calculator**

Create `tests/unit/test_pnl_calculator.py`:

```python
import pytest
from agent.pnl_calculator import DailyPnLCalculator


class TestDailyPnLCalculator:

    def test_first_day_zero_pnl(self):
        """First trading day should have zero P&L."""
        calculator = DailyPnLCalculator(initial_cash=10000.0)

        result = calculator.calculate(
            previous_day=None,
            current_date="2025-01-15",
            current_prices={"AAPL": 150.0}
        )

        assert result["daily_profit"] == 0.0
        assert result["daily_return_pct"] == 0.0
        assert result["starting_portfolio_value"] == 10000.0
        assert result["days_since_last_trading"] == 0

    def test_positive_pnl_from_price_increase(self):
        """Portfolio gains value when holdings appreciate."""
        calculator = DailyPnLCalculator(initial_cash=10000.0)

        # Previous day: 10 shares of AAPL at $100, cash $9000
        previous_day = {
            "date": "2025-01-15",
            "ending_cash": 9000.0,
            "ending_portfolio_value": 10000.0,  # 10 * $100 + $9000
            "holdings": [{"symbol": "AAPL", "quantity": 10}]
        }

        # Current day: AAPL now $150
        current_prices = {"AAPL": 150.0}

        result = calculator.calculate(
            previous_day=previous_day,
            current_date="2025-01-16",
            current_prices=current_prices
        )

        # New value: 10 * $150 + $9000 = $10,500
        # Profit: $10,500 - $10,000 = $500
        assert result["daily_profit"] == 500.0
        assert result["daily_return_pct"] == 5.0
        assert result["starting_portfolio_value"] == 10500.0
        assert result["days_since_last_trading"] == 1

    def test_negative_pnl_from_price_decrease(self):
        """Portfolio loses value when holdings depreciate."""
        calculator = DailyPnLCalculator(initial_cash=10000.0)

        previous_day = {
            "date": "2025-01-15",
            "ending_cash": 9000.0,
            "ending_portfolio_value": 10000.0,
            "holdings": [{"symbol": "AAPL", "quantity": 10}]
        }

        # AAPL drops from $100 to $80
        current_prices = {"AAPL": 80.0}

        result = calculator.calculate(
            previous_day=previous_day,
            current_date="2025-01-16",
            current_prices=current_prices
        )

        # New value: 10 * $80 + $9000 = $9,800
        # Loss: $9,800 - $10,000 = -$200
        assert result["daily_profit"] == -200.0
        assert result["daily_return_pct"] == -2.0

    def test_weekend_gap_calculation(self):
        """Calculate P&L correctly across weekend."""
        calculator = DailyPnLCalculator(initial_cash=10000.0)

        # Friday
        previous_day = {
            "date": "2025-01-17",  # Friday
            "ending_cash": 9000.0,
            "ending_portfolio_value": 10000.0,
            "holdings": [{"symbol": "AAPL", "quantity": 10}]
        }

        # Monday (3 days later)
        current_prices = {"AAPL": 120.0}

        result = calculator.calculate(
            previous_day=previous_day,
            current_date="2025-01-20",  # Monday
            current_prices=current_prices
        )

        # New value: 10 * $120 + $9000 = $10,200
        assert result["daily_profit"] == 200.0
        assert result["days_since_last_trading"] == 3

    def test_multiple_holdings(self):
        """Calculate P&L with multiple stock positions."""
        calculator = DailyPnLCalculator(initial_cash=10000.0)

        previous_day = {
            "date": "2025-01-15",
            "ending_cash": 8000.0,
            "ending_portfolio_value": 10000.0,
            "holdings": [
                {"symbol": "AAPL", "quantity": 10},  # Was $100
                {"symbol": "MSFT", "quantity": 5}    # Was $200
            ]
        }

        # Prices change
        current_prices = {
            "AAPL": 110.0,  # +$10
            "MSFT": 190.0   # -$10
        }

        result = calculator.calculate(
            previous_day=previous_day,
            current_date="2025-01-16",
            current_prices=current_prices
        )

        # AAPL: 10 * $110 = $1,100 (was $1,000, +$100)
        # MSFT: 5 * $190 = $950 (was $1,000, -$50)
        # Cash: $8,000 (unchanged)
        # New total: $10,050
        # Profit: $50
        assert result["daily_profit"] == 50.0

    def test_missing_price_raises_error(self):
        """Raise error if price data missing for holding."""
        calculator = DailyPnLCalculator(initial_cash=10000.0)

        previous_day = {
            "date": "2025-01-15",
            "ending_cash": 9000.0,
            "ending_portfolio_value": 10000.0,
            "holdings": [{"symbol": "AAPL", "quantity": 10}]
        }

        # Missing AAPL price
        current_prices = {"MSFT": 150.0}

        with pytest.raises(ValueError, match="Missing price data for AAPL"):
            calculator.calculate(
                previous_day=previous_day,
                current_date="2025-01-16",
                current_prices=current_prices
            )
```

**Step 2: Run test to verify it fails**

Run: `./venv/bin/python -m pytest tests/unit/test_pnl_calculator.py -v`

Expected: FAIL with "ModuleNotFoundError: No module named 'agent.pnl_calculator'"

**Step 3: Implement P&L calculator**

Create `agent/pnl_calculator.py`:

```python
"""Daily P&L calculation logic."""

from datetime import datetime
from typing import Optional, Dict, List


class DailyPnLCalculator:
    """Calculate daily profit/loss for trading portfolios."""

    def __init__(self, initial_cash: float):
        """Initialize calculator.

        Args:
            initial_cash: Starting cash amount for first day
        """
        self.initial_cash = initial_cash

    def calculate(
        self,
        previous_day: Optional[Dict],
        current_date: str,
        current_prices: Dict[str, float]
    ) -> Dict:
        """Calculate daily P&L by valuing holdings at current prices.

        Args:
            previous_day: Previous trading day data with keys:
                - date: str
                - ending_cash: float
                - ending_portfolio_value: float
                - holdings: List[Dict] with symbol and quantity
                None if first trading day
            current_date: Current trading date (YYYY-MM-DD)
            current_prices: Dict mapping symbol to current price

        Returns:
            Dict with keys:
                - daily_profit: float
                - daily_return_pct: float
                - starting_portfolio_value: float
                - days_since_last_trading: int

        Raises:
            ValueError: If price data missing for a holding
        """
        if previous_day is None:
            # First trading day - no P&L
            return {
                "daily_profit": 0.0,
                "daily_return_pct": 0.0,
                "starting_portfolio_value": self.initial_cash,
                "days_since_last_trading": 0
            }

        # Calculate days since last trading
        days_gap = self._calculate_day_gap(
            previous_day["date"],
            current_date
        )

        # Value previous holdings at current prices
        current_value = self._calculate_portfolio_value(
            holdings=previous_day["holdings"],
            prices=current_prices,
            cash=previous_day["ending_cash"]
        )

        # Calculate P&L
        previous_value = previous_day["ending_portfolio_value"]
        daily_profit = current_value - previous_value
        daily_return_pct = (daily_profit / previous_value * 100) if previous_value > 0 else 0.0

        return {
            "daily_profit": daily_profit,
            "daily_return_pct": daily_return_pct,
            "starting_portfolio_value": current_value,
            "days_since_last_trading": days_gap
        }

    def _calculate_portfolio_value(
        self,
        holdings: List[Dict],
        prices: Dict[str, float],
        cash: float
    ) -> float:
        """Calculate total portfolio value.

        Args:
            holdings: List of dicts with symbol and quantity
            prices: Dict mapping symbol to price
            cash: Cash balance

        Returns:
            Total portfolio value

        Raises:
            ValueError: If price missing for a holding
        """
        total_value = cash

        for holding in holdings:
            symbol = holding["symbol"]
            quantity = holding["quantity"]

            if symbol not in prices:
                raise ValueError(f"Missing price data for {symbol}")

            total_value += quantity * prices[symbol]

        return total_value

    def _calculate_day_gap(self, date1: str, date2: str) -> int:
        """Calculate number of days between two dates.

        Args:
            date1: Earlier date (YYYY-MM-DD)
            date2: Later date (YYYY-MM-DD)

        Returns:
            Number of days between dates
        """
        d1 = datetime.strptime(date1, "%Y-%m-%d")
        d2 = datetime.strptime(date2, "%Y-%m-%d")
        return (d2 - d1).days
```

**Step 4: Run test to verify it passes**

Run: `./venv/bin/python -m pytest tests/unit/test_pnl_calculator.py -v`

Expected: PASS (all tests)

**Step 5: Commit**

```bash
git add agent/pnl_calculator.py tests/unit/test_pnl_calculator.py
git commit -m "feat: add daily P&L calculator with weekend gap handling"
```

---

## Task 4: Reasoning Summary Generation

**Files:**
- Create: `agent/reasoning_summarizer.py`
- Create: `tests/unit/test_reasoning_summarizer.py`

**Step 1: Write failing tests for reasoning summarizer**

Create `tests/unit/test_reasoning_summarizer.py`:

```python
import pytest
from unittest.mock import AsyncMock, Mock
from agent.reasoning_summarizer import ReasoningSummarizer


class TestReasoningSummarizer:

    @pytest.mark.asyncio
    async def test_generate_summary_success(self):
        """Test successful AI summary generation."""
        # Mock AI model
        mock_model = AsyncMock()
        mock_model.ainvoke.return_value = Mock(
            content="Analyzed AAPL earnings. Bought 10 shares based on positive guidance."
        )

        summarizer = ReasoningSummarizer(model=mock_model)

        reasoning_log = [
            {"role": "user", "content": "Analyze market"},
            {"role": "assistant", "content": "Let me check AAPL"},
            {"role": "tool", "name": "search", "content": "AAPL earnings positive"}
        ]

        summary = await summarizer.generate_summary(reasoning_log)

        assert summary == "Analyzed AAPL earnings. Bought 10 shares based on positive guidance."
        mock_model.ainvoke.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_summary_failure_fallback(self):
        """Test fallback summary when AI generation fails."""
        # Mock AI model that raises exception
        mock_model = AsyncMock()
        mock_model.ainvoke.side_effect = Exception("API error")

        summarizer = ReasoningSummarizer(model=mock_model)

        reasoning_log = [
            {"role": "assistant", "content": "Let me search"},
            {"role": "tool", "name": "search", "content": "Results"},
            {"role": "tool", "name": "trade", "content": "Buy AAPL"},
            {"role": "tool", "name": "trade", "content": "Sell MSFT"}
        ]

        summary = await summarizer.generate_summary(reasoning_log)

        # Should return fallback with stats
        assert "2 trades" in summary
        assert "1 market searches" in summary

    @pytest.mark.asyncio
    async def test_format_reasoning_for_summary(self):
        """Test condensing reasoning log for summary prompt."""
        mock_model = AsyncMock()
        summarizer = ReasoningSummarizer(model=mock_model)

        reasoning_log = [
            {"role": "user", "content": "System prompt here"},
            {"role": "assistant", "content": "I will analyze AAPL"},
            {"role": "tool", "name": "search", "content": "AAPL earnings data..."},
            {"role": "assistant", "content": "Based on analysis, buying AAPL"}
        ]

        formatted = summarizer._format_reasoning_for_summary(reasoning_log)

        # Should include key messages
        assert "analyze AAPL" in formatted
        assert "search" in formatted
        assert "buying AAPL" in formatted

    @pytest.mark.asyncio
    async def test_empty_reasoning_log(self):
        """Test handling empty reasoning log."""
        mock_model = AsyncMock()
        summarizer = ReasoningSummarizer(model=mock_model)

        summary = await summarizer.generate_summary([])

        assert summary == "No trading activity recorded."
```

**Step 2: Run test to verify it fails**

Run: `./venv/bin/python -m pytest tests/unit/test_reasoning_summarizer.py -v`

Expected: FAIL with "ModuleNotFoundError: No module named 'agent.reasoning_summarizer'"

**Step 3: Implement reasoning summarizer**

Create `agent/reasoning_summarizer.py`:

```python
"""AI reasoning summary generation."""

import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class ReasoningSummarizer:
    """Generate summaries of AI trading session reasoning."""

    def __init__(self, model: Any):
        """Initialize summarizer.

        Args:
            model: LangChain chat model for generating summaries
        """
        self.model = model

    async def generate_summary(self, reasoning_log: List[Dict]) -> str:
        """Generate AI summary of trading session reasoning.

        Args:
            reasoning_log: List of message dicts with role and content

        Returns:
            Summary string (2-3 sentences)
        """
        if not reasoning_log:
            return "No trading activity recorded."

        try:
            # Build condensed version of reasoning log
            log_text = self._format_reasoning_for_summary(reasoning_log)

            summary_prompt = f"""You are reviewing your own trading decisions for the day.
Summarize your trading strategy and key decisions in 2-3 sentences.

Focus on:
- What you analyzed
- Why you made the trades you did
- Your overall strategy for the day

Trading session log:
{log_text}

Provide a concise summary:"""

            response = await self.model.ainvoke([
                {"role": "user", "content": summary_prompt}
            ])

            # Extract content from response
            if hasattr(response, 'content'):
                return response.content
            else:
                return str(response)

        except Exception as e:
            logger.error(f"Failed to generate AI reasoning summary: {e}")
            return self._generate_fallback_summary(reasoning_log)

    def _format_reasoning_for_summary(self, reasoning_log: List[Dict]) -> str:
        """Format reasoning log into concise text for summary prompt.

        Args:
            reasoning_log: List of message dicts

        Returns:
            Formatted text representation
        """
        formatted_parts = []

        for msg in reasoning_log:
            role = msg.get("role", "")
            content = msg.get("content", "")

            if role == "assistant":
                # AI's thoughts
                formatted_parts.append(f"AI: {content[:200]}")
            elif role == "tool":
                # Tool results
                tool_name = msg.get("name", "tool")
                formatted_parts.append(f"{tool_name}: {content[:100]}")

        return "\n".join(formatted_parts)

    def _generate_fallback_summary(self, reasoning_log: List[Dict]) -> str:
        """Generate simple statistical summary without AI.

        Args:
            reasoning_log: List of message dicts

        Returns:
            Fallback summary string
        """
        trade_count = sum(
            1 for msg in reasoning_log
            if msg.get("role") == "tool" and msg.get("name") == "trade"
        )

        search_count = sum(
            1 for msg in reasoning_log
            if msg.get("role") == "tool" and msg.get("name") == "search"
        )

        return (
            f"Executed {trade_count} trades using {search_count} market searches. "
            f"Full reasoning log available."
        )
```

**Step 4: Run test to verify it passes**

Run: `./venv/bin/python -m pytest tests/unit/test_reasoning_summarizer.py -v`

Expected: PASS (all tests)

**Step 5: Commit**

```bash
git add agent/reasoning_summarizer.py tests/unit/test_reasoning_summarizer.py
git commit -m "feat: add AI reasoning summary generator with fallback"
```

---

## Task 5: Integrate P&L Calculation into BaseAgent

**Files:**
- Modify: `agent/base_agent/base_agent.py`
- Create: `tests/integration/test_agent_pnl_integration.py`

**Step 1: Write failing integration test**

Create `tests/integration/test_agent_pnl_integration.py`:

```python
import pytest
from unittest.mock import Mock, AsyncMock, patch
from agent.base_agent.base_agent import BaseAgent
from api.database import Database


class TestAgentPnLIntegration:

    @pytest.fixture
    def db(self, tmp_path):
        """Create test database."""
        from api.migrations.001_trading_days_schema import create_trading_days_schema

        db_path = tmp_path / "test.db"
        db = Database(str(db_path))

        # Create prerequisite tables
        db.connection.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                status TEXT
            )
        """)

        create_trading_days_schema(db)

        # Insert test job
        db.connection.execute(
            "INSERT INTO jobs (job_id, status) VALUES (?, ?)",
            ("test-job", "running")
        )
        db.connection.commit()

        return db

    @pytest.mark.asyncio
    @patch('agent.base_agent.base_agent.Database')
    async def test_first_day_creates_trading_day_with_zero_pnl(self, mock_db_class, db):
        """Test first trading day calculates zero P&L."""
        mock_db_class.return_value = db

        # Create agent
        agent = BaseAgent(
            job_id="test-job",
            signature="test-model",
            config={
                "agent_config": {
                    "initial_cash": 10000.0,
                    "max_steps": 5
                }
            }
        )

        # Mock price data
        with patch('tools.price_tools.get_prices_for_date') as mock_prices:
            mock_prices.return_value = {"AAPL": 150.0}

            # Mock AI model to finish immediately
            agent.ai_model = AsyncMock()
            agent.ai_model.ainvoke.return_value = Mock(
                content="<FINISH_SIGNAL>"
            )

            # Run first trading session
            await agent.run_trading_session("2025-01-15")

        # Verify trading_day created with zero P&L
        cursor = db.connection.execute(
            """
            SELECT daily_profit, daily_return_pct, starting_portfolio_value
            FROM trading_days
            WHERE job_id = ? AND model = ? AND date = ?
            """,
            ("test-job", "test-model", "2025-01-15")
        )

        row = cursor.fetchone()
        assert row is not None
        assert row[0] == 0.0  # daily_profit
        assert row[1] == 0.0  # daily_return_pct
        assert row[2] == 10000.0  # starting_portfolio_value

    @pytest.mark.asyncio
    @patch('agent.base_agent.base_agent.Database')
    async def test_second_day_calculates_pnl_from_price_changes(self, mock_db_class, db):
        """Test second trading day calculates P&L correctly."""
        mock_db_class.return_value = db

        # Setup: Create first trading day with holdings
        day1_id = db.create_trading_day(
            job_id="test-job",
            model="test-model",
            date="2025-01-15",
            starting_cash=10000.0,
            starting_portfolio_value=10000.0,
            daily_profit=0.0,
            daily_return_pct=0.0,
            ending_cash=8500.0,  # Spent $1500 on 10 shares
            ending_portfolio_value=10000.0  # 10 * $150 + $8500
        )
        db.create_holding(day1_id, "AAPL", 10)

        # Create agent
        agent = BaseAgent(
            job_id="test-job",
            signature="test-model",
            config={
                "agent_config": {
                    "initial_cash": 10000.0,
                    "max_steps": 5
                }
            }
        )

        # Set agent's current state to match day 1 ending
        agent.cash = 8500.0
        agent.holdings = {"AAPL": 10}

        # Mock price data - AAPL increased to $160
        with patch('tools.price_tools.get_prices_for_date') as mock_prices:
            mock_prices.return_value = {"AAPL": 160.0}

            # Mock AI model
            agent.ai_model = AsyncMock()
            agent.ai_model.ainvoke.return_value = Mock(
                content="<FINISH_SIGNAL>"
            )

            # Run second trading session
            await agent.run_trading_session("2025-01-16")

        # Verify P&L calculated correctly
        cursor = db.connection.execute(
            """
            SELECT daily_profit, daily_return_pct, starting_portfolio_value
            FROM trading_days
            WHERE job_id = ? AND model = ? AND date = ?
            """,
            ("test-job", "test-model", "2025-01-16")
        )

        row = cursor.fetchone()
        assert row is not None

        # Expected: 10 shares * ($160 - $150) = $100 profit
        # Portfolio went from $10,000 to $10,100
        assert abs(row[0] - 100.0) < 0.01  # daily_profit
        assert abs(row[1] - 1.0) < 0.01    # daily_return_pct (1%)
        assert abs(row[2] - 10100.0) < 0.01  # starting_portfolio_value
```

**Step 2: Run test to verify it fails**

Run: `./venv/bin/python -m pytest tests/integration/test_agent_pnl_integration.py -v`

Expected: FAIL (BaseAgent doesn't calculate P&L yet)

**Step 3: Modify BaseAgent to integrate P&L calculation**

Modify `agent/base_agent/base_agent.py` - add imports at top:

```python
from agent.pnl_calculator import DailyPnLCalculator
from agent.reasoning_summarizer import ReasoningSummarizer
import time
```

Modify `agent/base_agent/base_agent.py` - update `__init__` method:

```python
def __init__(self, job_id: str, signature: str, config: dict):
    # ... existing code ...

    # Add P&L calculator
    initial_cash = config.get("agent_config", {}).get("initial_cash", 10000.0)
    self.pnl_calculator = DailyPnLCalculator(initial_cash=initial_cash)
```

Modify `agent/base_agent/base_agent.py` - update `run_trading_session` method:

```python
async def run_trading_session(self, date: str):
    """Execute trading session for a single day with P&L calculation.

    Args:
        date: Trading date in YYYY-MM-DD format
    """
    from api.database import Database
    from tools.price_tools import get_prices_for_date

    db = Database()
    session_start = time.time()

    # 1. Get previous trading day data
    previous_day = db.get_previous_trading_day(
        job_id=self.job_id,
        model=self.signature,
        current_date=date
    )

    # 2. Load today's prices
    current_prices = get_prices_for_date(date)

    # 3. Calculate daily P&L
    pnl_metrics = self.pnl_calculator.calculate(
        previous_day=previous_day,
        current_date=date,
        current_prices=current_prices
    )

    # 4. Create trading_day record (will be updated after session)
    trading_day_id = db.create_trading_day(
        job_id=self.job_id,
        model=self.signature,
        date=date,
        starting_cash=self.cash,
        starting_portfolio_value=pnl_metrics["starting_portfolio_value"],
        daily_profit=pnl_metrics["daily_profit"],
        daily_return_pct=pnl_metrics["daily_return_pct"],
        ending_cash=self.cash,  # Will update after trading
        ending_portfolio_value=pnl_metrics["starting_portfolio_value"],  # Will update
        days_since_last_trading=pnl_metrics["days_since_last_trading"]
    )

    # 5. Run AI trading session
    reasoning_log = []
    action_count = 0

    for step in range(self.max_steps):
        # Get system prompt with current state
        messages = self._build_messages(date, current_prices)

        # Call AI model
        response = await self.ai_model.ainvoke(messages)
        reasoning_log.append(self._message_to_dict(response))

        # Extract and execute trades
        trades = self._extract_trades(response)
        for trade in trades:
            # Execute trade (updates self.cash and self.holdings)
            self._execute_trade(trade)

            # Record action
            db.create_action(
                trading_day_id=trading_day_id,
                action_type=trade["action_type"],
                symbol=trade.get("symbol"),
                quantity=trade.get("quantity"),
                price=trade.get("price")
            )
            action_count += 1

        # Check for finish signal
        if "<FINISH_SIGNAL>" in str(response):
            break

    session_duration = time.time() - session_start

    # 6. Generate reasoning summary
    summarizer = ReasoningSummarizer(model=self.ai_model)
    summary = await summarizer.generate_summary(reasoning_log)

    # 7. Save final holdings
    for symbol, quantity in self.holdings.items():
        if quantity > 0:
            db.create_holding(
                trading_day_id=trading_day_id,
                symbol=symbol,
                quantity=quantity
            )

    # 8. Calculate final portfolio value
    final_value = self._calculate_current_portfolio_value(current_prices)

    # 9. Update trading_day with completion data
    db.connection.execute(
        """
        UPDATE trading_days
        SET
            ending_cash = ?,
            ending_portfolio_value = ?,
            reasoning_summary = ?,
            reasoning_full = ?,
            total_actions = ?,
            session_duration_seconds = ?,
            completed_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (
            self.cash,
            final_value,
            summary,
            json.dumps(reasoning_log),
            action_count,
            session_duration,
            trading_day_id
        )
    )
    db.connection.commit()

def _message_to_dict(self, message) -> dict:
    """Convert LangChain message to dict for logging."""
    if hasattr(message, 'dict'):
        return message.dict()
    return {"content": str(message)}

def _calculate_current_portfolio_value(self, prices: dict) -> float:
    """Calculate current total portfolio value."""
    total = self.cash
    for symbol, quantity in self.holdings.items():
        if symbol in prices:
            total += quantity * prices[symbol]
    return total
```

**Step 4: Run test to verify it passes**

Run: `./venv/bin/python -m pytest tests/integration/test_agent_pnl_integration.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add agent/base_agent/base_agent.py tests/integration/test_agent_pnl_integration.py
git commit -m "feat: integrate P&L calculation and reasoning summary into BaseAgent"
```

---

## Task 6: New Results API Endpoint

**Files:**
- Create: `api/routes/results_v2.py`
- Create: `tests/integration/test_results_api_v2.py`

**Step 1: Write failing tests for new results API**

Create `tests/integration/test_results_api_v2.py`:

```python
import pytest
from fastapi.testclient import TestClient
from api.app import app
from api.database import Database


class TestResultsAPIV2:

    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)

    @pytest.fixture
    def db(self, tmp_path):
        """Create test database with sample data."""
        from api.migrations.001_trading_days_schema import create_trading_days_schema

        db_path = tmp_path / "test.db"
        db = Database(str(db_path))

        # Create schema
        db.connection.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                status TEXT
            )
        """)
        create_trading_days_schema(db)

        # Insert sample data
        db.connection.execute(
            "INSERT INTO jobs (job_id, status) VALUES (?, ?)",
            ("test-job", "completed")
        )

        # Day 1
        day1_id = db.create_trading_day(
            job_id="test-job",
            model="gpt-4",
            date="2025-01-15",
            starting_cash=10000.0,
            starting_portfolio_value=10000.0,
            daily_profit=0.0,
            daily_return_pct=0.0,
            ending_cash=8500.0,
            ending_portfolio_value=10000.0,
            reasoning_summary="First day summary",
            total_actions=1
        )
        db.create_holding(day1_id, "AAPL", 10)
        db.create_action(day1_id, "buy", "AAPL", 10, 150.0)

        db.connection.commit()
        return db

    def test_results_without_reasoning(self, client, db):
        """Test default response excludes reasoning."""
        response = client.get("/results?job_id=test-job")

        assert response.status_code == 200
        data = response.json()

        assert data["count"] == 1
        assert data["results"][0]["reasoning"] is None

    def test_results_with_summary(self, client, db):
        """Test including reasoning summary."""
        response = client.get("/results?job_id=test-job&reasoning=summary")

        data = response.json()
        result = data["results"][0]

        assert result["reasoning"] == "First day summary"

    def test_results_structure(self, client, db):
        """Test complete response structure."""
        response = client.get("/results?job_id=test-job")

        result = response.json()["results"][0]

        # Basic fields
        assert result["date"] == "2025-01-15"
        assert result["model"] == "gpt-4"
        assert result["job_id"] == "test-job"

        # Starting position
        assert "starting_position" in result
        assert result["starting_position"]["cash"] == 10000.0
        assert result["starting_position"]["portfolio_value"] == 10000.0
        assert result["starting_position"]["holdings"] == []  # First day

        # Daily metrics
        assert "daily_metrics" in result
        assert result["daily_metrics"]["profit"] == 0.0
        assert result["daily_metrics"]["return_pct"] == 0.0

        # Trades
        assert "trades" in result
        assert len(result["trades"]) == 1
        assert result["trades"][0]["action_type"] == "buy"
        assert result["trades"][0]["symbol"] == "AAPL"

        # Final position
        assert "final_position" in result
        assert result["final_position"]["cash"] == 8500.0
        assert result["final_position"]["portfolio_value"] == 10000.0
        assert len(result["final_position"]["holdings"]) == 1
        assert result["final_position"]["holdings"][0]["symbol"] == "AAPL"

        # Metadata
        assert "metadata" in result
        assert result["metadata"]["total_actions"] == 1

    def test_results_filtering_by_date(self, client, db):
        """Test filtering results by date."""
        response = client.get("/results?date=2025-01-15")

        results = response.json()["results"]
        assert all(r["date"] == "2025-01-15" for r in results)

    def test_results_filtering_by_model(self, client, db):
        """Test filtering results by model."""
        response = client.get("/results?model=gpt-4")

        results = response.json()["results"]
        assert all(r["model"] == "gpt-4" for r in results)
```

**Step 2: Run test to verify it fails**

Run: `./venv/bin/python -m pytest tests/integration/test_results_api_v2.py -v`

Expected: FAIL with 404 (endpoint doesn't exist yet)

**Step 3: Implement new results API endpoint**

Create `api/routes/results_v2.py`:

```python
"""New results API with day-centric structure."""

from fastapi import APIRouter, Query
from typing import Optional, Literal
import json

from api.database import Database

router = APIRouter()


@router.get("/results")
async def get_results(
    job_id: Optional[str] = None,
    model: Optional[str] = None,
    date: Optional[str] = None,
    reasoning: Literal["none", "summary", "full"] = "none"
):
    """Get trading results grouped by day.

    Args:
        job_id: Filter by simulation job ID
        model: Filter by model signature
        date: Filter by trading date (YYYY-MM-DD)
        reasoning: Include reasoning logs (none/summary/full)

    Returns:
        JSON with day-centric trading results and performance metrics
    """
    db = Database()

    # Build query with filters
    query = "SELECT * FROM trading_days WHERE 1=1"
    params = []

    if job_id:
        query += " AND job_id = ?"
        params.append(job_id)

    if model:
        query += " AND model = ?"
        params.append(model)

    if date:
        query += " AND date = ?"
        params.append(date)

    query += " ORDER BY date ASC, model ASC"

    # Execute query
    cursor = db.connection.execute(query, params)

    # Format results
    formatted_results = []

    for row in cursor.fetchall():
        trading_day_id = row[0]

        # Build response object
        day_data = {
            "date": row[3],
            "model": row[2],
            "job_id": row[1],

            "starting_position": {
                "holdings": db.get_starting_holdings(trading_day_id),
                "cash": row[4],  # starting_cash
                "portfolio_value": row[5]  # starting_portfolio_value
            },

            "daily_metrics": {
                "profit": row[6],  # daily_profit
                "return_pct": row[7],  # daily_return_pct
                "days_since_last_trading": row[17] if len(row) > 17 else 1
            },

            "trades": db.get_actions(trading_day_id),

            "final_position": {
                "holdings": db.get_ending_holdings(trading_day_id),
                "cash": row[8],  # ending_cash
                "portfolio_value": row[9]  # ending_portfolio_value
            },

            "metadata": {
                "total_actions": row[12] if row[12] is not None else 0,
                "session_duration_seconds": row[13],
                "completed_at": row[16]
            }
        }

        # Add reasoning if requested
        if reasoning == "summary":
            day_data["reasoning"] = row[10]  # reasoning_summary
        elif reasoning == "full":
            reasoning_full = row[11]  # reasoning_full
            day_data["reasoning"] = json.loads(reasoning_full) if reasoning_full else []
        else:
            day_data["reasoning"] = None

        formatted_results.append(day_data)

    return {
        "count": len(formatted_results),
        "results": formatted_results
    }
```

**Step 4: Register new route in app**

Modify `api/app.py` - add import and include router:

```python
from api.routes import results_v2

# Include routers
app.include_router(results_v2.router)
```

**Step 5: Run test to verify it passes**

Run: `./venv/bin/python -m pytest tests/integration/test_results_api_v2.py -v`

Expected: PASS

**Step 6: Commit**

```bash
git add api/routes/results_v2.py api/app.py tests/integration/test_results_api_v2.py
git commit -m "feat: add new day-centric results API endpoint"
```

---

## Task 7: Database Initialization

**Files:**
- Modify: `api/database.py`
- Create: `tests/integration/test_database_initialization.py`

**Step 1: Write failing test for database initialization**

Create `tests/integration/test_database_initialization.py`:

```python
import pytest
from api.database import Database


class TestDatabaseInitialization:

    def test_database_creates_new_schema_on_init(self, tmp_path):
        """Test database automatically creates trading_days schema."""
        db_path = tmp_path / "new.db"

        # Create database (should auto-initialize schema)
        db = Database(str(db_path))

        # Verify trading_days table exists
        cursor = db.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='trading_days'"
        )
        assert cursor.fetchone() is not None

        # Verify holdings table exists
        cursor = db.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='holdings'"
        )
        assert cursor.fetchone() is not None

        # Verify actions table exists
        cursor = db.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='actions'"
        )
        assert cursor.fetchone() is not None
```

**Step 2: Run test to verify it fails**

Run: `./venv/bin/python -m pytest tests/integration/test_database_initialization.py -v`

Expected: FAIL (tables don't exist)

**Step 3: Update Database class to auto-initialize schema**

Modify `api/database.py` - update `__init__` method:

```python
def __init__(self, db_path: str = None):
    """Initialize database connection.

    Args:
        db_path: Path to SQLite database file.
                 If None, uses default from deployment config.
    """
    if db_path is None:
        from tools.deployment_config import get_database_path
        db_path = get_database_path()

    self.db_path = db_path
    self.connection = sqlite3.connect(db_path, check_same_thread=False)
    self.connection.row_factory = sqlite3.Row

    # Auto-initialize schema if needed
    self._initialize_schema()

def _initialize_schema(self):
    """Initialize database schema if tables don't exist."""
    from api.migrations.001_trading_days_schema import create_trading_days_schema

    # Check if trading_days table exists
    cursor = self.connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='trading_days'"
    )

    if cursor.fetchone() is None:
        # Schema doesn't exist, create it
        create_trading_days_schema(self)
```

**Step 4: Run test to verify it passes**

Run: `./venv/bin/python -m pytest tests/integration/test_database_initialization.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add api/database.py tests/integration/test_database_initialization.py
git commit -m "feat: auto-initialize trading_days schema on database creation"
```

---

## Task 8: Remove Old Positions Table

**Files:**
- Create: `scripts/migrate_clean_database.py`
- Modify: `api/database.py` (remove old positions references)

**Step 1: Create migration script to clean database**

Create `scripts/migrate_clean_database.py`:

```python
#!/usr/bin/env python3
"""
Clean database migration script.

Drops old positions table and creates fresh trading_days schema.
WARNING: This deletes all existing position data.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.database import Database
from api.migrations.001_trading_days_schema import drop_old_positions_table


def migrate_clean_database():
    """Drop old schema and create clean new schema."""
    print("Starting clean database migration...")

    db = Database()

    # Drop old positions table
    print("Dropping old positions table...")
    drop_old_positions_table(db)

    # New schema already created by Database.__init__()
    print("New trading_days schema created successfully")

    # Verify new tables exist
    cursor = db.connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [row[0] for row in cursor.fetchall()]

    print(f"\nCurrent tables: {', '.join(tables)}")

    # Verify positions table is gone
    if 'positions' in tables:
        print("WARNING: positions table still exists!")
        return False

    # Verify new tables exist
    required_tables = ['trading_days', 'holdings', 'actions']
    for table in required_tables:
        if table not in tables:
            print(f"ERROR: Required table '{table}' not found!")
            return False

    print("\nMigration completed successfully!")
    return True


if __name__ == "__main__":
    success = migrate_clean_database()
    sys.exit(0 if success else 1)
```

Make executable:
```bash
chmod +x scripts/migrate_clean_database.py
```

**Step 2: Remove old positions table references**

Search for references to old positions table:
```bash
grep -r "positions" api/ agent/ --include="*.py" | grep -v "holdings"
```

Comment out or remove any code that references the old `positions` table.

**Step 3: Run migration script**

Run: `python scripts/migrate_clean_database.py`

Expected: Output showing successful migration and table list

**Step 4: Verify database state**

Run: `sqlite3 data/trading.db ".schema trading_days"`

Expected: Shows trading_days table schema

**Step 5: Commit**

```bash
git add scripts/migrate_clean_database.py api/database.py
git commit -m "feat: add clean database migration script and remove old positions references"
```

---

## Task 9: End-to-End Testing

**Files:**
- Create: `tests/e2e/test_full_simulation_workflow.py`

**Step 1: Write E2E test for complete workflow**

Create `tests/e2e/test_full_simulation_workflow.py`:

```python
import pytest
import time
from fastapi.testclient import TestClient
from api.app import app


@pytest.mark.e2e
class TestFullSimulationWorkflow:

    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)

    def test_complete_simulation_with_new_schema(self, client):
        """Test full simulation workflow with new database schema."""
        # 1. Trigger simulation
        response = client.post("/simulate/trigger", json={
            "start_date": "2025-01-15",
            "end_date": "2025-01-17",
            "models": ["gpt-4"]
        })

        assert response.status_code == 200
        job_id = response.json()["job_id"]

        # 2. Wait for completion (with timeout)
        max_wait = 300  # 5 minutes
        start_time = time.time()

        while time.time() - start_time < max_wait:
            status_response = client.get(f"/simulate/status/{job_id}")
            status = status_response.json()["status"]

            if status in ["completed", "failed"]:
                break

            time.sleep(5)

        assert status == "completed", "Simulation did not complete successfully"

        # 3. Query results without reasoning
        results_response = client.get(f"/results?job_id={job_id}")

        assert results_response.status_code == 200
        data = results_response.json()

        # Should have 3 trading days
        assert data["count"] == 3

        # 4. Verify first day structure
        day1 = data["results"][0]

        assert day1["date"] == "2025-01-15"
        assert day1["model"] == "gpt-4"
        assert "starting_position" in day1
        assert "daily_metrics" in day1
        assert "trades" in day1
        assert "final_position" in day1
        assert day1["reasoning"] is None  # Not requested

        # First day should have zero P&L
        assert day1["daily_metrics"]["profit"] == 0.0
        assert day1["daily_metrics"]["return_pct"] == 0.0

        # 5. Verify holdings chain across days
        day2 = data["results"][1]
        day3 = data["results"][2]

        # Day 2 starting = Day 1 ending
        assert day2["starting_position"]["holdings"] == day1["final_position"]["holdings"]
        assert day2["starting_position"]["cash"] == day1["final_position"]["cash"]

        # Day 3 starting = Day 2 ending
        assert day3["starting_position"]["holdings"] == day2["final_position"]["holdings"]
        assert day3["starting_position"]["cash"] == day2["final_position"]["cash"]

        # 6. Query results with reasoning summary
        summary_response = client.get(f"/results?job_id={job_id}&reasoning=summary")
        summary_data = summary_response.json()

        # Each day should have reasoning summary
        for result in summary_data["results"]:
            assert result["reasoning"] is not None
            assert isinstance(result["reasoning"], str)
            assert len(result["reasoning"]) > 0

        # 7. Query results with full reasoning
        full_response = client.get(f"/results?job_id={job_id}&reasoning=full")
        full_data = full_response.json()

        # Each day should have full reasoning log
        for result in full_data["results"]:
            assert result["reasoning"] is not None
            assert isinstance(result["reasoning"], list)
```

**Step 2: Run E2E test**

Run: `./venv/bin/python -m pytest tests/e2e/test_full_simulation_workflow.py -v -m e2e`

Expected: PASS (may take several minutes)

**Step 3: Commit**

```bash
git add tests/e2e/test_full_simulation_workflow.py
git commit -m "test: add end-to-end test for complete simulation workflow"
```

---

## Task 10: Documentation Updates

**Files:**
- Modify: `API_REFERENCE.md`
- Modify: `docs/developer/database-schema.md`
- Create: `docs/plans/2025-11-03-daily-pnl-results-api-design.md`

**Step 1: Update API reference documentation**

Modify `API_REFERENCE.md` - update the `/results` endpoint section:

```markdown
### GET /results

Get trading results grouped by day with daily P&L metrics.

**Query Parameters:**
- `job_id` (optional) - Filter by simulation job ID
- `model` (optional) - Filter by model signature
- `date` (optional) - Filter by trading date (YYYY-MM-DD)
- `reasoning` (optional) - Include reasoning logs: `none` (default), `summary`, `full`

**Example Request:**
```bash
curl "http://localhost:8080/results?job_id=abc123&reasoning=summary"
```

**Example Response:**
```json
{
  "count": 2,
  "results": [
    {
      "date": "2025-01-15",
      "model": "gpt-4",
      "job_id": "abc123",
      "starting_position": {
        "holdings": [],
        "cash": 10000.0,
        "portfolio_value": 10000.0
      },
      "daily_metrics": {
        "profit": 0.0,
        "return_pct": 0.0,
        "days_since_last_trading": 0
      },
      "trades": [
        {
          "action_type": "buy",
          "symbol": "AAPL",
          "quantity": 10,
          "price": 150.0,
          "created_at": "2025-01-15T14:30:00Z"
        }
      ],
      "final_position": {
        "holdings": [
          {"symbol": "AAPL", "quantity": 10}
        ],
        "cash": 8500.0,
        "portfolio_value": 10000.0
      },
      "metadata": {
        "total_actions": 1,
        "session_duration_seconds": 45.2,
        "completed_at": "2025-01-15T14:31:00Z"
      },
      "reasoning": "Analyzed AAPL earnings report. Bought 10 shares based on positive guidance."
    }
  ]
}
```

**Response Fields:**

**Day-level:**
- `date` - Trading date
- `model` - Model signature
- `job_id` - Simulation job ID

**starting_position:**
- `holdings` - Stock positions at start of day (from previous day's close)
- `cash` - Cash balance at start
- `portfolio_value` - Total portfolio value at start

**daily_metrics:**
- `profit` - Dollar amount gained/lost from previous close
- `return_pct` - Percentage return from previous close
- `days_since_last_trading` - Number of days since last trading day (1=normal, 3=weekend)

**trades:**
- Array of actions executed during the day
- `action_type` - "buy", "sell", or "no_trade"
- `symbol` - Stock symbol
- `quantity` - Number of shares
- `price` - Execution price

**final_position:**
- `holdings` - Stock positions at end of day
- `cash` - Cash balance at end
- `portfolio_value` - Total portfolio value at end

**metadata:**
- `total_actions` - Number of trades executed
- `session_duration_seconds` - AI session duration
- `completed_at` - Timestamp of session completion

**reasoning:**
- `null` if `reasoning=none` (default)
- String summary if `reasoning=summary`
- Array of message objects if `reasoning=full`
```

**Step 2: Update database schema documentation**

Modify `docs/developer/database-schema.md` - add new tables section:

```markdown
## trading_days

Core table for each model-day execution with daily P&L metrics.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| job_id | TEXT | Foreign key to jobs table |
| model | TEXT | Model signature |
| date | TEXT | Trading date (YYYY-MM-DD) |
| starting_cash | REAL | Cash at start of day |
| starting_portfolio_value | REAL | Total portfolio value at start |
| daily_profit | REAL | Dollar P&L from previous close |
| daily_return_pct | REAL | Percentage return from previous close |
| ending_cash | REAL | Cash at end of day |
| ending_portfolio_value | REAL | Total portfolio value at end |
| reasoning_summary | TEXT | AI-generated summary of trading decisions |
| reasoning_full | TEXT | JSON array of complete reasoning log |
| total_actions | INTEGER | Number of trades executed |
| session_duration_seconds | REAL | AI session duration |
| days_since_last_trading | INTEGER | Days since previous trading day |
| created_at | TIMESTAMP | Record creation timestamp |
| completed_at | TIMESTAMP | Session completion timestamp |

**Indexes:**
- `idx_trading_days_lookup` on (job_id, model, date)

**Constraints:**
- UNIQUE(job_id, model, date)

---

## holdings

Portfolio holdings snapshots (ending positions only).

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| trading_day_id | INTEGER | Foreign key to trading_days |
| symbol | TEXT | Stock symbol |
| quantity | INTEGER | Number of shares held |

**Indexes:**
- `idx_holdings_day` on (trading_day_id)

**Constraints:**
- UNIQUE(trading_day_id, symbol)
- ON DELETE CASCADE

**Note:** Starting holdings for day N are derived by querying holdings for day N-1.

---

## actions

Trade execution ledger.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| trading_day_id | INTEGER | Foreign key to trading_days |
| action_type | TEXT | "buy", "sell", or "no_trade" |
| symbol | TEXT | Stock symbol (NULL for no_trade) |
| quantity | INTEGER | Shares traded (NULL for no_trade) |
| price | REAL | Execution price (NULL for no_trade) |
| created_at | TIMESTAMP | Action timestamp |

**Indexes:**
- `idx_actions_day` on (trading_day_id)

**Constraints:**
- ON DELETE CASCADE
```

**Step 3: Copy design document to docs/plans**

Copy the brainstorming design document:
```bash
cp docs/plans/2025-11-03-daily-pnl-results-api-design.md docs/plans/
```

**Step 4: Commit documentation updates**

```bash
git add API_REFERENCE.md docs/developer/database-schema.md docs/plans/
git commit -m "docs: update API reference and database schema for new results endpoint"
```

---

## Task 11: Final Verification and Cleanup

**Files:**
- Run all tests
- Clean up temporary files
- Verify deployment readiness

**Step 1: Run complete test suite**

Run: `./venv/bin/python -m pytest tests/ -v --cov=. --cov-report=term-missing`

Expected: All tests pass with >85% coverage

**Step 2: Run validation scripts**

Run: `bash scripts/validate_docker_build.sh`

Expected: Docker build succeeds

Run: `bash scripts/test_api_endpoints.sh`

Expected: All API endpoints respond correctly

**Step 3: Test with development mode**

Run:
```bash
export DEPLOYMENT_MODE=DEV
export PRESERVE_DEV_DATA=false
python main.py configs/default_config.json
```

Expected: Simulation runs successfully with new schema

**Step 4: Clean up**

Remove any temporary test databases:
```bash
find . -name "*.db" -path "*/tmp/*" -delete
```

**Step 5: Final commit**

```bash
git add .
git commit -m "chore: final cleanup and verification for daily P&L refactor"
```

---

## Verification Checklist

Before marking implementation complete, verify:

- [ ] All unit tests pass
- [ ] All integration tests pass
- [ ] E2E test passes with real simulation
- [ ] API returns correct structure for `/results`
- [ ] Daily P&L calculated correctly (first day = 0, subsequent days show changes)
- [ ] Weekend gaps handled correctly
- [ ] Reasoning summary generated successfully
- [ ] Database schema migration complete
- [ ] Old positions table removed
- [ ] Documentation updated
- [ ] Docker build succeeds
- [ ] Development mode works with new schema

---

## Plan Complete

This implementation plan provides step-by-step instructions to refactor the AI-Trader database schema and API for day-centric results with accurate daily P&L calculations.

**Total estimated time:** 8-12 hours for experienced developer

**Key deliverables:**
1. New normalized database schema (trading_days, holdings, actions)
2. Daily P&L calculator with weekend handling
3. AI reasoning summary generator
4. Unified results API endpoint
5. Complete test coverage
6. Updated documentation

**Next steps after implementation:**
1. Run full test suite
2. Deploy to staging environment
3. Test with production-like data
4. Update client integrations to use new API structure
5. Monitor performance and adjust indexes if needed
