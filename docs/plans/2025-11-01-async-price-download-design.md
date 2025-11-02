# Async Price Data Download Design

**Date:** 2025-11-01
**Status:** Approved
**Problem:** `/simulate/trigger` endpoint times out (30s+) when downloading missing price data

## Problem Statement

The `/simulate/trigger` API endpoint currently downloads missing price data synchronously within the HTTP request handler. This causes:
- HTTP timeouts when downloads take >30 seconds
- Poor user experience (long wait for job_id)
- Blocking behavior that doesn't match async job pattern

## Solution Overview

Move price data download from the HTTP endpoint to the background worker thread, enabling:
- Fast API response (<1 second)
- Background data preparation with progress visibility
- Graceful handling of rate limits and partial downloads

## Architecture Changes

### Current Flow
```
POST /simulate/trigger → Download price data (30s+) → Create job → Return job_id
```

### New Flow
```
POST /simulate/trigger → Quick validation → Create job → Return job_id (<1s)
                                                ↓
Background worker → Download missing data → Execute trading → Complete
```

### Status Progression
```
pending → downloading_data → running → completed (with optional warnings)
                          ↓
                       failed (if download fails completely)
```

## Component Changes

### 1. API Endpoint (`api/main.py`)

**Remove:**
- Price data availability checks (lines 228-287)
- `PriceDataManager.get_missing_coverage()`
- `PriceDataManager.download_missing_data_prioritized()`
- `PriceDataManager.get_available_trading_dates()`
- Idempotent filtering logic (move to worker)

**Keep:**
- Date format validation
- Job creation
- Worker thread startup

**New Logic:**
```python
# Quick validation only
validate_date_range(start_date, end_date, max_days=max_days)

# Check if can start new job
if not job_manager.can_start_new_job():
    raise HTTPException(status_code=400, detail="...")

# Create job immediately with all requested dates
job_id = job_manager.create_job(
    config_path=config_path,
    date_range=expand_date_range(start_date, end_date),  # All weekdays
    models=models_to_run,
    model_day_filter=None  # Worker will filter
)

# Start worker thread (existing code)
```

### 2. Simulation Worker (`api/simulation_worker.py`)

**New Method: `_prepare_data()`**

Encapsulates data preparation phase:

```python
def _prepare_data(
    self,
    requested_dates: List[str],
    models: List[str],
    config_path: str
) -> Tuple[List[str], List[str]]:
    """
    Prepare price data for simulation.

    Steps:
    1. Update job status to "downloading_data"
    2. Check what data is missing
    3. Download missing data (with rate limit handling)
    4. Determine available trading dates
    5. Filter out already-completed model-days (idempotent)
    6. Update job status to "running"

    Returns:
        (available_dates, warnings)
    """
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
        warnings.append(f"Skipped {len(skipped)} dates due to incomplete price data: {sorted(skipped)}")
        logger.warning(f"Job {self.job_id}: {warnings[-1]}")

    # Filter already-completed model-days (idempotent behavior)
    available_dates = self._filter_completed_dates(available_dates, models)

    # Update to running
    self.job_manager.update_job_status(self.job_id, "running")
    logger.info(f"Job {self.job_id}: Starting execution - {len(available_dates)} dates, {len(models)} models")

    return available_dates, warnings
```

**New Method: `_download_price_data()`**

Handles download with progress logging:

```python
def _download_price_data(
    self,
    price_manager: PriceDataManager,
    missing_coverage: Dict[str, Set[str]],
    requested_dates: List[str],
    warnings: List[str]
) -> None:
    """Download missing price data with progress logging."""

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

**New Method: `_filter_completed_dates()`**

Implements idempotent behavior:

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
    """
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

**New Method: `_add_job_warnings()`**

Store warnings in job metadata:

```python
def _add_job_warnings(self, warnings: List[str]) -> None:
    """Store warnings in job metadata."""
    self.job_manager.add_job_warnings(self.job_id, warnings)
```

**Modified: `run()` method**

```python
def run(self) -> Dict[str, Any]:
    try:
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

        # Determine final status
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
        self.job_manager.update_job_status(self.job_id, "failed", error=error_msg)
        return {"success": False, "job_id": self.job_id, "error": error_msg}
```

### 3. Job Manager (`api/job_manager.py`)

**Verify Status Support:**
- Ensure "downloading_data" status is allowed in database schema
- Verify status transition logic supports: `pending → downloading_data → running`

**New Method: `add_job_warnings()`**

```python
def add_job_warnings(self, job_id: str, warnings: List[str]) -> None:
    """
    Store warnings for a job.

    Implementation options:
    1. Add 'warnings' JSON column to jobs table
    2. Store in existing metadata field
    3. Create separate warnings table
    """
    # To be implemented based on schema preference
    pass
```

### 4. Response Models (`api/main.py`)

**Add warnings field:**

```python
class SimulateTriggerResponse(BaseModel):
    job_id: str
    status: str
    total_model_days: int
    message: str
    deployment_mode: str
    is_dev_mode: bool
    preserve_dev_data: Optional[bool] = None
    warnings: Optional[List[str]] = None  # NEW

class JobStatusResponse(BaseModel):
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

## Logging Strategy

### Progress Visibility

Enhanced logging for monitoring via `docker logs -f`:

```python
# At download start
logger.info(f"Job {job_id}: Checking price data availability...")
logger.info(f"Job {job_id}: Missing data for {len(missing_symbols)} symbols")
logger.info(f"Job {job_id}: Starting prioritized download...")

# Download completion
logger.info(f"Job {job_id}: Download complete - {downloaded}/{total} symbols succeeded")
logger.warning(f"Job {job_id}: Rate limited - proceeding with available dates")

# Execution start
logger.info(f"Job {job_id}: Starting execution - {len(dates)} dates, {len(models)} models")
logger.info(f"Job {job_id}: Processing date {date} with {len(models)} models")
```

### DEV Mode Enhancement

```python
if DEPLOYMENT_MODE == "DEV":
    logger.setLevel(logging.DEBUG)
    logger.info("🔧 DEV MODE: Enhanced logging enabled")
```

### Example Console Output

```
Job 019a426b: Checking price data availability...
Job 019a426b: Missing data for 15 symbols
Job 019a426b: Starting prioritized download...
Job 019a426b: Download complete - 12/15 symbols succeeded
Job 019a426b: Rate limit reached - downloaded 12/15 symbols
Job 019a426b: Skipped 2 dates due to incomplete price data: ['2025-10-02', '2025-10-05']
Job 019a426b: Starting execution - 8 dates, 1 models
Job 019a426b: Processing date 2025-10-01 with 1 models
Job 019a426b: Processing date 2025-10-03 with 1 models
...
Job 019a426b: Job finished with status: completed
```

## Behavior Specifications

### Rate Limit Handling

**Option B (Approved):** Run with available data
- Download symbols in priority order (most date-completing first)
- When rate limited, proceed with dates that have complete data
- Add warning to job response
- Mark job as "completed" (not "failed") if any dates processed
- Log skipped dates for visibility

### Job Status Communication

**Option B (Approved):** Status "completed" with warnings
- Status = "completed" means "successfully processed all processable dates"
- Warnings field communicates skipped dates
- Consistent with existing skip-incomplete-data behavior
- Doesn't penalize users for rate limits

### Progress Visibility

**Option A (Approved):** Job status field
- New status: "downloading_data"
- Appears in `/simulate/status/{job_id}` responses
- Clear distinction between phases:
  - `pending`: Job queued, not started
  - `downloading_data`: Preparing price data
  - `running`: Executing trades
  - `completed`: Finished successfully
  - `partial`: Some model-days failed
  - `failed`: Job-level failure

## Testing Strategy

### Test Cases

1. **Fast path** - All data present
   - Request simulation with existing data
   - Expect <1s response with job_id
   - Verify status goes: pending → running → completed

2. **Download path** - Missing data
   - Request simulation with missing price data
   - Expect <1s response with job_id
   - Verify status goes: pending → downloading_data → running → completed
   - Check `docker logs -f` shows download progress

3. **Rate limit handling**
   - Trigger rate limit during download
   - Verify job completes with warnings
   - Verify partial dates processed
   - Verify status = "completed" (not "failed")

4. **Complete failure**
   - Simulate download failure (invalid API key)
   - Verify job status = "failed"
   - Verify error message in response

5. **Idempotent behavior**
   - Request same date range twice
   - Verify second request skips completed model-days
   - Verify no duplicate executions

### Integration Test Example

```python
def test_async_download_with_missing_data():
    """Test that missing data is downloaded in background."""
    # Trigger simulation
    response = requests.post("http://localhost:8080/simulate/trigger", json={
        "start_date": "2025-10-01",
        "end_date": "2025-10-01",
        "models": ["gpt-5"]
    })

    # Should return immediately
    assert response.elapsed.total_seconds() < 2
    assert response.status_code == 200

    job_id = response.json()["job_id"]

    # Poll status - should see downloading_data
    status = requests.get(f"http://localhost:8080/simulate/status/{job_id}").json()
    assert status["status"] in ["pending", "downloading_data", "running"]

    # Wait for completion
    while status["status"] not in ["completed", "partial", "failed"]:
        time.sleep(1)
        status = requests.get(f"http://localhost:8080/simulate/status/{job_id}").json()

    # Verify success
    assert status["status"] == "completed"
```

## Migration & Rollout

### Implementation Order

1. **Database changes** - Add warnings support to job schema
2. **Worker changes** - Implement `_prepare_data()` and helpers
3. **Endpoint changes** - Remove blocking download logic
4. **Response models** - Add warnings field
5. **Testing** - Integration tests for all scenarios
6. **Documentation** - Update API docs

### Backwards Compatibility

- No breaking changes to API contract
- New `warnings` field is optional
- Existing clients continue to work unchanged
- Response time improves (better UX)

### Rollback Plan

If issues arise:
1. Revert endpoint changes (restore price download)
2. Keep worker changes (no harm if unused)
3. Response models are backwards compatible

## Benefits Summary

1. **Performance**: API response <1s (vs 30s+ timeout)
2. **UX**: Immediate job_id, async progress tracking
3. **Reliability**: No HTTP timeouts
4. **Visibility**: Real-time logs via `docker logs -f`
5. **Resilience**: Graceful rate limit handling
6. **Consistency**: Matches async job pattern
7. **Maintainability**: Cleaner separation of concerns

## Open Questions

None - design approved.
