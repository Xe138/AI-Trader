# Job Manager & Database Specification

## 1. Overview

The Job Manager is responsible for:
1. **Job lifecycle management** - Creating, tracking, updating job status
2. **Database operations** - SQLite CRUD operations for jobs and job_details
3. **Concurrency control** - Ensuring only one simulation runs at a time
4. **State persistence** - Maintaining job state across API restarts

---

## 2. Database Schema

### 2.1 SQLite Database Location

```
data/jobs.db
```

**Rationale:** Co-located with simulation data for easy volume mounting

### 2.2 Table: jobs

**Purpose:** Track high-level job metadata and status

```sql
CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    config_path TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('pending', 'running', 'completed', 'partial', 'failed')),
    date_range TEXT NOT NULL,  -- JSON array: ["2025-01-16", "2025-01-17"]
    models TEXT NOT NULL,      -- JSON array: ["claude-3.7-sonnet", "gpt-5"]
    created_at TEXT NOT NULL,  -- ISO 8601: "2025-01-20T14:30:00Z"
    started_at TEXT,           -- When first model-day started
    completed_at TEXT,         -- When last model-day finished
    total_duration_seconds REAL,
    error TEXT                 -- Top-level error message if job failed
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at DESC);
```

**Field Details:**
- `job_id`: UUID v4 (e.g., `550e8400-e29b-41d4-a716-446655440000`)
- `status`: Current job state
  - `pending`: Job created, not started yet
  - `running`: At least one model-day is executing
  - `completed`: All model-days succeeded
  - `partial`: Some model-days succeeded, some failed
  - `failed`: All model-days failed (rare edge case)
- `date_range`: JSON string for easy querying
- `models`: JSON string of enabled model signatures

### 2.3 Table: job_details

**Purpose:** Track individual model-day execution status

```sql
CREATE TABLE IF NOT EXISTS job_details (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    date TEXT NOT NULL,        -- "2025-01-16"
    model TEXT NOT NULL,       -- "gpt-5"
    status TEXT NOT NULL CHECK(status IN ('pending', 'running', 'completed', 'failed')),
    started_at TEXT,
    completed_at TEXT,
    duration_seconds REAL,
    error TEXT,                -- Error message if this model-day failed
    FOREIGN KEY (job_id) REFERENCES jobs(job_id) ON DELETE CASCADE
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_job_details_job_id ON job_details(job_id);
CREATE INDEX IF NOT EXISTS idx_job_details_status ON job_details(status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_job_details_unique ON job_details(job_id, date, model);
```

**Field Details:**
- Each row represents one model-day (e.g., `gpt-5` on `2025-01-16`)
- `UNIQUE INDEX` prevents duplicate execution entries
- `ON DELETE CASCADE` ensures orphaned records are cleaned up

### 2.4 Example Data

**jobs table:**
```
job_id                                | config_path              | status    | date_range                        | models                          | created_at           | started_at           | completed_at         | total_duration_seconds
--------------------------------------|--------------------------|-----------|-----------------------------------|---------------------------------|----------------------|----------------------|----------------------|----------------------
550e8400-e29b-41d4-a716-446655440000 | configs/default_config.json | completed | ["2025-01-16","2025-01-17"]     | ["gpt-5","claude-3.7-sonnet"]  | 2025-01-20T14:25:00Z | 2025-01-20T14:25:10Z | 2025-01-20T14:29:45Z | 275.3
```

**job_details table:**
```
id | job_id                               | date       | model              | status    | started_at           | completed_at         | duration_seconds | error
---|--------------------------------------|------------|--------------------|-----------|----------------------|----------------------|------------------|------
1  | 550e8400-e29b-41d4-a716-446655440000 | 2025-01-16 | gpt-5              | completed | 2025-01-20T14:25:10Z | 2025-01-20T14:25:48Z | 38.2             | NULL
2  | 550e8400-e29b-41d4-a716-446655440000 | 2025-01-16 | claude-3.7-sonnet  | completed | 2025-01-20T14:25:10Z | 2025-01-20T14:25:55Z | 45.1             | NULL
3  | 550e8400-e29b-41d4-a716-446655440000 | 2025-01-17 | gpt-5              | completed | 2025-01-20T14:25:56Z | 2025-01-20T14:26:36Z | 40.0             | NULL
4  | 550e8400-e29b-41d4-a716-446655440000 | 2025-01-17 | claude-3.7-sonnet  | completed | 2025-01-20T14:25:56Z | 2025-01-20T14:26:42Z | 46.5             | NULL
```

---

## 3. Job Manager Class

### 3.1 File Structure

```
api/
├── job_manager.py      # Core JobManager class
├── database.py         # SQLite connection and utilities
└── models.py           # Pydantic models
```

### 3.2 JobManager Interface

```python
# api/job_manager.py

from datetime import datetime
from typing import Optional, List, Dict, Tuple
import uuid
import json
from api.database import get_db_connection

class JobManager:
    """Manages simulation job lifecycle and database operations"""

    def __init__(self, db_path: str = "data/jobs.db"):
        self.db_path = db_path
        self._initialize_database()

    def _initialize_database(self) -> None:
        """Create tables if they don't exist"""
        conn = get_db_connection(self.db_path)
        # Execute CREATE TABLE statements from section 2.2 and 2.3
        conn.close()

    # ========== Job Creation ==========

    def create_job(
        self,
        config_path: str,
        date_range: List[str],
        models: List[str]
    ) -> str:
        """
        Create a new simulation job.

        Args:
            config_path: Path to config file
            date_range: List of trading dates to simulate
            models: List of model signatures to run

        Returns:
            job_id: UUID of created job

        Raises:
            ValueError: If another job is already running
        """
        # 1. Check if any jobs are currently running
        if not self.can_start_new_job():
            raise ValueError("Another simulation job is already running")

        # 2. Generate job ID
        job_id = str(uuid.uuid4())

        # 3. Create job record
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO jobs (
                job_id, config_path, status, date_range, models, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            job_id,
            config_path,
            "pending",
            json.dumps(date_range),
            json.dumps(models),
            datetime.utcnow().isoformat() + "Z"
        ))

        # 4. Create job_details records for each model-day
        for date in date_range:
            for model in models:
                cursor.execute("""
                    INSERT INTO job_details (
                        job_id, date, model, status
                    ) VALUES (?, ?, ?, ?)
                """, (job_id, date, model, "pending"))

        conn.commit()
        conn.close()

        return job_id

    # ========== Job Retrieval ==========

    def get_job(self, job_id: str) -> Optional[Dict]:
        """
        Get job metadata by ID.

        Returns:
            Job dict with keys: job_id, config_path, status, date_range (list),
            models (list), created_at, started_at, completed_at, total_duration_seconds

            Returns None if job not found.
        """
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,))
        row = cursor.fetchone()
        conn.close()

        if row is None:
            return None

        return {
            "job_id": row[0],
            "config_path": row[1],
            "status": row[2],
            "date_range": json.loads(row[3]),
            "models": json.loads(row[4]),
            "created_at": row[5],
            "started_at": row[6],
            "completed_at": row[7],
            "total_duration_seconds": row[8],
            "error": row[9]
        }

    def get_current_job(self) -> Optional[Dict]:
        """Get most recent job (for /simulate/current endpoint)"""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM jobs
            ORDER BY created_at DESC
            LIMIT 1
        """)
        row = cursor.fetchone()
        conn.close()

        if row is None:
            return None

        return self._row_to_job_dict(row)

    def get_running_jobs(self) -> List[Dict]:
        """Get all running or pending jobs"""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM jobs
            WHERE status IN ('pending', 'running')
            ORDER BY created_at DESC
        """)
        rows = cursor.fetchall()
        conn.close()

        return [self._row_to_job_dict(row) for row in rows]

    # ========== Job Status Updates ==========

    def update_job_status(
        self,
        job_id: str,
        status: str,
        error: Optional[str] = None
    ) -> None:
        """Update job status (pending → running → completed/partial/failed)"""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        updates = {"status": status}

        if status == "running" and self.get_job(job_id)["status"] == "pending":
            updates["started_at"] = datetime.utcnow().isoformat() + "Z"

        if status in ("completed", "partial", "failed"):
            updates["completed_at"] = datetime.utcnow().isoformat() + "Z"
            # Calculate total duration
            job = self.get_job(job_id)
            if job["started_at"]:
                started = datetime.fromisoformat(job["started_at"].replace("Z", ""))
                completed = datetime.utcnow()
                updates["total_duration_seconds"] = (completed - started).total_seconds()

        if error:
            updates["error"] = error

        # Build dynamic UPDATE query
        set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
        values = list(updates.values()) + [job_id]

        cursor.execute(f"""
            UPDATE jobs
            SET {set_clause}
            WHERE job_id = ?
        """, values)

        conn.commit()
        conn.close()

    def update_job_detail_status(
        self,
        job_id: str,
        date: str,
        model: str,
        status: str,
        error: Optional[str] = None
    ) -> None:
        """Update individual model-day status"""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        updates = {"status": status}

        # Get current detail status to determine if this is a status transition
        cursor.execute("""
            SELECT status, started_at FROM job_details
            WHERE job_id = ? AND date = ? AND model = ?
        """, (job_id, date, model))
        row = cursor.fetchone()

        if row:
            current_status = row[0]

            if status == "running" and current_status == "pending":
                updates["started_at"] = datetime.utcnow().isoformat() + "Z"

            if status in ("completed", "failed"):
                updates["completed_at"] = datetime.utcnow().isoformat() + "Z"
                # Calculate duration if started_at exists
                if row[1]:  # started_at
                    started = datetime.fromisoformat(row[1].replace("Z", ""))
                    completed = datetime.utcnow()
                    updates["duration_seconds"] = (completed - started).total_seconds()

        if error:
            updates["error"] = error

        # Build UPDATE query
        set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
        values = list(updates.values()) + [job_id, date, model]

        cursor.execute(f"""
            UPDATE job_details
            SET {set_clause}
            WHERE job_id = ? AND date = ? AND model = ?
        """, values)

        conn.commit()
        conn.close()

        # After updating detail, check if overall job status needs update
        self._update_job_status_from_details(job_id)

    def _update_job_status_from_details(self, job_id: str) -> None:
        """
        Recalculate job status based on job_details statuses.

        Logic:
        - If any detail is 'running' → job is 'running'
        - If all details are 'completed' → job is 'completed'
        - If some details are 'completed' and some 'failed' → job is 'partial'
        - If all details are 'failed' → job is 'failed'
        - If all details are 'pending' → job is 'pending'
        """
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT status, COUNT(*)
            FROM job_details
            WHERE job_id = ?
            GROUP BY status
        """, (job_id,))

        status_counts = {row[0]: row[1] for row in cursor.fetchall()}
        conn.close()

        # Determine overall job status
        if status_counts.get("running", 0) > 0:
            new_status = "running"
        elif status_counts.get("pending", 0) > 0:
            # Some details still pending, job is either pending or running
            current_job = self.get_job(job_id)
            new_status = current_job["status"]  # Keep current status
        elif status_counts.get("failed", 0) > 0 and status_counts.get("completed", 0) > 0:
            new_status = "partial"
        elif status_counts.get("failed", 0) > 0:
            new_status = "failed"
        else:
            new_status = "completed"

        self.update_job_status(job_id, new_status)

    # ========== Job Progress ==========

    def get_job_progress(self, job_id: str) -> Dict:
        """
        Get detailed progress for a job.

        Returns:
            {
                "total_model_days": int,
                "completed": int,
                "failed": int,
                "current": {"date": str, "model": str} | None,
                "details": [
                    {"date": str, "model": str, "status": str, "duration_seconds": float | None, "error": str | None},
                    ...
                ]
            }
        """
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        # Get all details for this job
        cursor.execute("""
            SELECT date, model, status, started_at, completed_at, duration_seconds, error
            FROM job_details
            WHERE job_id = ?
            ORDER BY date ASC, model ASC
        """, (job_id,))

        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return {
                "total_model_days": 0,
                "completed": 0,
                "failed": 0,
                "current": None,
                "details": []
            }

        total = len(rows)
        completed = sum(1 for row in rows if row[2] == "completed")
        failed = sum(1 for row in rows if row[2] == "failed")

        # Find currently running model-day
        current = None
        for row in rows:
            if row[2] == "running":
                current = {"date": row[0], "model": row[1]}
                break

        # Build details list
        details = []
        for row in rows:
            details.append({
                "date": row[0],
                "model": row[1],
                "status": row[2],
                "started_at": row[3],
                "completed_at": row[4],
                "duration_seconds": row[5],
                "error": row[6]
            })

        return {
            "total_model_days": total,
            "completed": completed,
            "failed": failed,
            "current": current,
            "details": details
        }

    # ========== Concurrency Control ==========

    def can_start_new_job(self) -> bool:
        """Check if a new job can be started (max 1 concurrent job)"""
        running_jobs = self.get_running_jobs()
        return len(running_jobs) == 0

    def find_job_by_date_range(self, date_range: List[str]) -> Optional[Dict]:
        """Find job with exact matching date range (for idempotency check)"""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        # Query recent jobs (last 24 hours)
        cursor.execute("""
            SELECT * FROM jobs
            WHERE created_at > datetime('now', '-1 day')
            ORDER BY created_at DESC
        """)

        rows = cursor.fetchall()
        conn.close()

        # Check each job's date_range
        target_range = set(date_range)
        for row in rows:
            job_range = set(json.loads(row[3]))  # date_range column
            if job_range == target_range:
                return self._row_to_job_dict(row)

        return None

    # ========== Utility Methods ==========

    def _row_to_job_dict(self, row: tuple) -> Dict:
        """Convert DB row to job dictionary"""
        return {
            "job_id": row[0],
            "config_path": row[1],
            "status": row[2],
            "date_range": json.loads(row[3]),
            "models": json.loads(row[4]),
            "created_at": row[5],
            "started_at": row[6],
            "completed_at": row[7],
            "total_duration_seconds": row[8],
            "error": row[9]
        }

    def cleanup_old_jobs(self, days: int = 30) -> int:
        """
        Delete jobs older than specified days (cleanup maintenance).

        Returns:
            Number of jobs deleted
        """
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            DELETE FROM jobs
            WHERE created_at < datetime('now', '-' || ? || ' days')
        """, (days,))

        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()

        return deleted_count
```

---

## 4. Database Utility Module

```python
# api/database.py

import sqlite3
from typing import Optional
import os

def get_db_connection(db_path: str = "data/jobs.db") -> sqlite3.Connection:
    """
    Get SQLite database connection.

    Ensures:
    - Database directory exists
    - Foreign keys are enabled
    - Row factory returns dict-like objects
    """
    # Ensure data directory exists
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON")  # Enable FK constraints
    conn.row_factory = sqlite3.Row  # Return rows as dict-like objects

    return conn

def initialize_database(db_path: str = "data/jobs.db") -> None:
    """Create database tables if they don't exist"""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    # Create jobs table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            job_id TEXT PRIMARY KEY,
            config_path TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('pending', 'running', 'completed', 'partial', 'failed')),
            date_range TEXT NOT NULL,
            models TEXT NOT NULL,
            created_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            total_duration_seconds REAL,
            error TEXT
        )
    """)

    # Create indexes
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at DESC)
    """)

    # Create job_details table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS job_details (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            date TEXT NOT NULL,
            model TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('pending', 'running', 'completed', 'failed')),
            started_at TEXT,
            completed_at TEXT,
            duration_seconds REAL,
            error TEXT,
            FOREIGN KEY (job_id) REFERENCES jobs(job_id) ON DELETE CASCADE
        )
    """)

    # Create indexes
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_job_details_job_id ON job_details(job_id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_job_details_status ON job_details(status)
    """)
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_job_details_unique
        ON job_details(job_id, date, model)
    """)

    conn.commit()
    conn.close()
```

---

## 5. State Transitions

### 5.1 Job Status State Machine

```
pending ──────────────> running ──────────> completed
                          │                     │
                          │                     │
                          └────────────> partial
                          │                     │
                          └────────────> failed
```

**Transition Logic:**
- `pending → running`: When first model-day starts executing
- `running → completed`: When all model-days complete successfully
- `running → partial`: When some model-days succeed, some fail
- `running → failed`: When all model-days fail (rare)

### 5.2 Job Detail Status State Machine

```
pending ──────> running ──────> completed
                   │
                   └───────────> failed
```

**Transition Logic:**
- `pending → running`: When worker starts executing that model-day
- `running → completed`: When `agent.run_trading_session()` succeeds
- `running → failed`: When `agent.run_trading_session()` raises exception after retries

---

## 6. Concurrency Scenarios

### 6.1 Scenario: Duplicate Trigger Requests

**Timeline:**
1. Request A: POST /simulate/trigger → Job created with date_range=[2025-01-16, 2025-01-17]
2. Request B (5 seconds later): POST /simulate/trigger → Same date range

**Expected Behavior:**
- Request A: Returns `{"job_id": "abc123", "status": "accepted"}`
- Request B: `find_job_by_date_range()` finds Job abc123
- Request B: Returns `{"job_id": "abc123", "status": "running", ...}` (same job)

**Code:**
```python
# In /simulate/trigger endpoint
existing_job = job_manager.find_job_by_date_range(date_range)
if existing_job:
    # Return existing job instead of creating duplicate
    return existing_job
```

### 6.2 Scenario: Concurrent Jobs with Different Dates

**Timeline:**
1. Job A running: date_range=[2025-01-01 to 2025-01-10] (started 5 min ago)
2. Request: POST /simulate/trigger with date_range=[2025-01-11 to 2025-01-15]

**Expected Behavior:**
- `can_start_new_job()` returns False (Job A is still running)
- Request returns 409 Conflict with details of Job A

### 6.3 Scenario: Job Cleanup on API Restart

**Problem:** API crashes while job is running. On restart, job stuck in "running" state.

**Solution:** On API startup, detect stale jobs and mark as failed:
```python
# In api/main.py startup event
@app.on_event("startup")
async def startup_event():
    job_manager = JobManager()

    # Find jobs stuck in 'running' or 'pending' state
    stale_jobs = job_manager.get_running_jobs()

    for job in stale_jobs:
        # Mark as failed with explanation
        job_manager.update_job_status(
            job["job_id"],
            "failed",
            error="API restarted while job was running"
        )
```

---

## 7. Testing Strategy

### 7.1 Unit Tests

```python
# tests/test_job_manager.py

import pytest
from api.job_manager import JobManager
import tempfile
import os

@pytest.fixture
def job_manager():
    # Use temporary database for tests
    temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    temp_db.close()

    jm = JobManager(db_path=temp_db.name)
    yield jm

    # Cleanup
    os.unlink(temp_db.name)

def test_create_job(job_manager):
    job_id = job_manager.create_job(
        config_path="configs/test.json",
        date_range=["2025-01-16", "2025-01-17"],
        models=["gpt-5", "claude-3.7-sonnet"]
    )

    assert job_id is not None
    job = job_manager.get_job(job_id)
    assert job["status"] == "pending"
    assert job["date_range"] == ["2025-01-16", "2025-01-17"]

    # Check job_details created
    progress = job_manager.get_job_progress(job_id)
    assert progress["total_model_days"] == 4  # 2 dates × 2 models

def test_concurrent_job_blocked(job_manager):
    # Create first job
    job1_id = job_manager.create_job("configs/test.json", ["2025-01-16"], ["gpt-5"])

    # Try to create second job while first is pending
    with pytest.raises(ValueError, match="Another simulation job is already running"):
        job_manager.create_job("configs/test.json", ["2025-01-17"], ["gpt-5"])

    # Mark first job as completed
    job_manager.update_job_status(job1_id, "completed")

    # Now second job should be allowed
    job2_id = job_manager.create_job("configs/test.json", ["2025-01-17"], ["gpt-5"])
    assert job2_id is not None

def test_job_status_transitions(job_manager):
    job_id = job_manager.create_job("configs/test.json", ["2025-01-16"], ["gpt-5"])

    # Update job detail to running
    job_manager.update_job_detail_status(job_id, "2025-01-16", "gpt-5", "running")

    # Job should now be 'running'
    job = job_manager.get_job(job_id)
    assert job["status"] == "running"
    assert job["started_at"] is not None

    # Complete the detail
    job_manager.update_job_detail_status(job_id, "2025-01-16", "gpt-5", "completed")

    # Job should now be 'completed'
    job = job_manager.get_job(job_id)
    assert job["status"] == "completed"
    assert job["completed_at"] is not None

def test_partial_job_status(job_manager):
    job_id = job_manager.create_job(
        "configs/test.json",
        ["2025-01-16"],
        ["gpt-5", "claude-3.7-sonnet"]
    )

    # One model succeeds
    job_manager.update_job_detail_status(job_id, "2025-01-16", "gpt-5", "running")
    job_manager.update_job_detail_status(job_id, "2025-01-16", "gpt-5", "completed")

    # One model fails
    job_manager.update_job_detail_status(job_id, "2025-01-16", "claude-3.7-sonnet", "running")
    job_manager.update_job_detail_status(
        job_id, "2025-01-16", "claude-3.7-sonnet", "failed",
        error="API timeout"
    )

    # Job should be 'partial'
    job = job_manager.get_job(job_id)
    assert job["status"] == "partial"

    progress = job_manager.get_job_progress(job_id)
    assert progress["completed"] == 1
    assert progress["failed"] == 1
```

---

## 8. Performance Considerations

### 8.1 Database Indexing

- `idx_jobs_status`: Fast filtering for running jobs
- `idx_jobs_created_at DESC`: Fast retrieval of most recent job
- `idx_job_details_unique`: Prevent duplicate model-day entries

### 8.2 Connection Pooling

For MVP, using `sqlite3.connect()` per operation is acceptable (low concurrency).

For higher concurrency (future), consider:
- SQLAlchemy ORM with connection pooling
- PostgreSQL for production deployments

### 8.3 Query Optimization

**Avoid N+1 queries:**
```python
# BAD: Separate query for each job's progress
for job in jobs:
    progress = job_manager.get_job_progress(job["job_id"])

# GOOD: Join jobs and job_details in single query
SELECT
    jobs.*,
    COUNT(job_details.id) as total,
    SUM(CASE WHEN job_details.status = 'completed' THEN 1 ELSE 0 END) as completed
FROM jobs
LEFT JOIN job_details ON jobs.job_id = job_details.job_id
GROUP BY jobs.job_id
```

---

## 9. Error Handling

### 9.1 Database Errors

**Scenario:** SQLite database is locked or corrupted

**Handling:**
```python
try:
    job_id = job_manager.create_job(...)
except sqlite3.OperationalError as e:
    # Database locked - retry with exponential backoff
    logger.error(f"Database error: {e}")
    raise HTTPException(status_code=503, detail="Database temporarily unavailable")
except sqlite3.IntegrityError as e:
    # Constraint violation (e.g., duplicate job_id)
    logger.error(f"Integrity error: {e}")
    raise HTTPException(status_code=400, detail="Invalid job data")
```

### 9.2 Foreign Key Violations

**Scenario:** Attempt to create job_detail for non-existent job

**Prevention:**
- Always create job record before job_details records
- Use transactions to ensure atomicity

```python
def create_job(self, ...):
    conn = get_db_connection(self.db_path)
    try:
        cursor = conn.cursor()

        # Insert job
        cursor.execute("INSERT INTO jobs ...")

        # Insert job_details
        for date in date_range:
            for model in models:
                cursor.execute("INSERT INTO job_details ...")

        conn.commit()  # Atomic commit
    except Exception as e:
        conn.rollback()  # Rollback on any error
        raise
    finally:
        conn.close()
```

---

## 10. Migration Strategy

### 10.1 Schema Versioning

For future schema changes, use migration scripts:

```
data/
└── migrations/
    ├── 001_initial_schema.sql
    ├── 002_add_priority_column.sql
    └── ...
```

Track applied migrations in database:
```sql
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
```

### 10.2 Backward Compatibility

When adding columns:
- Use `ALTER TABLE ADD COLUMN ... DEFAULT ...` for backward compatibility
- Never remove columns (deprecate instead)
- Version API responses to handle schema changes

---

## Summary

The Job Manager provides:
1. **Robust job tracking** with SQLite persistence
2. **Concurrency control** ensuring single-job execution
3. **Granular progress monitoring** at model-day level
4. **Flexible status handling** (completed/partial/failed)
5. **Idempotency** for duplicate trigger requests

Next specification: **Background Worker Architecture**
