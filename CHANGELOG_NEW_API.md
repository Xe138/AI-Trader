# API Schema Update - Resume Mode & Idempotent Behavior

## Summary

Updated the `/simulate/trigger` endpoint to support three new use cases:
1. **Resume mode**: Continue simulations from last completed date per model
2. **Idempotent behavior**: Skip already-completed dates by default
3. **Explicit date ranges**: Clearer API contract with required `end_date`

## Breaking Changes

### Request Schema

**Before:**
```json
{
  "start_date": "2025-10-01",        // Required
  "end_date": "2025-10-02",          // Optional (defaulted to start_date)
  "models": ["gpt-5"]                // Optional
}
```

**After:**
```json
{
  "start_date": "2025-10-01",        // Optional (null for resume mode)
  "end_date": "2025-10-02",          // REQUIRED (cannot be null/empty)
  "models": ["gpt-5"],               // Optional
  "replace_existing": false          // NEW: Optional (default: false)
}
```

### Key Changes

1. **`end_date` is now REQUIRED**
   - Cannot be `null` or empty string
   - Must always be provided
   - For single-day simulation, set `start_date` == `end_date`

2. **`start_date` is now OPTIONAL**
   - Can be `null` or omitted to enable resume mode
   - When `null`, each model resumes from its last completed date
   - If no data exists (cold start), uses `end_date` as single-day simulation

3. **NEW `replace_existing` field**
   - `false` (default): Skip already-completed model-days (idempotent)
   - `true`: Re-run all dates even if previously completed

## Use Cases

### 1. Explicit Date Range
```bash
curl -X POST http://localhost:8080/simulate/trigger \
  -H "Content-Type: application/json" \
  -d '{
    "start_date": "2025-10-01",
    "end_date": "2025-10-31",
    "models": ["gpt-5"]
  }'
```

### 2. Single Date
```bash
curl -X POST http://localhost:8080/simulate/trigger \
  -H "Content-Type: application/json" \
  -d '{
    "start_date": "2025-10-15",
    "end_date": "2025-10-15",
    "models": ["gpt-5"]
  }'
```

### 3. Resume Mode (NEW)
```bash
curl -X POST http://localhost:8080/simulate/trigger \
  -H "Content-Type: application/json" \
  -d '{
    "start_date": null,
    "end_date": "2025-10-31",
    "models": ["gpt-5"]
  }'
```

**Behavior:**
- Model "gpt-5" last completed: `2025-10-15`
- Will simulate: `2025-10-16` through `2025-10-31`
- If no data exists: Will simulate only `2025-10-31`

### 4. Idempotent Simulation (NEW)
```bash
curl -X POST http://localhost:8080/simulate/trigger \
  -H "Content-Type: application/json" \
  -d '{
    "start_date": "2025-10-01",
    "end_date": "2025-10-31",
    "models": ["gpt-5"],
    "replace_existing": false
  }'
```

**Behavior:**
- Checks database for already-completed dates
- Only simulates dates that haven't been completed yet
- Returns error if all dates already completed

### 5. Force Replace
```bash
curl -X POST http://localhost:8080/simulate/trigger \
  -H "Content-Type: application/json" \
  -d '{
    "start_date": "2025-10-01",
    "end_date": "2025-10-31",
    "models": ["gpt-5"],
    "replace_existing": true
  }'
```

**Behavior:**
- Re-runs all dates regardless of completion status

## Implementation Details

### Files Modified

1. **`api/main.py`**
   - Updated `SimulateTriggerRequest` Pydantic model
   - Added validators for `end_date` (required)
   - Added validators for `start_date` (optional, can be null)
   - Added resume logic per model
   - Added idempotent filtering logic
   - Fixed bug with `start_date=None` in price data checks

2. **`api/job_manager.py`**
   - Added `get_last_completed_date_for_model(model)` method
   - Added `get_completed_model_dates(models, start_date, end_date)` method
   - Updated `create_job()` to accept `model_day_filter` parameter

3. **`tests/integration/test_api_endpoints.py`**
   - Updated all tests to use new schema
   - Added tests for resume mode
   - Added tests for idempotent behavior
   - Added tests for validation rules

4. **Documentation Updated**
   - `API_REFERENCE.md` - Complete API documentation with examples
   - `QUICK_START.md` - Updated getting started examples
   - `docs/user-guide/using-the-api.md` - Updated user guide
   - Client library examples (Python, TypeScript)

### Database Schema

No changes to database schema. New functionality uses existing tables:
- `job_details` table tracks completion status per model-day
- Unique index on `(job_id, date, model)` ensures no duplicates

### Per-Model Independence

Each model maintains its own completion state:
```
Model A: last_completed_date = 2025-10-15
Model B: last_completed_date = 2025-10-10

Request: start_date=null, end_date=2025-10-31

Result:
- Model A simulates: 2025-10-16 through 2025-10-31 (16 days)
- Model B simulates: 2025-10-11 through 2025-10-31 (21 days)
```

## Migration Guide

### For API Clients

**Old Code:**
```python
# Single day (old)
client.trigger_simulation(start_date="2025-10-15")
```

**New Code:**
```python
# Single day (new) - MUST provide end_date
client.trigger_simulation(start_date="2025-10-15", end_date="2025-10-15")

# Or use resume mode
client.trigger_simulation(start_date=None, end_date="2025-10-31")
```

### Validation Changes

**Will Now Fail:**
```json
{
  "start_date": "2025-10-01",
  "end_date": ""              // ❌ Empty string rejected
}
```

```json
{
  "start_date": "2025-10-01",
  "end_date": null            // ❌ Null rejected
}
```

```json
{
  "start_date": "2025-10-01"  // ❌ Missing end_date
}
```

**Will Work:**
```json
{
  "end_date": "2025-10-31"    // ✓ start_date omitted = resume mode
}
```

```json
{
  "start_date": null,
  "end_date": "2025-10-31"    // ✓ Explicit null = resume mode
}
```

## Benefits

1. **Daily Automation**: Resume mode perfect for cron jobs
   - No need to calculate "yesterday's date"
   - Just provide today as end_date

2. **Idempotent by Default**: Safe to re-run
   - Accidentally trigger same date? No problem, it's skipped
   - Explicit `replace_existing=true` when you want to re-run

3. **Per-Model Independence**: Flexible deployment
   - Can add new models without re-running old ones
   - Models can progress at different rates

4. **Clear API Contract**: No ambiguity
   - `end_date` always required
   - `start_date=null` clearly means "resume"
   - Default behavior is safe (idempotent)

## Backward Compatibility

⚠️ **This is a BREAKING CHANGE** for clients that:
- Rely on `end_date` defaulting to `start_date`
- Don't explicitly provide `end_date`

**Migration:** Update all API calls to explicitly provide `end_date`.

## Testing

Run integration tests:
```bash
pytest tests/integration/test_api_endpoints.py -v
```

All tests updated to cover:
- Single-day simulation
- Date ranges
- Resume mode (cold start and with existing data)
- Idempotent behavior
- Validation rules
