# Async Price Data Download Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move price data downloading from synchronous API endpoint to background worker thread, enabling <1s API responses and better progress visibility.

**Architecture:** Refactor `/simulate/trigger` to create jobs immediately without downloading data. SimulationWorker prepares data (downloads if needed) before executing trades. Add "downloading_data" status and warnings field for visibility.

**Tech Stack:** FastAPI, SQLite, Python 3.12, pytest

---

## Task 1: Add Database Support for New Status and Warnings

**Files:**
- Modify: `api/database.py:88`
- Modify: `api/database.py:96`
- Test: `tests/unit/test_database_schema.py`

**Step 1: Write failing test for "downloading_data" status**

```python
# In tests/unit/test_database_schema.py (create if doesn't exist)
import pytest
import sqlite3
from api.database import initialize_database, get_db_connection

def test_jobs_table_allows_downloading_data_status(tmp_path):
    """Test that jobs table accepts downloading_data status."""
    db_path = str(tmp_path / "test.db")
    initialize_database(db_path)

    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    # Should not raise constraint violation
    cursor.execute("""
        INSERT INTO jobs (job_id, config_path, status, date_range, models, created_at)
        VALUES ('test-123', 'config.json', 'downloading_data', '[]', '[]', '2025-11-01T00:00:00Z')
    """)
    conn.commit()

    # Verify it was inserted
    cursor.execute("SELECT status FROM jobs WHERE job_id = 'test-123'")
    result = cursor.fetchone()
    assert result[0] == "downloading_data"

    conn.close()
```

**Step 2: Run test to verify it fails**

Run: `../../venv/bin/python -m pytest tests/unit/test_database_schema.py::test_jobs_table_allows_downloading_data_status -v`

Expected: FAIL with constraint violation (status not in allowed values)

**Step 3: Add "downloading_data" to status enum**

In `api/database.py:88`, update CHECK constraint:

```python
status TEXT NOT NULL CHECK(status IN ('pending', 'downloading_data', 'running', 'completed', 'partial', 'failed')),
```

**Step 4: Run test to verify it passes**

Run: `../../venv/bin/python -m pytest tests/unit/test_database_schema.py::test_jobs_table_allows_downloading_data_status -v`

Expected: PASS

**Step 5: Write failing test for warnings column**

Add to `tests/unit/test_database_schema.py`:

```python
def test_jobs_table_has_warnings_column(tmp_path):
    """Test that jobs table has warnings TEXT column."""
    db_path = str(tmp_path / "test.db")
    initialize_database(db_path)

    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    # Insert job with warnings
    cursor.execute("""
        INSERT INTO jobs (job_id, config_path, status, date_range, models, created_at, warnings)
        VALUES ('test-456', 'config.json', 'completed', '[]', '[]', '2025-11-01T00:00:00Z', '["Warning 1", "Warning 2"]')
    """)
    conn.commit()

    # Verify warnings can be retrieved
    cursor.execute("SELECT warnings FROM jobs WHERE job_id = 'test-456'")
    result = cursor.fetchone()
    assert result[0] == '["Warning 1", "Warning 2"]'

    conn.close()
```

**Step 6: Run test to verify it fails**

Run: `../../venv/bin/python -m pytest tests/unit/test_database_schema.py::test_jobs_table_has_warnings_column -v`

Expected: FAIL (no such column: warnings)

**Step 7: Add warnings column to jobs table**

In `api/database.py:96` (after error column), add:

```python
error TEXT,
warnings TEXT
```

**Step 8: Run test to verify it passes**

Run: `../../venv/bin/python -m pytest tests/unit/test_database_schema.py::test_jobs_table_has_warnings_column -v`

Expected: PASS

**Step 9: Commit database schema changes**

```bash
git add api/database.py tests/unit/test_database_schema.py
git commit -m "feat(db): add downloading_data status and warnings column

Add support for:
- downloading_data job status for visibility during data prep
- warnings TEXT column for storing job-level warnings (JSON array)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 2: Add JobManager Method for Warnings

**Files:**
- Modify: `api/job_manager.py`
- Test: `tests/unit/test_job_manager.py`

**Step 1: Write failing test for add_job_warnings**

Add to `tests/unit/test_job_manager.py`:

```python
import json

def test_add_job_warnings(tmp_path):
    """Test adding warnings to a job."""
    db_path = str(tmp_path / "test.db")
    initialize_database(db_path)
    job_manager = JobManager(db_path=db_path)

    # Create a job
    job_id = job_manager.create_job(
        config_path="config.json",
        date_range=["2025-10-01"],
        models=["gpt-5"]
    )

    # Add warnings
    warnings = ["Rate limit reached", "Skipped 2 dates"]
    job_manager.add_job_warnings(job_id, warnings)

    # Verify warnings were stored
    job = job_manager.get_job(job_id)
    stored_warnings = json.loads(job["warnings"])
    assert stored_warnings == warnings
```

**Step 2: Run test to verify it fails**

Run: `../../venv/bin/python -m pytest tests/unit/test_job_manager.py::test_add_job_warnings -v`

Expected: FAIL (AttributeError: 'JobManager' has no attribute 'add_job_warnings')

**Step 3: Implement add_job_warnings method**

In `api/job_manager.py`, add method (find appropriate location after existing update methods):

```python
def add_job_warnings(self, job_id: str, warnings: List[str]) -> None:
    """
    Store warnings for a job.

    Args:
        job_id: Job UUID
        warnings: List of warning messages
    """
    import json

    conn = get_db_connection(self.db_path)
    cursor = conn.cursor()

    warnings_json = json.dumps(warnings)

    cursor.execute("""
        UPDATE jobs
        SET warnings = ?
        WHERE job_id = ?
    """, (warnings_json, job_id))

    conn.commit()
    conn.close()

    logger.info(f"Added {len(warnings)} warnings to job {job_id}")
```

**Step 4: Add import for List if not present**

At top of `api/job_manager.py`, ensure:

```python
from typing import Dict, Any, List, Optional
```

**Step 5: Run test to verify it passes**

Run: `../../venv/bin/python -m pytest tests/unit/test_job_manager.py::test_add_job_warnings -v`

Expected: PASS

**Step 6: Commit JobManager changes**

```bash
git add api/job_manager.py tests/unit/test_job_manager.py
git commit -m "feat(api): add JobManager.add_job_warnings method

Store job warnings as JSON array in database.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 3: Add Response Model Warnings Fields

**Files:**
- Modify: `api/main.py:336` (SimulateTriggerResponse)
- Modify: `api/main.py:353` (JobStatusResponse)
- Test: `tests/unit/test_response_models.py`

**Step 1: Write failing test for response model warnings**

Create `tests/unit/test_response_models.py`:

```python
from api.main import SimulateTriggerResponse, JobStatusResponse, JobProgress

def test_simulate_trigger_response_accepts_warnings():
    """Test SimulateTriggerResponse accepts warnings field."""
    response = SimulateTriggerResponse(
        job_id="test-123",
        status="completed",
        total_model_days=10,
        message="Job completed",
        deployment_mode="DEV",
        is_dev_mode=True,
        warnings=["Rate limited", "Skipped 2 dates"]
    )

    assert response.warnings == ["Rate limited", "Skipped 2 dates"]

def test_job_status_response_accepts_warnings():
    """Test JobStatusResponse accepts warnings field."""
    response = JobStatusResponse(
        job_id="test-123",
        status="completed",
        progress=JobProgress(total_model_days=10, completed=10, failed=0, pending=0),
        date_range=["2025-10-01"],
        models=["gpt-5"],
        created_at="2025-11-01T00:00:00Z",
        details=[],
        deployment_mode="DEV",
        is_dev_mode=True,
        warnings=["Rate limited"]
    )

    assert response.warnings == ["Rate limited"]
```

**Step 2: Run tests to verify they fail**

Run: `../../venv/bin/python -m pytest tests/unit/test_response_models.py -v`

Expected: FAIL (pydantic validation error - unexpected field)

**Step 3: Add warnings to SimulateTriggerResponse**

In `api/main.py`, find SimulateTriggerResponse class (around line 68) and add:

```python
class SimulateTriggerResponse(BaseModel):
    """Response body for POST /simulate/trigger."""
    job_id: str
    status: str
    total_model_days: int
    message: str
    deployment_mode: str
    is_dev_mode: bool
    preserve_dev_data: Optional[bool] = None
    warnings: Optional[List[str]] = None  # NEW
```

**Step 4: Add warnings to JobStatusResponse**

In `api/main.py`, find JobStatusResponse class (around line 87) and add:

```python
class JobStatusResponse(BaseModel):
    """Response body for GET /simulate/status/{job_id}."""
    job_id: str
    status: str
    progress: JobProgress
    date_range: List[str]
    models: List[str]
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    total_duration_seconds: Optional[float] = None
    error: Optional[str] = None
    details: List[Dict[str, Any]]
    deployment_mode: str
    is_dev_mode: bool
    preserve_dev_data: Optional[bool] = None
    warnings: Optional[List[str]] = None  # NEW
```

**Step 5: Run tests to verify they pass**

Run: `../../venv/bin/python -m pytest tests/unit/test_response_models.py -v`

Expected: PASS

**Step 6: Commit response model changes**

```bash
git add api/main.py tests/unit/test_response_models.py
git commit -m "feat(api): add warnings field to response models

Add optional warnings field to:
- SimulateTriggerResponse
- JobStatusResponse

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 4: Implement SimulationWorker Helper Methods

**Files:**
- Modify: `api/simulation_worker.py`
- Test: `tests/unit/test_simulation_worker.py`

**Step 4.1: Add _download_price_data helper**

**Step 1: Write failing test**

Add to `tests/unit/test_simulation_worker.py`:

```python
from unittest.mock import Mock, MagicMock
from api.simulation_worker import SimulationWorker

def test_download_price_data_success(tmp_path, monkeypatch):
    """Test successful price data download."""
    db_path = str(tmp_path / "test.db")
    initialize_database(db_path)

    worker = SimulationWorker(job_id="test-123", db_path=db_path)

    # Mock price manager
    mock_price_manager = Mock()
    mock_price_manager.download_missing_data_prioritized.return_value = {
        "downloaded": ["AAPL", "MSFT"],
        "failed": [],
        "rate_limited": False
    }

    warnings = []
    missing_coverage = {"AAPL": {"2025-10-01"}, "MSFT": {"2025-10-01"}}

    worker._download_price_data(mock_price_manager, missing_coverage, ["2025-10-01"], warnings)

    # Verify download was called
    mock_price_manager.download_missing_data_prioritized.assert_called_once()

    # No warnings for successful download
    assert len(warnings) == 0

def test_download_price_data_rate_limited(tmp_path):
    """Test price download with rate limit."""
    db_path = str(tmp_path / "test.db")
    initialize_database(db_path)

    worker = SimulationWorker(job_id="test-456", db_path=db_path)

    # Mock price manager
    mock_price_manager = Mock()
    mock_price_manager.download_missing_data_prioritized.return_value = {
        "downloaded": ["AAPL"],
        "failed": ["MSFT"],
        "rate_limited": True
    }

    warnings = []
    missing_coverage = {"AAPL": {"2025-10-01"}, "MSFT": {"2025-10-01"}}

    worker._download_price_data(mock_price_manager, missing_coverage, ["2025-10-01"], warnings)

    # Should add rate limit warning
    assert len(warnings) == 1
    assert "Rate limit" in warnings[0]
```

**Step 2: Run tests to verify they fail**

Run: `../../venv/bin/python -m pytest tests/unit/test_simulation_worker.py::test_download_price_data_success -v`

Expected: FAIL (AttributeError: no attribute '_download_price_data')

**Step 3: Implement _download_price_data method**

In `api/simulation_worker.py`, add method after `_execute_model_day`:

```python
def _download_price_data(
    self,
    price_manager,
    missing_coverage: Dict[str, Set[str]],
    requested_dates: List[str],
    warnings: List[str]
) -> None:
    """Download missing price data with progress logging."""
    from typing import Set, Dict

    logger.info(f"Job {self.job_id}: Starting prioritized download...")

    requested_dates_set = set(requested_dates)

    download_result = price_manager.download_missing_data_prioritized(
        missing_coverage,
        requested_dates_set
    )

    downloaded = len(download_result["downloaded"])
    failed = len(download_result["failed"])
    total = downloaded + failed

    logger.info(
        f"Job {self.job_id}: Download complete - "
        f"{downloaded}/{total} symbols succeeded"
    )

    if download_result["rate_limited"]:
        msg = f"Rate limit reached - downloaded {downloaded}/{total} symbols"
        warnings.append(msg)
        logger.warning(f"Job {self.job_id}: {msg}")

    if failed > 0 and not download_result["rate_limited"]:
        msg = f"{failed} symbols failed to download"
        warnings.append(msg)
        logger.warning(f"Job {self.job_id}: {msg}")
```

**Step 4: Add necessary imports at top of file**

Ensure `api/simulation_worker.py` has:

```python
from typing import Dict, Any, List, Set
```

**Step 5: Run tests to verify they pass**

Run: `../../venv/bin/python -m pytest tests/unit/test_simulation_worker.py::test_download_price_data_success tests/unit/test_simulation_worker.py::test_download_price_data_rate_limited -v`

Expected: PASS

**Step 6: Commit _download_price_data**

```bash
git add api/simulation_worker.py tests/unit/test_simulation_worker.py
git commit -m "feat(worker): add _download_price_data helper method

Handle price data download with rate limit detection and warning generation.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

**Step 4.2: Add _filter_completed_dates helper**

**Step 1: Write failing test**

Add to `tests/unit/test_simulation_worker.py`:

```python
def test_filter_completed_dates_all_new(tmp_path, monkeypatch):
    """Test filtering when no dates are completed."""
    db_path = str(tmp_path / "test.db")
    initialize_database(db_path)

    worker = SimulationWorker(job_id="test-789", db_path=db_path)

    # Mock job_manager to return empty completed dates
    mock_job_manager = Mock()
    mock_job_manager.get_completed_model_dates.return_value = {}
    worker.job_manager = mock_job_manager

    available_dates = ["2025-10-01", "2025-10-02"]
    models = ["gpt-5"]

    result = worker._filter_completed_dates(available_dates, models)

    # All dates should be returned
    assert result == available_dates

def test_filter_completed_dates_some_completed(tmp_path):
    """Test filtering when some dates are completed."""
    db_path = str(tmp_path / "test.db")
    initialize_database(db_path)

    worker = SimulationWorker(job_id="test-abc", db_path=db_path)

    # Mock job_manager to return one completed date
    mock_job_manager = Mock()
    mock_job_manager.get_completed_model_dates.return_value = {
        "gpt-5": ["2025-10-01"]
    }
    worker.job_manager = mock_job_manager

    available_dates = ["2025-10-01", "2025-10-02", "2025-10-03"]
    models = ["gpt-5"]

    result = worker._filter_completed_dates(available_dates, models)

    # Should exclude completed date
    assert result == ["2025-10-02", "2025-10-03"]
```

**Step 2: Run tests to verify they fail**

Run: `../../venv/bin/python -m pytest tests/unit/test_simulation_worker.py::test_filter_completed_dates_all_new -v`

Expected: FAIL (AttributeError: no attribute '_filter_completed_dates')

**Step 3: Implement _filter_completed_dates method**

In `api/simulation_worker.py`, add method after `_download_price_data`:

```python
def _filter_completed_dates(
    self,
    available_dates: List[str],
    models: List[str]
) -> List[str]:
    """
    Filter out dates that are already completed for all models.

    Implements idempotent job behavior - skip model-days that already
    have completed data.

    Args:
        available_dates: List of dates with complete price data
        models: List of model signatures

    Returns:
        List of dates that need processing
    """
    if not available_dates:
        return []

    # Get completed dates from job_manager
    start_date = available_dates[0]
    end_date = available_dates[-1]

    completed_dates = self.job_manager.get_completed_model_dates(
        models,
        start_date,
        end_date
    )

    # Build list of dates that need processing
    dates_to_process = []
    for date in available_dates:
        # Check if any model needs this date
        needs_processing = False
        for model in models:
            if date not in completed_dates.get(model, []):
                needs_processing = True
                break

        if needs_processing:
            dates_to_process.append(date)

    return dates_to_process
```

**Step 4: Run tests to verify they pass**

Run: `../../venv/bin/python -m pytest tests/unit/test_simulation_worker.py::test_filter_completed_dates_all_new tests/unit/test_simulation_worker.py::test_filter_completed_dates_some_completed -v`

Expected: PASS

**Step 5: Commit _filter_completed_dates**

```bash
git add api/simulation_worker.py tests/unit/test_simulation_worker.py
git commit -m "feat(worker): add _filter_completed_dates helper method

Implement idempotent behavior by skipping already-completed model-days.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

**Step 4.3: Add _add_job_warnings helper**

**Step 1: Write failing test**

Add to `tests/unit/test_simulation_worker.py`:

```python
def test_add_job_warnings(tmp_path):
    """Test adding warnings to job via worker."""
    db_path = str(tmp_path / "test.db")
    initialize_database(db_path)
    job_manager = JobManager(db_path=db_path)

    # Create job
    job_id = job_manager.create_job(
        config_path="config.json",
        date_range=["2025-10-01"],
        models=["gpt-5"]
    )

    worker = SimulationWorker(job_id=job_id, db_path=db_path)

    # Add warnings
    warnings = ["Warning 1", "Warning 2"]
    worker._add_job_warnings(warnings)

    # Verify warnings were stored
    import json
    job = job_manager.get_job(job_id)
    assert job["warnings"] is not None
    stored_warnings = json.loads(job["warnings"])
    assert stored_warnings == warnings
```

**Step 2: Run test to verify it fails**

Run: `../../venv/bin/python -m pytest tests/unit/test_simulation_worker.py::test_add_job_warnings -v`

Expected: FAIL (AttributeError: no attribute '_add_job_warnings')

**Step 3: Implement _add_job_warnings method**

In `api/simulation_worker.py`, add method after `_filter_completed_dates`:

```python
def _add_job_warnings(self, warnings: List[str]) -> None:
    """Store warnings in job metadata."""
    self.job_manager.add_job_warnings(self.job_id, warnings)
```

**Step 4: Run test to verify it passes**

Run: `../../venv/bin/python -m pytest tests/unit/test_simulation_worker.py::test_add_job_warnings -v`

Expected: PASS

**Step 5: Commit _add_job_warnings**

```bash
git add api/simulation_worker.py tests/unit/test_simulation_worker.py
git commit -m "feat(worker): add _add_job_warnings helper method

Delegate to JobManager.add_job_warnings for storing warnings.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 5: Implement SimulationWorker._prepare_data

**Files:**
- Modify: `api/simulation_worker.py`
- Test: `tests/unit/test_simulation_worker.py`

**Step 1: Write failing test for _prepare_data**

Add to `tests/unit/test_simulation_worker.py`:

```python
def test_prepare_data_no_missing_data(tmp_path, monkeypatch):
    """Test prepare_data when all data is available."""
    db_path = str(tmp_path / "test.db")
    initialize_database(db_path)
    job_manager = JobManager(db_path=db_path)

    # Create job
    job_id = job_manager.create_job(
        config_path="config.json",
        date_range=["2025-10-01"],
        models=["gpt-5"]
    )

    worker = SimulationWorker(job_id=job_id, db_path=db_path)

    # Mock PriceDataManager
    mock_price_manager = Mock()
    mock_price_manager.get_missing_coverage.return_value = {}  # No missing data
    mock_price_manager.get_available_trading_dates.return_value = ["2025-10-01"]

    # Patch PriceDataManager import
    def mock_pdm_init(db_path):
        return mock_price_manager

    monkeypatch.setattr("api.simulation_worker.PriceDataManager", mock_pdm_init)

    # Mock get_completed_model_dates
    worker.job_manager.get_completed_model_dates = Mock(return_value={})

    # Execute
    available_dates, warnings = worker._prepare_data(
        requested_dates=["2025-10-01"],
        models=["gpt-5"],
        config_path="config.json"
    )

    # Verify results
    assert available_dates == ["2025-10-01"]
    assert len(warnings) == 0

    # Verify status was updated to running
    job = job_manager.get_job(job_id)
    assert job["status"] == "running"

def test_prepare_data_with_download(tmp_path, monkeypatch):
    """Test prepare_data when data needs downloading."""
    db_path = str(tmp_path / "test.db")
    initialize_database(db_path)
    job_manager = JobManager(db_path=db_path)

    job_id = job_manager.create_job(
        config_path="config.json",
        date_range=["2025-10-01"],
        models=["gpt-5"]
    )

    worker = SimulationWorker(job_id=job_id, db_path=db_path)

    # Mock PriceDataManager
    mock_price_manager = Mock()
    mock_price_manager.get_missing_coverage.return_value = {"AAPL": {"2025-10-01"}}
    mock_price_manager.download_missing_data_prioritized.return_value = {
        "downloaded": ["AAPL"],
        "failed": [],
        "rate_limited": False
    }
    mock_price_manager.get_available_trading_dates.return_value = ["2025-10-01"]

    def mock_pdm_init(db_path):
        return mock_price_manager

    monkeypatch.setattr("api.simulation_worker.PriceDataManager", mock_pdm_init)
    worker.job_manager.get_completed_model_dates = Mock(return_value={})

    # Execute
    available_dates, warnings = worker._prepare_data(
        requested_dates=["2025-10-01"],
        models=["gpt-5"],
        config_path="config.json"
    )

    # Verify download was called
    mock_price_manager.download_missing_data_prioritized.assert_called_once()

    # Verify status transitions
    job = job_manager.get_job(job_id)
    assert job["status"] == "running"
```

**Step 2: Run tests to verify they fail**

Run: `../../venv/bin/python -m pytest tests/unit/test_simulation_worker.py::test_prepare_data_no_missing_data -v`

Expected: FAIL (AttributeError: no attribute '_prepare_data')

**Step 3: Implement _prepare_data method**

In `api/simulation_worker.py`, add method after `_add_job_warnings`, before `get_job_info`:

```python
def _prepare_data(
    self,
    requested_dates: List[str],
    models: List[str],
    config_path: str
) -> tuple:
    """
    Prepare price data for simulation.

    Steps:
    1. Update job status to "downloading_data"
    2. Check what data is missing
    3. Download missing data (with rate limit handling)
    4. Determine available trading dates
    5. Filter out already-completed model-days (idempotent)
    6. Update job status to "running"

    Args:
        requested_dates: All dates requested for simulation
        models: Model signatures to simulate
        config_path: Path to configuration file

    Returns:
        Tuple of (available_dates, warnings)
    """
    from api.price_data_manager import PriceDataManager

    warnings = []

    # Update status
    self.job_manager.update_job_status(self.job_id, "downloading_data")
    logger.info(f"Job {self.job_id}: Checking price data availability...")

    # Initialize price manager
    price_manager = PriceDataManager(db_path=self.db_path)

    # Check missing coverage
    start_date = requested_dates[0]
    end_date = requested_dates[-1]
    missing_coverage = price_manager.get_missing_coverage(start_date, end_date)

    # Download if needed
    if missing_coverage:
        logger.info(f"Job {self.job_id}: Missing data for {len(missing_coverage)} symbols")
        self._download_price_data(price_manager, missing_coverage, requested_dates, warnings)
    else:
        logger.info(f"Job {self.job_id}: All price data available")

    # Get available dates after download
    available_dates = price_manager.get_available_trading_dates(start_date, end_date)

    # Warn about skipped dates
    skipped = set(requested_dates) - set(available_dates)
    if skipped:
        warnings.append(f"Skipped {len(skipped)} dates due to incomplete price data: {sorted(list(skipped))}")
        logger.warning(f"Job {self.job_id}: {warnings[-1]}")

    # Filter already-completed model-days (idempotent behavior)
    available_dates = self._filter_completed_dates(available_dates, models)

    # Update to running
    self.job_manager.update_job_status(self.job_id, "running")
    logger.info(f"Job {self.job_id}: Starting execution - {len(available_dates)} dates, {len(models)} models")

    return available_dates, warnings
```

**Step 4: Run tests to verify they pass**

Run: `../../venv/bin/python -m pytest tests/unit/test_simulation_worker.py::test_prepare_data_no_missing_data tests/unit/test_simulation_worker.py::test_prepare_data_with_download -v`

Expected: PASS

**Step 5: Commit _prepare_data**

```bash
git add api/simulation_worker.py tests/unit/test_simulation_worker.py
git commit -m "feat(worker): add _prepare_data method

Orchestrate data preparation phase:
- Check missing data
- Download if needed
- Filter completed dates
- Update job status

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 6: Integrate _prepare_data into SimulationWorker.run()

**Files:**
- Modify: `api/simulation_worker.py:59-133`
- Test: `tests/integration/test_async_download.py`

**Step 1: Write integration test for async download flow**

Create `tests/integration/test_async_download.py`:

```python
import pytest
import time
from api.database import initialize_database
from api.job_manager import JobManager
from api.simulation_worker import SimulationWorker
from unittest.mock import Mock, patch

def test_worker_prepares_data_before_execution(tmp_path):
    """Test that worker calls _prepare_data before executing trades."""
    db_path = str(tmp_path / "test.db")
    initialize_database(db_path)
    job_manager = JobManager(db_path=db_path)

    # Create job
    job_id = job_manager.create_job(
        config_path="configs/default_config.json",
        date_range=["2025-10-01"],
        models=["gpt-5"]
    )

    worker = SimulationWorker(job_id=job_id, db_path=db_path)

    # Mock _prepare_data to track call
    original_prepare = worker._prepare_data
    prepare_called = []

    def mock_prepare(*args, **kwargs):
        prepare_called.append(True)
        return (["2025-10-01"], [])  # Return available dates, no warnings

    worker._prepare_data = mock_prepare

    # Mock _execute_date to avoid actual execution
    worker._execute_date = Mock()

    # Run worker
    result = worker.run()

    # Verify _prepare_data was called
    assert len(prepare_called) == 1
    assert result["success"] is True

def test_worker_handles_no_available_dates(tmp_path):
    """Test worker fails gracefully when no dates are available."""
    db_path = str(tmp_path / "test.db")
    initialize_database(db_path)
    job_manager = JobManager(db_path=db_path)

    job_id = job_manager.create_job(
        config_path="configs/default_config.json",
        date_range=["2025-10-01"],
        models=["gpt-5"]
    )

    worker = SimulationWorker(job_id=job_id, db_path=db_path)

    # Mock _prepare_data to return empty dates
    worker._prepare_data = Mock(return_value=([], []))

    # Run worker
    result = worker.run()

    # Should fail with descriptive error
    assert result["success"] is False
    assert "No trading dates available" in result["error"]

    # Job should be marked as failed
    job = job_manager.get_job(job_id)
    assert job["status"] == "failed"

def test_worker_stores_warnings(tmp_path):
    """Test worker stores warnings from prepare_data."""
    db_path = str(tmp_path / "test.db")
    initialize_database(db_path)
    job_manager = JobManager(db_path=db_path)

    job_id = job_manager.create_job(
        config_path="configs/default_config.json",
        date_range=["2025-10-01"],
        models=["gpt-5"]
    )

    worker = SimulationWorker(job_id=job_id, db_path=db_path)

    # Mock _prepare_data to return warnings
    warnings = ["Rate limited", "Skipped 1 date"]
    worker._prepare_data = Mock(return_value=(["2025-10-01"], warnings))
    worker._execute_date = Mock()

    # Run worker
    result = worker.run()

    # Verify warnings in result
    assert result["warnings"] == warnings

    # Verify warnings stored in database
    import json
    job = job_manager.get_job(job_id)
    stored_warnings = json.loads(job["warnings"])
    assert stored_warnings == warnings
```

**Step 2: Run tests to verify they fail**

Run: `../../venv/bin/python -m pytest tests/integration/test_async_download.py::test_worker_prepares_data_before_execution -v`

Expected: FAIL (run() doesn't call _prepare_data)

**Step 3: Modify SimulationWorker.run() to call _prepare_data**

In `api/simulation_worker.py`, modify the `run()` method (around line 59):

```python
def run(self) -> Dict[str, Any]:
    """
    Execute the simulation job.

    Returns:
        Result dict with success status and summary

    Process:
        1. Get job details (dates, models, config)
        2. Prepare data (download if needed)
        3. For each date sequentially:
            a. Execute all models in parallel
            b. Wait for all to complete
            c. Update progress
        4. Determine final job status
        5. Store warnings if any

    Error Handling:
        - Individual model failures: Mark detail as failed, continue with others
        - Job-level errors: Mark entire job as failed
    """
    try:
        # Get job info
        job = self.job_manager.get_job(self.job_id)
        if not job:
            raise ValueError(f"Job {self.job_id} not found")

        date_range = job["date_range"]
        models = job["models"]
        config_path = job["config_path"]

        logger.info(f"Starting job {self.job_id}: {len(date_range)} dates, {len(models)} models")

        # NEW: Prepare price data (download if needed)
        available_dates, warnings = self._prepare_data(date_range, models, config_path)

        if not available_dates:
            error_msg = "No trading dates available after price data preparation"
            self.job_manager.update_job_status(self.job_id, "failed", error=error_msg)
            return {"success": False, "error": error_msg}

        # Execute available dates only
        for date in available_dates:
            logger.info(f"Processing date {date} with {len(models)} models")
            self._execute_date(date, models, config_path)

        # Job completed - determine final status
        progress = self.job_manager.get_job_progress(self.job_id)

        if progress["failed"] == 0:
            final_status = "completed"
        elif progress["completed"] > 0:
            final_status = "partial"
        else:
            final_status = "failed"

        # Add warnings if any dates were skipped
        if warnings:
            self._add_job_warnings(warnings)

        # Note: Job status is already updated by model_day_executor's detail status updates
        # We don't need to explicitly call update_job_status here as it's handled automatically
        # by the status transition logic in JobManager.update_job_detail_status

        logger.info(f"Job {self.job_id} finished with status: {final_status}")

        return {
            "success": True,
            "job_id": self.job_id,
            "status": final_status,
            "total_model_days": progress["total_model_days"],
            "completed": progress["completed"],
            "failed": progress["failed"],
            "warnings": warnings
        }

    except Exception as e:
        error_msg = f"Job execution failed: {str(e)}"
        logger.error(f"Job {self.job_id}: {error_msg}", exc_info=True)

        # Update job to failed
        self.job_manager.update_job_status(self.job_id, "failed", error=error_msg)

        return {
            "success": False,
            "job_id": self.job_id,
            "error": error_msg
        }
```

**Step 4: Run tests to verify they pass**

Run: `../../venv/bin/python -m pytest tests/integration/test_async_download.py -v`

Expected: PASS

**Step 5: Commit worker run() integration**

```bash
git add api/simulation_worker.py tests/integration/test_async_download.py
git commit -m "feat(worker): integrate data preparation into run() method

Call _prepare_data before executing trades:
- Download missing data if needed
- Filter completed dates
- Store warnings
- Handle empty date scenarios

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 7: Simplify /simulate/trigger Endpoint

**Files:**
- Modify: `api/main.py:144-405`
- Test: `tests/integration/test_api_endpoints.py`

**Step 1: Write integration test for fast endpoint response**

Add to `tests/integration/test_api_endpoints.py`:

```python
import time

def test_trigger_endpoint_fast_response(test_client):
    """Test that /simulate/trigger responds quickly without downloading data."""
    start_time = time.time()

    response = test_client.post("/simulate/trigger", json={
        "start_date": "2025-10-01",
        "end_date": "2025-10-01",
        "models": ["gpt-5"]
    })

    elapsed = time.time() - start_time

    # Should respond in less than 2 seconds (allowing for DB operations)
    assert elapsed < 2.0
    assert response.status_code == 200
    assert "job_id" in response.json()

def test_trigger_endpoint_no_price_download(test_client, monkeypatch):
    """Test that endpoint doesn't call price download."""
    download_called = []

    # Patch PriceDataManager to track if download is called
    original_pdm = __import__('api.price_data_manager', fromlist=['PriceDataManager']).PriceDataManager

    class MockPDM:
        def __init__(self, *args, **kwargs):
            pass

        def download_missing_data_prioritized(self, *args, **kwargs):
            download_called.append(True)
            return {"downloaded": [], "failed": [], "rate_limited": False}

    monkeypatch.setattr("api.main.PriceDataManager", MockPDM)

    response = test_client.post("/simulate/trigger", json={
        "start_date": "2025-10-01",
        "end_date": "2025-10-01",
        "models": ["gpt-5"]
    })

    # Download should NOT be called in endpoint
    assert len(download_called) == 0
    assert response.status_code == 200
```

**Step 2: Run tests to verify they fail**

Run: `../../venv/bin/python -m pytest tests/integration/test_api_endpoints.py::test_trigger_endpoint_no_price_download -v`

Expected: FAIL (download is currently called in endpoint)

**Step 3: Remove price download logic from /simulate/trigger**

In `api/main.py`, modify `trigger_simulation` function (around line 144):

Find and remove these sections:
- Lines 228-273: Price data download logic
- Lines 276-287: Available dates check
- Lines 290-333: Idempotent filtering

Replace with simpler logic:

```python
@app.post("/simulate/trigger", response_model=SimulateTriggerResponse, status_code=200)
async def trigger_simulation(request: SimulateTriggerRequest):
    """
    Trigger a new simulation job.

    Validates date range and creates job. Price data is downloaded
    in background by SimulationWorker.

    Supports:
    - Single date: start_date == end_date
    - Date range: start_date < end_date
    - Resume: start_date is null (each model resumes from its last completed date)

    Raises:
        HTTPException 400: Validation errors, running job, or invalid dates
    """
    try:
        # Use config path from app state
        config_path = app.state.config_path

        # Validate config path exists
        if not Path(config_path).exists():
            raise HTTPException(
                status_code=500,
                detail=f"Server configuration file not found: {config_path}"
            )

        end_date = request.end_date

        # Determine which models to run
        import json
        with open(config_path, 'r') as f:
            config = json.load(f)

        if request.models is not None:
            # Use models from request (explicit override)
            models_to_run = request.models
        else:
            # Use enabled models from config
            models_to_run = [
                model["signature"]
                for model in config.get("models", [])
                if model.get("enabled", False)
            ]

            if not models_to_run:
                raise HTTPException(
                    status_code=400,
                    detail="No enabled models found in config. Either enable models in config or specify them in request."
                )

        job_manager = JobManager(db_path=app.state.db_path)

        # Handle resume logic (start_date is null)
        if request.start_date is None:
            # Resume mode: determine start date per model
            from datetime import timedelta
            model_start_dates = {}

            for model in models_to_run:
                last_date = job_manager.get_last_completed_date_for_model(model)

                if last_date is None:
                    # Cold start: use end_date as single-day simulation
                    model_start_dates[model] = end_date
                else:
                    # Resume from next day after last completed
                    last_dt = datetime.strptime(last_date, "%Y-%m-%d")
                    next_dt = last_dt + timedelta(days=1)
                    model_start_dates[model] = next_dt.strftime("%Y-%m-%d")

            # For validation purposes, use earliest start date
            earliest_start = min(model_start_dates.values())
            start_date = earliest_start
        else:
            # Explicit start date provided
            start_date = request.start_date
            model_start_dates = {model: start_date for model in models_to_run}

        # Validate date range
        max_days = get_max_simulation_days()
        validate_date_range(start_date, end_date, max_days=max_days)

        # Check if can start new job
        if not job_manager.can_start_new_job():
            raise HTTPException(
                status_code=400,
                detail="Another simulation job is already running or pending. Please wait for it to complete."
            )

        # Get all weekdays in range (worker will filter based on data availability)
        all_dates = expand_date_range(start_date, end_date)

        # Create job immediately with all requested dates
        # Worker will handle data download and filtering
        job_id = job_manager.create_job(
            config_path=config_path,
            date_range=all_dates,
            models=models_to_run,
            model_day_filter=None  # Worker will filter based on available data
        )

        # Start worker in background thread (only if not in test mode)
        if not getattr(app.state, "test_mode", False):
            def run_worker():
                worker = SimulationWorker(job_id=job_id, db_path=app.state.db_path)
                worker.run()

            thread = threading.Thread(target=run_worker, daemon=True)
            thread.start()

        logger.info(f"Triggered simulation job {job_id} for {len(all_dates)} dates, {len(models_to_run)} models")

        # Build response message
        message = f"Simulation job created for {len(all_dates)} dates, {len(models_to_run)} models"

        if request.start_date is None:
            message += " (resume mode)"

        # Get deployment mode info
        deployment_info = get_deployment_mode_dict()

        response = SimulateTriggerResponse(
            job_id=job_id,
            status="pending",
            total_model_days=len(all_dates) * len(models_to_run),
            message=message,
            **deployment_info
        )

        return response

    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to trigger simulation: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
```

**Step 4: Remove unused imports from api/main.py**

Remove these imports if no longer used:
- `from api.price_data_manager import PriceDataManager`
- `from api.date_utils import expand_date_range` (if only used in removed code)

Keep:
- `from api.date_utils import validate_date_range, expand_date_range, get_max_simulation_days`

**Step 5: Run tests to verify they pass**

Run: `../../venv/bin/python -m pytest tests/integration/test_api_endpoints.py::test_trigger_endpoint_fast_response tests/integration/test_api_endpoints.py::test_trigger_endpoint_no_price_download -v`

Expected: PASS

**Step 6: Commit endpoint simplification**

```bash
git add api/main.py tests/integration/test_api_endpoints.py
git commit -m "refactor(api): remove price download from /simulate/trigger

Move data preparation to background worker:
- Fast endpoint response (<1s)
- No blocking downloads
- Worker handles data download and filtering
- Maintains backwards compatibility

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 8: Update /simulate/status to Return Warnings

**Files:**
- Modify: `api/main.py:407-465`
- Test: `tests/integration/test_api_endpoints.py`

**Step 1: Write test for warnings in status response**

Add to `tests/integration/test_api_endpoints.py`:

```python
def test_status_endpoint_returns_warnings(test_client, tmp_path):
    """Test that /simulate/status returns warnings field."""
    # Create job with warnings
    db_path = str(tmp_path / "test.db")
    initialize_database(db_path)
    job_manager = JobManager(db_path=db_path)

    job_id = job_manager.create_job(
        config_path="config.json",
        date_range=["2025-10-01"],
        models=["gpt-5"]
    )

    # Add warnings
    warnings = ["Rate limited", "Skipped 1 date"]
    job_manager.add_job_warnings(job_id, warnings)

    # Mock app.state.db_path
    test_client.app.state.db_path = db_path

    # Get status
    response = test_client.get(f"/simulate/status/{job_id}")

    assert response.status_code == 200
    data = response.json()
    assert "warnings" in data
    assert data["warnings"] == warnings
```

**Step 2: Run test to verify it fails**

Run: `../../venv/bin/python -m pytest tests/integration/test_api_endpoints.py::test_status_endpoint_returns_warnings -v`

Expected: FAIL (warnings not in response or None)

**Step 3: Modify get_job_status to include warnings**

In `api/main.py`, modify `get_job_status` function (around line 407):

```python
@app.get("/simulate/status/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str):
    """
    Get status and progress of a simulation job.

    Args:
        job_id: Job UUID

    Returns:
        Job status, progress, model-day details, and warnings

    Raises:
        HTTPException 404: If job not found
    """
    try:
        job_manager = JobManager(db_path=app.state.db_path)

        # Get job info
        job = job_manager.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

        # Get progress
        progress = job_manager.get_job_progress(job_id)

        # Get model-day details
        details = job_manager.get_job_details(job_id)

        # Calculate pending (total - completed - failed)
        pending = progress["total_model_days"] - progress["completed"] - progress["failed"]

        # Parse warnings from JSON if present
        import json
        warnings = None
        if job.get("warnings"):
            try:
                warnings = json.loads(job["warnings"])
            except (json.JSONDecodeError, TypeError):
                logger.warning(f"Failed to parse warnings for job {job_id}")

        # Get deployment mode info
        deployment_info = get_deployment_mode_dict()

        return JobStatusResponse(
            job_id=job["job_id"],
            status=job["status"],
            progress=JobProgress(
                total_model_days=progress["total_model_days"],
                completed=progress["completed"],
                failed=progress["failed"],
                pending=pending
            ),
            date_range=job["date_range"],
            models=job["models"],
            created_at=job["created_at"],
            started_at=job.get("started_at"),
            completed_at=job.get("completed_at"),
            total_duration_seconds=job.get("total_duration_seconds"),
            error=job.get("error"),
            details=details,
            warnings=warnings,  # NEW
            **deployment_info
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get job status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
```

**Step 4: Run test to verify it passes**

Run: `../../venv/bin/python -m pytest tests/integration/test_api_endpoints.py::test_status_endpoint_returns_warnings -v`

Expected: PASS

**Step 5: Commit status endpoint update**

```bash
git add api/main.py tests/integration/test_api_endpoints.py
git commit -m "feat(api): return warnings in /simulate/status response

Parse and return job warnings from database.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 9: End-to-End Integration Test

**Files:**
- Create: `tests/e2e/test_async_download_flow.py`

**Step 1: Write end-to-end test**

Create `tests/e2e/test_async_download_flow.py`:

```python
"""
End-to-end test for async price download flow.

Tests the complete flow:
1. POST /simulate/trigger (fast response)
2. Worker downloads data in background
3. GET /simulate/status shows downloading_data → running → completed
4. Warnings are captured and returned
"""

import pytest
import time
from unittest.mock import patch, Mock
from api.main import create_app
from api.database import initialize_database
from fastapi.testclient import TestClient

@pytest.fixture
def test_app(tmp_path):
    """Create test app with isolated database."""
    db_path = str(tmp_path / "test.db")
    initialize_database(db_path)

    app = create_app(db_path=db_path, config_path="configs/default_config.json")
    app.state.test_mode = True  # Disable background worker

    yield app

@pytest.fixture
def test_client(test_app):
    """Create test client."""
    return TestClient(test_app)

def test_complete_async_download_flow(test_client, monkeypatch):
    """Test complete flow from trigger to completion with async download."""

    # Mock PriceDataManager for predictable behavior
    class MockPriceManager:
        def __init__(self, db_path):
            self.db_path = db_path

        def get_missing_coverage(self, start, end):
            return {"AAPL": {"2025-10-01"}}  # Simulate missing data

        def download_missing_data_prioritized(self, missing, requested):
            return {
                "downloaded": ["AAPL"],
                "failed": [],
                "rate_limited": False
            }

        def get_available_trading_dates(self, start, end):
            return ["2025-10-01"]

    monkeypatch.setattr("api.simulation_worker.PriceDataManager", MockPriceManager)

    # Mock execution to avoid actual trading
    def mock_execute_date(self, date, models, config_path):
        pass

    monkeypatch.setattr("api.simulation_worker.SimulationWorker._execute_date", mock_execute_date)

    # Step 1: Trigger simulation
    start_time = time.time()
    response = test_client.post("/simulate/trigger", json={
        "start_date": "2025-10-01",
        "end_date": "2025-10-01",
        "models": ["gpt-5"]
    })
    elapsed = time.time() - start_time

    # Should respond quickly
    assert elapsed < 2.0
    assert response.status_code == 200

    data = response.json()
    job_id = data["job_id"]
    assert data["status"] == "pending"

    # Step 2: Run worker manually (since test_mode=True)
    from api.simulation_worker import SimulationWorker
    worker = SimulationWorker(job_id=job_id, db_path=test_client.app.state.db_path)
    result = worker.run()

    # Step 3: Check final status
    status_response = test_client.get(f"/simulate/status/{job_id}")
    assert status_response.status_code == 200

    status_data = status_response.json()
    assert status_data["status"] == "completed"
    assert status_data["job_id"] == job_id

def test_flow_with_rate_limit_warning(test_client, monkeypatch):
    """Test flow when rate limit is hit during download."""

    class MockPriceManagerRateLimited:
        def __init__(self, db_path):
            self.db_path = db_path

        def get_missing_coverage(self, start, end):
            return {"AAPL": {"2025-10-01"}, "MSFT": {"2025-10-01"}}

        def download_missing_data_prioritized(self, missing, requested):
            return {
                "downloaded": ["AAPL"],
                "failed": ["MSFT"],
                "rate_limited": True
            }

        def get_available_trading_dates(self, start, end):
            return []  # No complete dates due to rate limit

    monkeypatch.setattr("api.simulation_worker.PriceDataManager", MockPriceManagerRateLimited)

    # Trigger
    response = test_client.post("/simulate/trigger", json={
        "start_date": "2025-10-01",
        "end_date": "2025-10-01",
        "models": ["gpt-5"]
    })

    job_id = response.json()["job_id"]

    # Run worker
    from api.simulation_worker import SimulationWorker
    worker = SimulationWorker(job_id=job_id, db_path=test_client.app.state.db_path)
    result = worker.run()

    # Should fail due to no available dates
    assert result["success"] is False

    # Check status has error
    status_response = test_client.get(f"/simulate/status/{job_id}")
    status_data = status_response.json()
    assert status_data["status"] == "failed"
    assert "No trading dates available" in status_data["error"]

def test_flow_with_partial_data(test_client, monkeypatch):
    """Test flow when some dates are skipped due to incomplete data."""

    class MockPriceManagerPartial:
        def __init__(self, db_path):
            self.db_path = db_path

        def get_missing_coverage(self, start, end):
            return {}  # No missing data

        def get_available_trading_dates(self, start, end):
            # Only 2 out of 3 dates available
            return ["2025-10-01", "2025-10-03"]

    monkeypatch.setattr("api.simulation_worker.PriceDataManager", MockPriceManagerPartial)

    def mock_execute_date(self, date, models, config_path):
        pass

    monkeypatch.setattr("api.simulation_worker.SimulationWorker._execute_date", mock_execute_date)

    # Trigger with 3 dates
    response = test_client.post("/simulate/trigger", json={
        "start_date": "2025-10-01",
        "end_date": "2025-10-03",
        "models": ["gpt-5"]
    })

    job_id = response.json()["job_id"]

    # Run worker
    from api.simulation_worker import SimulationWorker
    worker = SimulationWorker(job_id=job_id, db_path=test_client.app.state.db_path)
    result = worker.run()

    # Should complete with warnings
    assert result["success"] is True
    assert len(result["warnings"]) > 0
    assert "Skipped" in result["warnings"][0]

    # Check status returns warnings
    status_response = test_client.get(f"/simulate/status/{job_id}")
    status_data = status_response.json()
    assert status_data["status"] == "completed"
    assert status_data["warnings"] is not None
    assert len(status_data["warnings"]) > 0
```

**Step 2: Run e2e test**

Run: `../../venv/bin/python -m pytest tests/e2e/test_async_download_flow.py -v`

Expected: PASS (all scenarios work end-to-end)

**Step 3: Commit e2e tests**

```bash
git add tests/e2e/test_async_download_flow.py
git commit -m "test: add end-to-end tests for async download flow

Test complete flow:
- Fast API response
- Background data download
- Status transitions
- Warning capture and display

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 10: Update API Documentation

**Files:**
- Modify: `API_REFERENCE.md`
- Modify: `docs/user-guide/using-the-api.md`

**Step 1: Update API_REFERENCE.md with new status**

In `API_REFERENCE.md`, find the job status documentation and update:

```markdown
### Job Status Values

- `pending`: Job created, waiting to start
- `downloading_data`: Preparing price data (downloading if needed)  ← NEW
- `running`: Executing trading simulations
- `completed`: All model-days completed successfully
- `partial`: Some model-days completed, some failed
- `failed`: Job failed to execute

### Response Fields (New)

#### warnings

Optional array of warning messages:
- Rate limit reached during data download
- Dates skipped due to incomplete price data
- Other non-fatal issues

Example:
```json
{
  "job_id": "019a426b...",
  "status": "completed",
  "warnings": [
    "Rate limit reached - downloaded 12/15 symbols",
    "Skipped 2 dates due to incomplete price data: ['2025-10-02', '2025-10-05']"
  ]
}
```
```

**Step 2: Update using-the-api.md with async behavior**

In `docs/user-guide/using-the-api.md`, add section:

```markdown
## Async Data Download

The `/simulate/trigger` endpoint responds immediately (<1 second), even when price data needs to be downloaded.

### Flow

1. **POST /simulate/trigger** - Returns `job_id` immediately
2. **Background worker** - Downloads missing data automatically
3. **Poll /simulate/status** - Track progress through status transitions

### Status Progression

```
pending → downloading_data → running → completed
```

### Monitoring Progress

Use `docker logs -f` to monitor download progress in real-time:

```bash
docker logs -f ai-trader-server

# Example output:
# Job 019a426b: Checking price data availability...
# Job 019a426b: Missing data for 15 symbols
# Job 019a426b: Starting prioritized download...
# Job 019a426b: Download complete - 12/15 symbols succeeded
# Job 019a426b: Rate limit reached - proceeding with available dates
# Job 019a426b: Starting execution - 8 dates, 1 models
```

### Handling Warnings

Check the `warnings` field in status response:

```python
import requests
import time

# Trigger simulation
response = requests.post("http://localhost:8080/simulate/trigger", json={
    "start_date": "2025-10-01",
    "end_date": "2025-10-10",
    "models": ["gpt-5"]
})

job_id = response.json()["job_id"]

# Poll until complete
while True:
    status = requests.get(f"http://localhost:8080/simulate/status/{job_id}").json()

    if status["status"] in ["completed", "partial", "failed"]:
        # Check for warnings
        if status.get("warnings"):
            print("Warnings:", status["warnings"])
        break

    time.sleep(2)
```
```

**Step 3: Commit documentation updates**

```bash
git add API_REFERENCE.md docs/user-guide/using-the-api.md
git commit -m "docs: update API docs for async download behavior

Document:
- New downloading_data status
- Warnings field in responses
- Async flow and monitoring
- Example usage patterns

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 11: Run Full Test Suite

**Files:**
- None (verification only)

**Step 1: Run all unit tests**

Run: `../../venv/bin/python -m pytest tests/unit/ -v`

Expected: All tests PASS

**Step 2: Run all integration tests**

Run: `../../venv/bin/python -m pytest tests/integration/ -v`

Expected: All tests PASS

**Step 3: Run e2e tests**

Run: `../../venv/bin/python -m pytest tests/e2e/ -v`

Expected: All tests PASS

**Step 4: If any tests fail, fix them**

Review failures and fix. Commit fixes:

```bash
git add <fixed-files>
git commit -m "fix: address test failures

<describe fixes>

Co-Authored-By: Claude <noreply@anthropic.com>"
```

**Step 5: Final verification - run complete suite**

Run: `../../venv/bin/python -m pytest tests/ -v --tb=short`

Expected: All tests PASS

---

## Completion

**All tasks complete!**

The async price download feature is now fully implemented:

✅ Database schema supports `downloading_data` status and warnings
✅ SimulationWorker prepares data before execution
✅ API endpoint responds quickly without blocking
✅ Warnings are captured and displayed
✅ End-to-end tests validate complete flow
✅ Documentation updated

**Next Steps:**

Use `superpowers:finishing-a-development-branch` to:
1. Review all changes
2. Create pull request or merge to main
3. Clean up worktree
