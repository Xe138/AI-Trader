# Job Skip Status Tracking Design

**Date:** 2025-11-02
**Status:** Approved for implementation

## Problem Statement

The job orchestration system has three related issues when handling date filtering:

1. **Incorrect status reporting** - Dates that are skipped (already completed or missing price data) remain in "pending" status instead of showing their actual state
2. **Jobs hang indefinitely** - Jobs never complete because the completion check only counts "completed" and "failed" statuses, ignoring dates that were intentionally skipped
3. **Unclear skip reasons** - Warning messages don't distinguish between different types of skips (weekends vs already-completed vs rate limits)

### Example of Broken Behavior

Job request: dates [2025-10-01 to 2025-10-05], model [gpt-5]

Current (broken) response:
```json
{
    "status": "running",  // STUCK - never completes
    "progress": {
        "pending": 3,     // WRONG - these will never be executed
        "completed": 2,
        "failed": 0
    },
    "details": [
        {"date": "2025-10-01", "status": "pending"},  // Already completed
        {"date": "2025-10-02", "status": "completed"},
        {"date": "2025-10-03", "status": "completed"},
        {"date": "2025-10-04", "status": "pending"},  // Weekend (no data)
        {"date": "2025-10-05", "status": "pending"}   // Weekend (no data)
    ]
}
```

## Solution Overview

Add "skipped" status to track dates that were intentionally not executed. Update job completion logic to count skipped dates as "done" since they don't require execution.

### Core Principles

1. **Status accuracy** - Every job_details entry reflects what actually happened
2. **Proper completion** - Jobs complete when all dates are in terminal states (completed/failed/skipped)
3. **Clear attribution** - Skip reasons stored in error field explain why each date was skipped
4. **Per-model granularity** - Multi-model jobs correctly handle different completion states per model

## Design Details

### 1. Database Schema Changes

**Current constraint:**
```sql
status TEXT NOT NULL CHECK(status IN ('pending', 'running', 'completed', 'failed'))
```

**New constraint:**
```sql
status TEXT NOT NULL CHECK(status IN ('pending', 'running', 'completed', 'failed', 'skipped'))
```

**Migration strategy:**
- Dev mode: Table recreated on startup (already happens with `PRESERVE_DEV_DATA=false`)
- Production: Provide manual migration SQL script

**No new columns needed:**
- Skip reasons stored in existing `error` field
- Field semantics: "error message for failures, skip reason for skips"

### 2. Skip Reason Categories

Three skip reasons stored in the `error` field:

| Reason | Description | When Applied |
|--------|-------------|--------------|
| "Already completed" | Position data exists from previous job | Per-model, based on job_details history |
| "Incomplete price data" | Missing stock prices for date | All models, for weekends/holidays/future dates |
| "Rate limited during download" | API rate limit hit during download | All models (optional, may merge with incomplete data) |

### 3. SimulationWorker Changes

#### Modified `_prepare_data()` Flow

**Current:**
```python
available_dates = price_manager.get_available_trading_dates(start, end)
available_dates = self._filter_completed_dates(available_dates, models)
# Skipped dates just disappear with no status update
```

**New:**
```python
# Step 1: Filter price data and track skips
available_dates = price_manager.get_available_trading_dates(start, end)
price_skips = set(requested_dates) - set(available_dates)

# Step 2: Filter completed dates per-model and track skips
dates_to_process, completion_skips = self._filter_completed_dates_with_tracking(
    available_dates, models
)

# Step 3: Update job_details status for all skipped dates
self._mark_skipped_dates(price_skips, completion_skips, models)

# Step 4: Execute only dates_to_process
return dates_to_process, warnings
```

#### New Helper: `_filter_completed_dates_with_tracking()`

```python
def _filter_completed_dates_with_tracking(
    self,
    available_dates: List[str],
    models: List[str]
) -> Tuple[List[str], Dict[str, Set[str]]]:
    """
    Filter already-completed dates per model.

    Args:
        available_dates: Dates with complete price data
        models: Model signatures

    Returns:
        - dates_to_process: Union of all dates needed by any model
        - completion_skips: {model: {dates_to_skip_for_this_model}}
    """
    if not available_dates:
        return [], {}

    # Get completed dates from job_details history
    start_date = available_dates[0]
    end_date = available_dates[-1]
    completed_dates = self.job_manager.get_completed_model_dates(
        models, start_date, end_date
    )

    completion_skips = {}
    dates_needed_by_any_model = set()

    for model in models:
        model_completed = set(completed_dates.get(model, []))
        model_skips = set(available_dates) & model_completed
        completion_skips[model] = model_skips

        # Track dates this model still needs
        dates_needed_by_any_model.update(
            set(available_dates) - model_skips
        )

    return sorted(list(dates_needed_by_any_model)), completion_skips
```

#### New Helper: `_mark_skipped_dates()`

```python
def _mark_skipped_dates(
    self,
    price_skips: Set[str],
    completion_skips: Dict[str, Set[str]],
    models: List[str]
) -> None:
    """
    Update job_details status for all skipped dates.

    Args:
        price_skips: Dates without complete price data (affects all models)
        completion_skips: {model: {dates}} already completed per model
        models: All model signatures in job
    """
    # Price skips affect ALL models equally
    for date in price_skips:
        for model in models:
            self.job_manager.update_job_detail_status(
                self.job_id, date, model,
                "skipped",
                error="Incomplete price data"
            )

    # Completion skips are per-model
    for model, skipped_dates in completion_skips.items():
        for date in skipped_dates:
            self.job_manager.update_job_detail_status(
                self.job_id, date, model,
                "skipped",
                error="Already completed"
            )
```

### 4. JobManager Changes

#### Updated Completion Logic in `update_job_detail_status()`

**Current (around line 419-437):**
```python
cursor.execute("""
    SELECT
        COUNT(*) as total,
        SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
        SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed
    FROM job_details
    WHERE job_id = ?
""", (job_id,))

total, completed, failed = cursor.fetchone()

if completed + failed == total:  # Never true with skipped entries!
    # Determine final status
```

**New:**
```python
cursor.execute("""
    SELECT
        COUNT(*) as total,
        SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
        SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
        SUM(CASE WHEN status = 'skipped' THEN 1 ELSE 0 END) as skipped
    FROM job_details
    WHERE job_id = ?
""", (job_id,))

total, completed, failed, skipped = cursor.fetchone()

# Job is done when all details are in terminal states
if completed + failed + skipped == total:
    # Determine final status based only on executed dates
    # (skipped dates don't affect job success/failure)
    if failed == 0:
        final_status = "completed"
    elif completed > 0:
        final_status = "partial"
    else:
        final_status = "failed"

    # Update job to final status...
```

#### Updated Progress Tracking in `get_job_progress()`

**Current:**
```python
cursor.execute("""
    SELECT
        COUNT(*) as total,
        SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
        SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed
    FROM job_details
    WHERE job_id = ?
""", (job_id,))

total, completed, failed = cursor.fetchone()

return {
    "total_model_days": total,
    "completed": completed or 0,
    "failed": failed or 0,
    # ...
}
```

**New:**
```python
cursor.execute("""
    SELECT
        COUNT(*) as total,
        SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
        SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
        SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
        SUM(CASE WHEN status = 'skipped' THEN 1 ELSE 0 END) as skipped
    FROM job_details
    WHERE job_id = ?
""", (job_id,))

total, completed, failed, pending, skipped = cursor.fetchone()

return {
    "total_model_days": total,
    "completed": completed or 0,
    "failed": failed or 0,
    "pending": pending or 0,
    "skipped": skipped or 0,  # NEW
    # ...
}
```

### 5. Warning Message Updates

**Current:**
```python
warnings.append(f"Skipped {len(skipped)} dates due to incomplete price data: {sorted(list(skipped))}")
```

**New (distinguish skip types):**
```python
if price_skips:
    warnings.append(
        f"Skipped {len(price_skips)} dates due to incomplete price data: "
        f"{sorted(list(price_skips))}"
    )

# Count total completion skips across all models
total_completion_skips = sum(len(dates) for dates in completion_skips.values())
if total_completion_skips > 0:
    warnings.append(
        f"Skipped {total_completion_skips} model-days already completed"
    )
```

### 6. Expected API Response

Using example: dates [2025-10-01 to 2025-10-05], model [gpt-5]
- 10/1: Already completed
- 10/2, 10/3: Executed successfully
- 10/4, 10/5: Weekends (no price data)

**After fix:**
```json
{
    "job_id": "c2b68f6a-8beb-4bd2-bd98-749cdd98dda6",
    "status": "completed",  // ✓ Job completes correctly
    "progress": {
        "total_model_days": 5,
        "completed": 2,
        "failed": 0,
        "pending": 0,      // ✓ No longer stuck
        "skipped": 3       // ✓ Clear accounting
    },
    "details": [
        {
            "date": "2025-10-01",
            "model": "gpt-5",
            "status": "skipped",
            "error": "Already completed",  // ✓ Clear reason
            "started_at": null,
            "completed_at": null
        },
        {
            "date": "2025-10-02",
            "model": "gpt-5",
            "status": "completed",
            "error": null,
            "started_at": "2025-11-02T14:05:45.592208Z",
            "completed_at": "2025-11-02T14:05:45.625924Z"
        },
        {
            "date": "2025-10-03",
            "model": "gpt-5",
            "status": "completed",
            "error": null,
            "started_at": "2025-11-02T14:05:45.636893Z",
            "completed_at": "2025-11-02T14:05:45.663431Z"
        },
        {
            "date": "2025-10-04",
            "model": "gpt-5",
            "status": "skipped",
            "error": "Incomplete price data",  // ✓ Clear reason
            "started_at": null,
            "completed_at": null
        },
        {
            "date": "2025-10-05",
            "model": "gpt-5",
            "status": "skipped",
            "error": "Incomplete price data",  // ✓ Clear reason
            "started_at": null,
            "completed_at": null
        }
    ],
    "warnings": [
        "Skipped 2 dates due to incomplete price data: ['2025-10-04', '2025-10-05']",
        "Skipped 1 model-days already completed"
    ]
}
```

## Multi-Model Handling

The design correctly handles multiple models with different completion states.

**Example scenario:**
- Job: dates [10/1, 10/2, 10/3], models [gpt-5, claude-opus]
- gpt-5: Already completed 10/1
- claude-opus: Needs all dates

**Correct behavior:**
```json
{
    "details": [
        {
            "date": "2025-10-01",
            "model": "gpt-5",
            "status": "skipped",
            "error": "Already completed"
        },
        {
            "date": "2025-10-01",
            "model": "claude-opus",
            "status": "completed",  // ✓ Executed for this model
            "error": null
        },
        // ... other dates
    ]
}
```

**Implementation detail:**
- `completion_skips` tracks per-model: `{"gpt-5": {"2025-10-01"}, "claude-opus": set()}`
- Only gpt-5's 10/1 entry gets marked skipped
- 10/1 still gets executed because claude-opus needs it

## Implementation Checklist

### 1. Database Migration
- [ ] Update database.py schema with 'skipped' status
- [ ] Test dev mode table recreation
- [ ] Create migration SQL for production users

### 2. JobManager Updates (api/job_manager.py)
- [ ] Update `update_job_detail_status()` completion logic (line ~419)
- [ ] Update `get_job_progress()` to include skipped count (line ~504)
- [ ] Test job completion with mixed statuses

### 3. SimulationWorker Updates (api/simulation_worker.py)
- [ ] Implement `_filter_completed_dates_with_tracking()` helper
- [ ] Implement `_mark_skipped_dates()` helper
- [ ] Update `_prepare_data()` to track and mark skips (line ~303)
- [ ] Update warning messages to distinguish skip types (line ~355)

### 4. Testing
- [ ] Unit test: Skip dates with incomplete price data
- [ ] Unit test: Skip dates already completed (single model)
- [ ] Unit test: Multi-model with different completion states
- [ ] Unit test: Job completes with all dates skipped
- [ ] Unit test: Mixed completed/failed/skipped determines correct final status
- [ ] Integration test: Full workflow with mixed scenarios
- [ ] Update existing tests expecting old behavior

### 5. Documentation
- [ ] Update API_REFERENCE.md with skipped status
- [ ] Update database-schema.md with new constraint
- [ ] Add migration notes to CHANGELOG.md

## Testing Strategy

### Unit Tests

**Test: Skip incomplete price data**
```python
def test_skip_incomplete_price_data():
    # Setup: Job with weekend dates
    # Mock: price_manager returns only weekdays
    # Assert: Weekend dates marked as skipped with "Incomplete price data"
```

**Test: Skip already completed**
```python
def test_skip_already_completed():
    # Setup: Job with dates already in job_details as completed
    # Assert: Those dates marked as skipped with "Already completed"
    # Assert: Job still completes successfully
```

**Test: Multi-model different states**
```python
def test_multi_model_skip_handling():
    # Setup: Two models, one has completed 10/1, other hasn't
    # Assert: Only first model's 10/1 is skipped
    # Assert: Second model's 10/1 executes normally
```

**Test: Job completion with skips**
```python
def test_job_completes_with_skipped():
    # Setup: Job where all dates are skipped
    # Assert: Job status becomes "completed"
    # Assert: Progress shows pending=0, skipped=N
```

### Integration Test

**Test: Mixed execution scenario**
```python
def test_mixed_completed_skipped_failed():
    # Setup: Date range with:
    #   - Some dates already completed
    #   - Some dates missing price data
    #   - Some dates to execute (mix success/failure)
    # Assert: Final status reflects executed dates only
    # Assert: All skip reasons correct
    # Assert: Job completes when all terminal
```

## Migration Notes

### For Development
No action needed - dev database recreates on startup.

### For Production Users

Run this SQL before deploying the updated code:

```sql
-- Backup existing data
CREATE TABLE job_details_backup AS SELECT * FROM job_details;

-- Drop old constraint and add new one
-- SQLite doesn't support ALTER CONSTRAINT, so recreate table
CREATE TABLE job_details_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    date TEXT NOT NULL,
    model TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('pending', 'running', 'completed', 'failed', 'skipped')),
    started_at TEXT,
    completed_at TEXT,
    duration_seconds REAL,
    error TEXT,
    FOREIGN KEY (job_id) REFERENCES jobs(job_id) ON DELETE CASCADE
);

-- Copy data
INSERT INTO job_details_new SELECT * FROM job_details;

-- Swap tables
DROP TABLE job_details;
ALTER TABLE job_details_new RENAME TO job_details;

-- Clean up backup (optional)
-- DROP TABLE job_details_backup;
```

## Rollback Plan

If issues arise:
1. Revert code changes
2. Restore database from backup (job_details_backup table)
3. Pending entries will remain pending (original behavior)

## Success Metrics

1. **No stuck jobs** - All jobs reach terminal status (completed/partial/failed)
2. **Clear status accounting** - API responses show exact counts for each status
3. **Accurate skip reasons** - Users can distinguish between skip types
4. **Multi-model correctness** - Different models can have different skip states for same date

## References

- Database schema: `api/database.py`
- Job manager: `api/job_manager.py`
- Simulation worker: `api/simulation_worker.py`
- Migration strategy: docs/developer/database-schema.md
