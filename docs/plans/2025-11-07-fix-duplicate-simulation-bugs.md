# Fix Duplicate Simulation Bugs Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Prevent duplicate simulations and ensure portfolio continuity across jobs by adding duplicate detection to job creation and removing job_id isolation from position queries.

**Architecture:** Two-part fix: (1) Add duplicate checking in JobManager.create_job() to skip already-completed model-day pairs, (2) Remove job_id filter from get_current_position_from_db() to enable cross-job trading history continuity.

**Tech Stack:** Python, SQLite, pytest

---

## Task 1: Add Duplicate Detection to JobManager

**Files:**
- Modify: `api/job_manager.py:53-131`
- Test: `tests/unit/test_job_manager_duplicate_detection.py` (new file)

**Step 1: Write the failing test**

Create `tests/unit/test_job_manager_duplicate_detection.py`:

```python
"""Test duplicate detection in job creation."""
import pytest
import tempfile
import os
from pathlib import Path
from api.job_manager import JobManager


@pytest.fixture
def temp_db():
    """Create temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)

    # Initialize schema
    from api.database import get_db_connection
    conn = get_db_connection(path)
    cursor = conn.cursor()

    # Create jobs table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            job_id TEXT PRIMARY KEY,
            config_path TEXT NOT NULL,
            status TEXT NOT NULL,
            date_range TEXT NOT NULL,
            models TEXT NOT NULL,
            created_at TEXT NOT NULL,
            started_at TEXT,
            updated_at TEXT,
            completed_at TEXT,
            total_duration_seconds REAL,
            error TEXT,
            warnings TEXT
        )
    """)

    # Create job_details table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS job_details (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            date TEXT NOT NULL,
            model TEXT NOT NULL,
            status TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            duration_seconds REAL,
            error TEXT,
            FOREIGN KEY (job_id) REFERENCES jobs(job_id) ON DELETE CASCADE,
            UNIQUE(job_id, date, model)
        )
    """)

    conn.commit()
    conn.close()

    yield path

    # Cleanup
    if os.path.exists(path):
        os.remove(path)


def test_create_job_with_filter_skips_completed_simulations(temp_db):
    """Test that job creation with model_day_filter skips already-completed pairs."""
    manager = JobManager(db_path=temp_db)

    # Create first job and mark model-day as completed
    job_id_1 = manager.create_job(
        config_path="test_config.json",
        date_range=["2025-10-15", "2025-10-16"],
        models=["deepseek-chat-v3.1"],
        model_day_filter=[("deepseek-chat-v3.1", "2025-10-15")]
    )

    # Mark as completed
    manager.update_job_detail_status(
        job_id_1,
        "2025-10-15",
        "deepseek-chat-v3.1",
        "completed"
    )

    # Try to create second job with overlapping date
    model_day_filter = [
        ("deepseek-chat-v3.1", "2025-10-15"),  # Already completed
        ("deepseek-chat-v3.1", "2025-10-16")   # Not yet completed
    ]

    job_id_2 = manager.create_job(
        config_path="test_config.json",
        date_range=["2025-10-15", "2025-10-16"],
        models=["deepseek-chat-v3.1"],
        model_day_filter=model_day_filter
    )

    # Get job details for second job
    details = manager.get_job_details(job_id_2)

    # Should only have 2025-10-16 (2025-10-15 was skipped as already completed)
    assert len(details) == 1
    assert details[0]["date"] == "2025-10-16"
    assert details[0]["model"] == "deepseek-chat-v3.1"


def test_create_job_without_filter_skips_all_completed_simulations(temp_db):
    """Test that job creation without filter skips all completed model-day pairs."""
    manager = JobManager(db_path=temp_db)

    # Create first job and complete some model-days
    job_id_1 = manager.create_job(
        config_path="test_config.json",
        date_range=["2025-10-15"],
        models=["model-a", "model-b"]
    )

    # Mark model-a/2025-10-15 as completed
    manager.update_job_detail_status(job_id_1, "2025-10-15", "model-a", "completed")
    # Leave model-b/2025-10-15 as pending

    # Create second job with same date range and models
    job_id_2 = manager.create_job(
        config_path="test_config.json",
        date_range=["2025-10-15", "2025-10-16"],
        models=["model-a", "model-b"]
    )

    # Get job details for second job
    details = manager.get_job_details(job_id_2)

    # Should have 3 entries (skip model-a/2025-10-15):
    # - model-b/2025-10-15 (not completed in job 1)
    # - model-a/2025-10-16 (new date)
    # - model-b/2025-10-16 (new date)
    assert len(details) == 3

    dates_models = [(d["date"], d["model"]) for d in details]
    assert ("2025-10-15", "model-a") not in dates_models  # Skipped
    assert ("2025-10-15", "model-b") in dates_models
    assert ("2025-10-16", "model-a") in dates_models
    assert ("2025-10-16", "model-b") in dates_models


def test_create_job_returns_warnings_for_skipped_simulations(temp_db):
    """Test that skipped simulations are returned as warnings."""
    manager = JobManager(db_path=temp_db)

    # Create and complete first simulation
    job_id_1 = manager.create_job(
        config_path="test_config.json",
        date_range=["2025-10-15"],
        models=["model-a"]
    )
    manager.update_job_detail_status(job_id_1, "2025-10-15", "model-a", "completed")

    # Try to create job with same model-day
    result = manager.create_job(
        config_path="test_config.json",
        date_range=["2025-10-15"],
        models=["model-a"]
    )

    # Result should be a dict with job_id and warnings
    assert isinstance(result, dict)
    assert "job_id" in result
    assert "warnings" in result
    assert len(result["warnings"]) == 1
    assert "model-a" in result["warnings"][0]
    assert "2025-10-15" in result["warnings"][0]
```

**Step 2: Run test to verify it fails**

Run:
```bash
pytest tests/unit/test_job_manager_duplicate_detection.py -v
```

Expected: FAIL with test errors showing that duplicate simulations are not being detected.

**Step 3: Implement duplicate detection in create_job()**

Modify `api/job_manager.py:53-131`:

```python
def create_job(
    self,
    config_path: str,
    date_range: List[str],
    models: List[str],
    model_day_filter: Optional[List[tuple]] = None
) -> Dict[str, Any]:
    """
    Create new simulation job.

    Args:
        config_path: Path to configuration file
        date_range: List of dates to simulate (YYYY-MM-DD)
        models: List of model signatures to execute
        model_day_filter: Optional list of (model, date) tuples to limit job_details.
                         If None, creates job_details for all model-date combinations.

    Returns:
        Dict with:
          - job_id: UUID of created job
          - warnings: List of warning messages for skipped simulations

    Raises:
        ValueError: If another job is already running/pending or if all simulations are already completed
    """
    if not self.can_start_new_job():
        raise ValueError("Another simulation job is already running or pending")

    job_id = str(uuid.uuid4())
    created_at = datetime.utcnow().isoformat() + "Z"

    conn = get_db_connection(self.db_path)
    cursor = conn.cursor()

    try:
        # Determine which model-day pairs to check
        if model_day_filter is not None:
            pairs_to_check = model_day_filter
        else:
            pairs_to_check = [(model, date) for date in date_range for model in models]

        # Check for already-completed simulations
        skipped_pairs = []
        pending_pairs = []

        for model, date in pairs_to_check:
            cursor.execute("""
                SELECT COUNT(*)
                FROM job_details
                WHERE model = ? AND date = ? AND status = 'completed'
            """, (model, date))

            count = cursor.fetchone()[0]

            if count > 0:
                skipped_pairs.append((model, date))
                logger.info(f"Skipping {model}/{date} - already completed in previous job")
            else:
                pending_pairs.append((model, date))

        # If all simulations are already completed, raise error
        if len(pending_pairs) == 0:
            warnings = [
                f"Skipped {model}/{date} - already completed"
                for model, date in skipped_pairs
            ]
            raise ValueError(
                f"All requested simulations are already completed. "
                f"Skipped {len(skipped_pairs)} model-day pair(s). "
                f"Details: {warnings}"
            )

        # Insert job
        cursor.execute("""
            INSERT INTO jobs (
                job_id, config_path, status, date_range, models, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            job_id,
            config_path,
            "pending",
            json.dumps(date_range),
            json.dumps(models),
            created_at
        ))

        # Create job_details only for pending pairs
        for model, date in pending_pairs:
            cursor.execute("""
                INSERT INTO job_details (
                    job_id, date, model, status
                )
                VALUES (?, ?, ?, ?)
            """, (job_id, date, model, "pending"))

        logger.info(f"Created job {job_id} with {len(pending_pairs)} model-day tasks")

        if skipped_pairs:
            logger.info(f"Skipped {len(skipped_pairs)} already-completed simulations")

        conn.commit()

        # Prepare warnings
        warnings = [
            f"Skipped {model}/{date} - already completed"
            for model, date in skipped_pairs
        ]

        return {
            "job_id": job_id,
            "warnings": warnings
        }

    finally:
        conn.close()
```

**Step 4: Update create_job() return type in docstring**

The return type changed from `str` to `Dict[str, Any]`. Search for all callers of `create_job()` and update them to handle the new return format.

**Step 5: Run test to verify it passes**

Run:
```bash
pytest tests/unit/test_job_manager_duplicate_detection.py -v
```

Expected: PASS for all tests.

**Step 6: Commit**

```bash
git add api/job_manager.py tests/unit/test_job_manager_duplicate_detection.py
git commit -m "feat: add duplicate detection to job creation

- Skip already-completed model-day pairs in create_job()
- Return warnings for skipped simulations
- Raise error if all simulations are already completed
- Add comprehensive test coverage"
```

---

## Task 2: Fix API Routes to Handle New create_job() Return Type

**Files:**
- Modify: `api/routes/*.py` (any files that call `job_manager.create_job()`)

**Step 1: Search for create_job() callers**

Run:
```bash
grep -r "create_job" api/routes/ --include="*.py" -n
```

Identify all locations that call `job_manager.create_job()`.

**Step 2: Update each caller to handle dict return type**

For each caller, change from:
```python
job_id = job_manager.create_job(...)
```

To:
```python
result = job_manager.create_job(...)
job_id = result["job_id"]
warnings = result.get("warnings", [])

# Log or return warnings if present
if warnings:
    logger.warning(f"Job {job_id} created with warnings: {warnings}")
```

**Step 3: Run integration tests**

Run:
```bash
pytest tests/integration/ -v -k job
```

Expected: All job-related integration tests should pass.

**Step 4: Commit**

```bash
git add api/routes/
git commit -m "fix: update create_job() callers to handle dict return type"
```

---

## Task 3: Remove job_id Filter from Position Queries

**Files:**
- Modify: `agent_tools/tool_trade.py:24-95`
- Test: `tests/unit/test_cross_job_position_continuity.py` (new file)

**Step 1: Write the failing test**

Create `tests/unit/test_cross_job_position_continuity.py`:

```python
"""Test portfolio continuity across multiple jobs."""
import pytest
import tempfile
import os
from agent_tools.tool_trade import get_current_position_from_db
from api.database import get_db_connection


@pytest.fixture
def temp_db():
    """Create temporary database with schema."""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)

    conn = get_db_connection(path)
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
    conn.close()

    yield path

    if os.path.exists(path):
        os.remove(path)


def test_position_continuity_across_jobs(temp_db):
    """Test that position queries see history from previous jobs."""
    # Insert trading_day from job 1
    conn = get_db_connection(temp_db)
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
    conn.close()

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


def test_position_returns_initial_state_for_first_day(temp_db):
    """Test that first trading day returns initial cash."""
    # No previous trading days exist
    position, _ = get_current_position_from_db(
        job_id="new-job-uuid",
        model="new-model",
        date="2025-10-13",
        initial_cash=10000.0
    )

    # Should return initial position
    assert position == {"CASH": 10000.0}


def test_position_uses_most_recent_prior_date(temp_db):
    """Test that position query uses the most recent date before current."""
    conn = get_db_connection(temp_db)
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
    conn.close()

    # Query for 2025-10-15 should use 2025-10-14's ending position
    position, _ = get_current_position_from_db(
        job_id="job-3",
        model="model-a",
        date="2025-10-15",
        initial_cash=10000.0
    )

    assert position["CASH"] == 12000.0  # From 2025-10-14, not 2025-10-13
```

**Step 2: Run test to verify it fails**

Run:
```bash
pytest tests/unit/test_cross_job_position_continuity.py::test_position_continuity_across_jobs -v
```

Expected: FAIL because current code filters by job_id and can't see previous job's data.

**Step 3: Remove job_id filter from get_current_position_from_db()**

Modify `agent_tools/tool_trade.py:54-60`:

```python
def get_current_position_from_db(
    job_id: str,
    model: str,
    date: str,
    initial_cash: float = 10000.0
) -> Tuple[Dict[str, float], int]:
    """
    Get starting position for current trading day from database (new schema).

    Queries most recent trading_day record BEFORE the given date (previous day's ending).
    Returns ending holdings and cash from that previous day, which becomes the
    starting position for the current day.

    NOTE: Searches across ALL jobs for the given model, enabling portfolio continuity
    even when new jobs are created with overlapping date ranges.

    Args:
        job_id: Job UUID (kept for compatibility but not used in query)
        model: Model signature
        date: Current trading date (will query for date < this)
        initial_cash: Initial cash if no prior data (first trading day)

    Returns:
        (position_dict, action_count) where:
          - position_dict: {"AAPL": 10, "MSFT": 5, "CASH": 8500.0}
          - action_count: Number of holdings (for action_id tracking)
    """
    db_path = get_db_path("data/jobs.db")
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    try:
        # Query most recent trading_day BEFORE current date (previous day's ending position)
        # NOTE: Removed job_id filter to enable cross-job continuity
        cursor.execute("""
            SELECT id, ending_cash
            FROM trading_days
            WHERE model = ? AND date < ?
            ORDER BY date DESC
            LIMIT 1
        """, (model, date))

        row = cursor.fetchone()

        if row is None:
            # First day - return initial position
            return {"CASH": initial_cash}, 0

        trading_day_id, ending_cash = row

        # Query holdings for that day
        cursor.execute("""
            SELECT symbol, quantity
            FROM holdings
            WHERE trading_day_id = ?
        """, (trading_day_id,))

        holdings_rows = cursor.fetchall()

        # Build position dict
        position = {"CASH": ending_cash}
        for symbol, quantity in holdings_rows:
            position[symbol] = quantity

        return position, len(holdings_rows)

    finally:
        conn.close()
```

**Step 4: Run test to verify it passes**

Run:
```bash
pytest tests/unit/test_cross_job_position_continuity.py -v
```

Expected: PASS for all tests.

**Step 5: Run existing position query tests**

Run:
```bash
pytest tests/unit/test_get_position_new_schema.py -v
```

Expected: PASS (existing behavior should still work).

**Step 6: Commit**

```bash
git add agent_tools/tool_trade.py tests/unit/test_cross_job_position_continuity.py
git commit -m "fix: enable cross-job portfolio continuity

- Remove job_id filter from get_current_position_from_db()
- Position queries now search across all jobs for the model
- Prevents portfolio reset when new jobs run overlapping dates
- Add test coverage for cross-job position continuity"
```

---

## Task 4: Add Integration Test for Complete Bug Fix

**Files:**
- Test: `tests/integration/test_duplicate_simulation_prevention.py` (new file)

**Step 1: Write integration test**

Create `tests/integration/test_duplicate_simulation_prevention.py`:

```python
"""Integration test for duplicate simulation prevention."""
import pytest
import tempfile
import os
import json
from pathlib import Path
from api.job_manager import JobManager
from api.model_day_executor import ModelDayExecutor
from api.database import get_db_connection


@pytest.fixture
def temp_env(tmp_path):
    """Create temporary environment with db and config."""
    # Create temp database
    db_path = str(tmp_path / "test_jobs.db")

    # Initialize database
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    # Create schema
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            job_id TEXT PRIMARY KEY,
            config_path TEXT NOT NULL,
            status TEXT NOT NULL,
            date_range TEXT NOT NULL,
            models TEXT NOT NULL,
            created_at TEXT NOT NULL,
            started_at TEXT,
            updated_at TEXT,
            completed_at TEXT,
            total_duration_seconds REAL,
            error TEXT,
            warnings TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS job_details (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            date TEXT NOT NULL,
            model TEXT NOT NULL,
            status TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            duration_seconds REAL,
            error TEXT,
            FOREIGN KEY (job_id) REFERENCES jobs(job_id) ON DELETE CASCADE,
            UNIQUE(job_id, date, model)
        )
    """)

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

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS holdings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trading_day_id INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            FOREIGN KEY (trading_day_id) REFERENCES trading_days(id) ON DELETE CASCADE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trading_day_id INTEGER NOT NULL,
            action_type TEXT NOT NULL,
            symbol TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            price REAL NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (trading_day_id) REFERENCES trading_days(id) ON DELETE CASCADE
        )
    """)

    conn.commit()
    conn.close()

    # Create mock config
    config_path = str(tmp_path / "test_config.json")
    config = {
        "models": [
            {
                "signature": "test-model",
                "basemodel": "mock/model",
                "enabled": True
            }
        ],
        "agent_config": {
            "max_steps": 10,
            "initial_cash": 10000.0
        },
        "log_config": {
            "log_path": str(tmp_path / "logs")
        },
        "date_range": {
            "init_date": "2025-10-13"
        }
    }

    with open(config_path, 'w') as f:
        json.dump(config, f)

    yield {
        "db_path": db_path,
        "config_path": config_path,
        "data_dir": str(tmp_path)
    }


def test_duplicate_simulation_is_skipped(temp_env):
    """Test that overlapping job skips already-completed simulation."""
    manager = JobManager(db_path=temp_env["db_path"])

    # Create first job
    result_1 = manager.create_job(
        config_path=temp_env["config_path"],
        date_range=["2025-10-15"],
        models=["test-model"]
    )
    job_id_1 = result_1["job_id"]

    # Simulate completion by manually inserting trading_day record
    conn = get_db_connection(temp_env["db_path"])
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO trading_days (
            job_id, model, date, starting_cash, ending_cash,
            profit, return_pct, portfolio_value, completed_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        job_id_1,
        "test-model",
        "2025-10-15",
        10000.0,
        9500.0,
        -500.0,
        -5.0,
        9500.0,
        "2025-11-07T01:00:00Z"
    ))

    conn.commit()
    conn.close()

    # Mark job_detail as completed
    manager.update_job_detail_status(
        job_id_1,
        "2025-10-15",
        "test-model",
        "completed"
    )

    # Try to create second job with same model-day
    result_2 = manager.create_job(
        config_path=temp_env["config_path"],
        date_range=["2025-10-15", "2025-10-16"],
        models=["test-model"]
    )

    # Should have warnings about skipped simulation
    assert len(result_2["warnings"]) == 1
    assert "2025-10-15" in result_2["warnings"][0]

    # Should only create job_detail for 2025-10-16
    details = manager.get_job_details(result_2["job_id"])
    assert len(details) == 1
    assert details[0]["date"] == "2025-10-16"


def test_portfolio_continues_from_previous_job(temp_env):
    """Test that new job continues portfolio from previous job's last day."""
    manager = JobManager(db_path=temp_env["db_path"])

    # Create and complete first job
    result_1 = manager.create_job(
        config_path=temp_env["config_path"],
        date_range=["2025-10-13"],
        models=["test-model"]
    )
    job_id_1 = result_1["job_id"]

    # Insert completed trading_day with holdings
    conn = get_db_connection(temp_env["db_path"])
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO trading_days (
            job_id, model, date, starting_cash, ending_cash,
            profit, return_pct, portfolio_value, completed_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        job_id_1,
        "test-model",
        "2025-10-13",
        10000.0,
        5000.0,
        0.0,
        0.0,
        15000.0,
        "2025-11-07T01:00:00Z"
    ))

    trading_day_id = cursor.lastrowid

    cursor.execute("""
        INSERT INTO holdings (trading_day_id, symbol, quantity)
        VALUES (?, ?, ?)
    """, (trading_day_id, "AAPL", 10))

    conn.commit()

    # Mark as completed
    manager.update_job_detail_status(job_id_1, "2025-10-13", "test-model", "completed")
    manager.update_job_status(job_id_1, "completed")

    # Create second job for next day
    result_2 = manager.create_job(
        config_path=temp_env["config_path"],
        date_range=["2025-10-14"],
        models=["test-model"]
    )
    job_id_2 = result_2["job_id"]

    # Get starting position for 2025-10-14
    from agent_tools.tool_trade import get_current_position_from_db
    position, _ = get_current_position_from_db(
        job_id=job_id_2,
        model="test-model",
        date="2025-10-14",
        initial_cash=10000.0
    )

    # Should continue from job 1's ending position
    assert position["CASH"] == 5000.0
    assert position["AAPL"] == 10

    conn.close()
```

**Step 2: Run integration test**

Run:
```bash
pytest tests/integration/test_duplicate_simulation_prevention.py -v
```

Expected: PASS for both tests.

**Step 3: Commit**

```bash
git add tests/integration/test_duplicate_simulation_prevention.py
git commit -m "test: add integration tests for duplicate prevention and cross-job continuity"
```

---

## Task 5: Update Documentation

**Files:**
- Modify: `CLAUDE.md` (add section about duplicate prevention)
- Modify: `docs/developer/architecture.md` (document cross-job continuity)

**Step 1: Update CLAUDE.md**

Add section after "Job System" section:

```markdown
### Duplicate Simulation Prevention

**Automatic Skip Logic:**
- `JobManager.create_job()` checks database for already-completed model-day pairs
- Skips completed simulations automatically
- Returns warnings list with skipped pairs
- Raises `ValueError` if all requested simulations are already completed

**Example:**
```python
result = job_manager.create_job(
    config_path="config.json",
    date_range=["2025-10-15", "2025-10-16"],
    models=["model-a"],
    model_day_filter=[("model-a", "2025-10-15")]  # Already completed
)

# result = {
#     "job_id": "new-job-uuid",
#     "warnings": ["Skipped model-a/2025-10-15 - already completed"]
# }
```

**Cross-Job Portfolio Continuity:**
- `get_current_position_from_db()` queries across ALL jobs for a given model
- Enables portfolio continuity even when new jobs are created with overlapping dates
- Starting position = most recent trading_day.ending_cash + holdings where date < current_date
```

**Step 2: Update architecture.md**

Add section about position tracking:

```markdown
### Position Tracking Across Jobs

**Design:** Portfolio state is tracked per-model across all jobs, not per-job.

**Query Logic:**
```python
# Get starting position for current trading day
SELECT id, ending_cash FROM trading_days
WHERE model = ? AND date < ?  # No job_id filter
ORDER BY date DESC
LIMIT 1
```

**Benefits:**
- Portfolio continuity when creating new jobs with overlapping dates
- Prevents accidental portfolio resets
- Enables flexible job scheduling (resume, rerun, backfill)

**Example:**
- Job 1: Runs 2025-10-13 to 2025-10-15 for model-a
- Job 2: Runs 2025-10-16 to 2025-10-20 for model-a
- Job 2 starts with Job 1's ending position from 2025-10-15
```

**Step 3: Commit**

```bash
git add CLAUDE.md docs/developer/architecture.md
git commit -m "docs: document duplicate prevention and cross-job continuity"
```

---

## Task 6: Run Full Test Suite

**Step 1: Run all unit tests**

Run:
```bash
bash scripts/run_tests.sh -t unit
```

Expected: All unit tests pass.

**Step 2: Run all integration tests**

Run:
```bash
bash scripts/run_tests.sh -t integration
```

Expected: All integration tests pass.

**Step 3: Run full test suite with coverage**

Run:
```bash
bash scripts/run_tests.sh
```

Expected: All tests pass, coverage >= 85%.

**Step 4: Commit if any fixes were needed**

If any tests failed and required fixes:
```bash
git add <fixed-files>
git commit -m "fix: address test failures from bug fix"
```

---

## Verification Checklist

After completing all tasks, verify:

- [ ] Unit tests pass for duplicate detection
- [ ] Unit tests pass for cross-job position continuity
- [ ] Integration tests pass for end-to-end scenarios
- [ ] All existing tests still pass
- [ ] Documentation updated with new behavior
- [ ] Code coverage >= 85%
- [ ] No regressions in job creation API
- [ ] Position queries work correctly for first trading day
- [ ] Position queries work correctly across job boundaries
- [ ] Warnings are properly logged and returned to API consumers

---

## Notes

**Design Decisions:**

1. **Skip vs Reject:** Chose to skip completed simulations automatically rather than rejecting the entire job. This provides better UX for overlapping date ranges.

2. **Cross-Job Queries:** Removed job_id filter from position queries to enable true portfolio continuity. This assumes model signatures are unique identifiers across all jobs.

3. **Warnings in Response:** Return warnings in create_job() response so API consumers can display skipped simulations to users.

**Edge Cases Handled:**

- All simulations already completed → Raise ValueError
- First trading day with no prior data → Return initial_cash
- Multiple jobs for same model → Use most recent completed date
- Partial job completion → Only skip fully completed model-days

**Future Enhancements:**

- Add `force_rerun` parameter to create_job() to override skip logic
- Add endpoint to query completion status before creating job
- Consider adding model-level position snapshots for faster queries
