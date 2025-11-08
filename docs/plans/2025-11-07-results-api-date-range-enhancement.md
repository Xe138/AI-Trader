# Results API Date Range Enhancement

**Date:** 2025-11-07
**Status:** Design Complete
**Breaking Change:** Yes (removes `date` parameter)

## Overview

Enhance the `/results` API endpoint to support date range queries with portfolio performance metrics including period returns and annualized returns.

## Current State

The `/results` endpoint currently supports:
- Single-date queries via `date` parameter
- Filtering by `job_id`, `model`
- Reasoning inclusion via `reasoning` parameter
- Returns detailed day-by-day trading information

## Proposed Changes

### 1. API Contract Changes

**New Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `start_date` | string | No | Start date (YYYY-MM-DD). If provided alone, acts as single date (end_date defaults to start_date) |
| `end_date` | string | No | End date (YYYY-MM-DD). If provided alone, acts as single date (start_date defaults to end_date) |
| `model` | string | No | Filter by model signature (unchanged) |
| `job_id` | string | No | Filter by job UUID (unchanged) |
| `reasoning` | string | No | Include reasoning: "none" (default), "summary", "full". Ignored for date range queries |

**Breaking Changes:**
- **REMOVE** `date` parameter (replaced by `start_date`/`end_date`)
- Clients using `date` will receive `422 Unprocessable Entity` with migration message

**Default Behavior (no filters):**
- Returns last 30 calendar days of data for all models
- Configurable via `DEFAULT_RESULTS_LOOKBACK_DAYS` environment variable (default: 30)

### 2. Response Structure

#### Single-Date Response (start_date == end_date)

Maintains current format:

```json
{
  "count": 2,
  "results": [
    {
      "date": "2025-01-16",
      "model": "gpt-4",
      "job_id": "550e8400-...",
      "starting_position": {
        "holdings": [{"symbol": "AAPL", "quantity": 10}],
        "cash": 8500.0,
        "portfolio_value": 10000.0
      },
      "daily_metrics": {
        "profit": 100.0,
        "return_pct": 1.0,
        "days_since_last_trading": 1
      },
      "trades": [...],
      "final_position": {...},
      "metadata": {...},
      "reasoning": null
    },
    {
      "date": "2025-01-16",
      "model": "claude-3.7-sonnet",
      ...
    }
  ]
}
```

#### Date Range Response (start_date < end_date)

New lightweight format:

```json
{
  "count": 2,
  "results": [
    {
      "model": "gpt-4",
      "start_date": "2025-01-16",
      "end_date": "2025-01-20",
      "daily_portfolio_values": [
        {"date": "2025-01-16", "portfolio_value": 10100.0},
        {"date": "2025-01-17", "portfolio_value": 10250.0},
        {"date": "2025-01-20", "portfolio_value": 10500.0}
      ],
      "period_metrics": {
        "starting_portfolio_value": 10000.0,
        "ending_portfolio_value": 10500.0,
        "period_return_pct": 5.0,
        "annualized_return_pct": 45.6,
        "calendar_days": 5,
        "trading_days": 3
      }
    },
    {
      "model": "claude-3.7-sonnet",
      "start_date": "2025-01-16",
      "end_date": "2025-01-20",
      "daily_portfolio_values": [...],
      "period_metrics": {...}
    }
  ]
}
```

### 3. Performance Metrics Calculations

**Starting Portfolio Value:**
- Use `trading_days.starting_portfolio_value` from first trading day in range

**Period Return:**
```
period_return_pct = ((ending_value - starting_value) / starting_value) * 100
```

**Annualized Return:**
```
annualized_return_pct = ((ending_value / starting_value) ** (365 / calendar_days) - 1) * 100
```

**Calendar Days:**
- Count actual calendar days from start_date to end_date (inclusive)

**Trading Days:**
- Count number of actual trading days with data in the range

### 4. Data Handling Rules

**Edge Trimming:**
- If requested range extends beyond available data at edges, trim to actual data boundaries
- Example: Request 2025-01-10 to 2025-01-20, but data exists 2025-01-15 to 2025-01-17
- Response shows `start_date=2025-01-15`, `end_date=2025-01-17`

**Gaps Within Range:**
- Include only dates with actual data (no null values, no gap indicators)
- Example: If 2025-01-18 missing between 2025-01-17 and 2025-01-19, only include existing dates

**Per-Model Results:**
- Return one result object per model
- Each model independently trimmed to its available data range
- If model has no data in range, exclude from results

**Empty Results:**
- If NO models have data matching filters → `404 Not Found`
- If ANY model has data → `200 OK` with results for models that have data

**Filter Logic:**
- All filters (job_id, model, date range) applied with AND logic
- Date range can extend beyond a job's scope (returns empty if no overlap)

### 5. Error Handling

| Scenario | Status | Response |
|----------|--------|----------|
| No data matches filters | 404 | `{"detail": "No trading data found for the specified filters"}` |
| Invalid date format | 400 | `{"detail": "Invalid date format: 2025-1-16. Expected YYYY-MM-DD"}` |
| start_date > end_date | 400 | `{"detail": "start_date must be <= end_date"}` |
| Future dates | 400 | `{"detail": "Cannot query future dates"}` |
| Using old `date` param | 422 | `{"detail": "Parameter 'date' has been removed. Use 'start_date' and/or 'end_date' instead."}` |

### 6. Special Cases

**Single Trading Day in Range:**
- Use date range response format (not single-date)
- `daily_portfolio_values` has one entry
- `period_return_pct` and `annualized_return_pct` = 0.0
- `calendar_days` = difference between requested start/end
- `trading_days` = 1

**Reasoning Parameter:**
- Ignored for date range queries (start_date < end_date)
- Only applies to single-date queries
- Keeps range responses lightweight and fast

## Implementation Plan

### Phase 1: Core Logic

**File:** `api/routes/results_v2.py`

1. Add new query parameters (`start_date`, `end_date`)
2. Implement date range defaulting logic:
   - No dates → last 30 days
   - Only start_date → single date
   - Only end_date → single date
   - Both → range query
3. Validate dates (format, order, not future)
4. Detect deprecated `date` parameter → return 422
5. Query database with date range filter
6. Group results by model
7. Trim edges per model
8. Calculate period metrics
9. Format response based on single-date vs range

### Phase 2: Period Metrics Calculation

**Functions to implement:**

```python
def calculate_period_metrics(
    starting_value: float,
    ending_value: float,
    start_date: str,
    end_date: str,
    trading_days: int
) -> dict:
    """Calculate period return and annualized return."""
    # Calculate calendar days
    # Calculate period_return_pct
    # Calculate annualized_return_pct
    # Return metrics dict
```

### Phase 3: Documentation Updates

1. **API_REFERENCE.md** - Complete rewrite of `/results` section
2. **docs/reference/environment-variables.md** - Add `DEFAULT_RESULTS_LOOKBACK_DAYS`
3. **CHANGELOG.md** - Document breaking change
4. **README.md** - Update example queries
5. **Client library examples** - Update Python/TypeScript examples

### Phase 4: Testing

**Test Coverage:**

- [ ] Single date query (start_date only)
- [ ] Single date query (end_date only)
- [ ] Single date query (both equal)
- [ ] Date range query (multiple days)
- [ ] Default lookback (no dates provided)
- [ ] Edge trimming (requested range exceeds data)
- [ ] Gap handling (missing dates in middle)
- [ ] Empty results (404)
- [ ] Invalid date formats (400)
- [ ] start_date > end_date (400)
- [ ] Future dates (400)
- [ ] Deprecated `date` parameter (422)
- [ ] Period metrics calculations
- [ ] All filter combinations (job_id, model, dates)
- [ ] Single trading day in range
- [ ] Reasoning parameter ignored in range queries
- [ ] Multiple models with different data ranges

## Migration Guide

### For API Consumers

**Before (current):**
```bash
# Single date
GET /results?date=2025-01-16&model=gpt-4

# Multiple dates required multiple queries
GET /results?date=2025-01-16&model=gpt-4
GET /results?date=2025-01-17&model=gpt-4
GET /results?date=2025-01-18&model=gpt-4
```

**After (new):**
```bash
# Single date (option 1)
GET /results?start_date=2025-01-16&model=gpt-4

# Single date (option 2)
GET /results?start_date=2025-01-16&end_date=2025-01-16&model=gpt-4

# Date range (new capability)
GET /results?start_date=2025-01-16&end_date=2025-01-20&model=gpt-4
```

### Python Client Update

```python
# OLD (will break)
results = client.get_results(date="2025-01-16")

# NEW
results = client.get_results(start_date="2025-01-16")  # Single date
results = client.get_results(start_date="2025-01-16", end_date="2025-01-20")  # Range
```

## Environment Variables

**New:**
- `DEFAULT_RESULTS_LOOKBACK_DAYS` (integer, default: 30) - Number of days to look back when no date filters provided

## Dependencies

- No new dependencies required
- Uses existing database schema (trading_days table)
- Compatible with current database structure

## Risks & Mitigations

**Risk:** Breaking change disrupts existing clients
**Mitigation:**
- Clear error message with migration instructions
- Update all documentation and examples
- Add to CHANGELOG with migration guide

**Risk:** Large date ranges cause performance issues
**Mitigation:**
- Consider adding max date range validation (e.g., 365 days)
- Date range responses are lightweight (no trades/holdings/reasoning)

**Risk:** Edge trimming behavior confuses users
**Mitigation:**
- Document clearly with examples
- Returned `start_date`/`end_date` show actual range
- Consider adding `requested_start_date`/`requested_end_date` fields to response

## Future Enhancements

- Add `max_date_range_days` environment variable
- Add `requested_start_date`/`requested_end_date` to response
- Consider adding aggregated statistics (max drawdown, Sharpe ratio)
- Consider adding comparison mode (multiple models side-by-side)

## Approval Checklist

- [x] Design validated with stakeholder
- [ ] Implementation plan reviewed
- [ ] Test coverage defined
- [ ] Documentation updates planned
- [ ] Migration guide created
- [ ] Breaking change acknowledged
