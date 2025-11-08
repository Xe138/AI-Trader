# Results API Date Range Enhancement - Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add date range query support to `/results` endpoint with portfolio performance metrics (period return, annualized return).

**Architecture:** Replace `date` parameter with `start_date`/`end_date`. Return single-date format (detailed) when dates are equal, or range format (lightweight with metrics) when different. Default to last 30 days when no dates provided.

**Tech Stack:** FastAPI, SQLite, Python 3.12, pytest

---

## Task 1: Add Period Metrics Calculation Function

**Files:**
- Create: `api/routes/period_metrics.py`
- Test: `tests/api/test_period_metrics.py`

**Step 1: Write the failing test**

Create `tests/api/test_period_metrics.py`:

```python
"""Tests for period metrics calculations."""

from datetime import datetime
from api.routes.period_metrics import calculate_period_metrics


def test_calculate_period_metrics_basic():
    """Test basic period metrics calculation."""
    metrics = calculate_period_metrics(
        starting_value=10000.0,
        ending_value=10500.0,
        start_date="2025-01-16",
        end_date="2025-01-20",
        trading_days=3
    )

    assert metrics["starting_portfolio_value"] == 10000.0
    assert metrics["ending_portfolio_value"] == 10500.0
    assert metrics["period_return_pct"] == 5.0
    assert metrics["calendar_days"] == 5
    assert metrics["trading_days"] == 3
    # annualized_return = ((10500/10000) ** (365/5) - 1) * 100 = ~492%
    assert 490 < metrics["annualized_return_pct"] < 495


def test_calculate_period_metrics_zero_return():
    """Test period metrics when no change."""
    metrics = calculate_period_metrics(
        starting_value=10000.0,
        ending_value=10000.0,
        start_date="2025-01-16",
        end_date="2025-01-16",
        trading_days=1
    )

    assert metrics["period_return_pct"] == 0.0
    assert metrics["annualized_return_pct"] == 0.0
    assert metrics["calendar_days"] == 1


def test_calculate_period_metrics_negative_return():
    """Test period metrics with loss."""
    metrics = calculate_period_metrics(
        starting_value=10000.0,
        ending_value=9500.0,
        start_date="2025-01-16",
        end_date="2025-01-23",
        trading_days=5
    )

    assert metrics["period_return_pct"] == -5.0
    assert metrics["calendar_days"] == 8
    # Negative annualized return
    assert metrics["annualized_return_pct"] < 0
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/api/test_period_metrics.py -v
```

Expected: `ModuleNotFoundError: No module named 'api.routes.period_metrics'`

**Step 3: Write minimal implementation**

Create `api/routes/period_metrics.py`:

```python
"""Period metrics calculation for date range queries."""

from datetime import datetime


def calculate_period_metrics(
    starting_value: float,
    ending_value: float,
    start_date: str,
    end_date: str,
    trading_days: int
) -> dict:
    """Calculate period return and annualized return.

    Args:
        starting_value: Portfolio value at start of period
        ending_value: Portfolio value at end of period
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        trading_days: Number of actual trading days in period

    Returns:
        Dict with period_return_pct, annualized_return_pct, calendar_days, trading_days
    """
    # Calculate calendar days (inclusive)
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    calendar_days = (end_dt - start_dt).days + 1

    # Calculate period return
    if starting_value == 0:
        period_return_pct = 0.0
    else:
        period_return_pct = ((ending_value - starting_value) / starting_value) * 100

    # Calculate annualized return
    if calendar_days == 0 or starting_value == 0 or ending_value <= 0:
        annualized_return_pct = 0.0
    else:
        # Formula: ((ending / starting) ** (365 / days) - 1) * 100
        annualized_return_pct = ((ending_value / starting_value) ** (365 / calendar_days) - 1) * 100

    return {
        "starting_portfolio_value": starting_value,
        "ending_portfolio_value": ending_value,
        "period_return_pct": round(period_return_pct, 2),
        "annualized_return_pct": round(annualized_return_pct, 2),
        "calendar_days": calendar_days,
        "trading_days": trading_days
    }
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/api/test_period_metrics.py -v
```

Expected: All tests PASS

**Step 5: Commit**

```bash
git add api/routes/period_metrics.py tests/api/test_period_metrics.py
git commit -m "feat: add period metrics calculation for date range queries"
```

---

## Task 2: Add Date Validation Utilities

**Files:**
- Modify: `api/routes/results_v2.py`
- Test: `tests/api/test_results_v2.py`

**Step 1: Write the failing test**

Create `tests/api/test_results_v2.py`:

```python
"""Tests for results_v2 endpoint date validation."""

import pytest
from datetime import datetime, timedelta
from api.routes.results_v2 import validate_and_resolve_dates


def test_validate_no_dates_provided():
    """Test default to last 30 days when no dates provided."""
    start, end = validate_and_resolve_dates(None, None)

    # Should default to last 30 days
    end_dt = datetime.strptime(end, "%Y-%m-%d")
    start_dt = datetime.strptime(start, "%Y-%m-%d")

    assert (end_dt - start_dt).days == 30
    assert end_dt.date() <= datetime.now().date()


def test_validate_only_start_date():
    """Test single date when only start_date provided."""
    start, end = validate_and_resolve_dates("2025-01-16", None)

    assert start == "2025-01-16"
    assert end == "2025-01-16"


def test_validate_only_end_date():
    """Test single date when only end_date provided."""
    start, end = validate_and_resolve_dates(None, "2025-01-16")

    assert start == "2025-01-16"
    assert end == "2025-01-16"


def test_validate_both_dates():
    """Test date range when both provided."""
    start, end = validate_and_resolve_dates("2025-01-16", "2025-01-20")

    assert start == "2025-01-16"
    assert end == "2025-01-20"


def test_validate_invalid_date_format():
    """Test error on invalid date format."""
    with pytest.raises(ValueError, match="Invalid date format"):
        validate_and_resolve_dates("2025-1-16", "2025-01-20")


def test_validate_start_after_end():
    """Test error when start_date > end_date."""
    with pytest.raises(ValueError, match="start_date must be <= end_date"):
        validate_and_resolve_dates("2025-01-20", "2025-01-16")


def test_validate_future_date():
    """Test error when dates are in future."""
    future = (datetime.now() + timedelta(days=10)).strftime("%Y-%m-%d")

    with pytest.raises(ValueError, match="Cannot query future dates"):
        validate_and_resolve_dates(future, future)
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/api/test_results_v2.py::test_validate_no_dates_provided -v
```

Expected: `ImportError: cannot import name 'validate_and_resolve_dates'`

**Step 3: Write minimal implementation**

Add to `api/routes/results_v2.py` (at top, before `get_results` function):

```python
import os
from datetime import datetime, timedelta
from fastapi import HTTPException


def validate_and_resolve_dates(
    start_date: Optional[str],
    end_date: Optional[str]
) -> tuple[str, str]:
    """Validate and resolve date parameters.

    Args:
        start_date: Start date (YYYY-MM-DD) or None
        end_date: End date (YYYY-MM-DD) or None

    Returns:
        Tuple of (resolved_start_date, resolved_end_date)

    Raises:
        ValueError: If dates are invalid
    """
    # Default lookback days
    default_lookback = int(os.getenv("DEFAULT_RESULTS_LOOKBACK_DAYS", "30"))

    # Handle None cases
    if start_date is None and end_date is None:
        # Default to last N days
        end_dt = datetime.now()
        start_dt = end_dt - timedelta(days=default_lookback)
        return start_dt.strftime("%Y-%m-%d"), end_dt.strftime("%Y-%m-%d")

    if start_date is None:
        # Only end_date provided -> single date
        start_date = end_date

    if end_date is None:
        # Only start_date provided -> single date
        end_date = start_date

    # Validate date formats
    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError:
        raise ValueError(f"Invalid date format. Expected YYYY-MM-DD")

    # Validate order
    if start_dt > end_dt:
        raise ValueError("start_date must be <= end_date")

    # Validate not future
    now = datetime.now()
    if start_dt.date() > now.date() or end_dt.date() > now.date():
        raise ValueError("Cannot query future dates")

    return start_date, end_date
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/api/test_results_v2.py -v
```

Expected: All tests PASS

**Step 5: Commit**

```bash
git add api/routes/results_v2.py tests/api/test_results_v2.py
git commit -m "feat: add date validation and resolution for results endpoint"
```

---

## Task 3: Update Results Endpoint with Date Range Support

**Files:**
- Modify: `api/routes/results_v2.py`
- Test: `tests/api/test_results_v2.py`

**Step 1: Write the failing test**

Add to `tests/api/test_results_v2.py`:

```python
import json
from fastapi.testclient import TestClient
from api.main import create_app
from api.database import Database


@pytest.fixture
def test_db(tmp_path):
    """Create test database with sample data."""
    db_path = str(tmp_path / "test.db")
    db = Database(db_path)

    # Create sample trading days
    trading_day_id_1 = db.create_trading_day(
        job_id="test-job-1",
        model="gpt-4",
        date="2025-01-16",
        starting_cash=10000.0,
        starting_portfolio_value=10000.0,
        daily_profit=0.0,
        daily_return_pct=0.0,
        ending_cash=9500.0,
        ending_portfolio_value=10100.0,
        reasoning_summary="Bought AAPL",
        total_actions=1,
        session_duration_seconds=45.2,
        days_since_last_trading=0
    )

    db.add_holding(trading_day_id_1, "AAPL", 10)
    db.add_action(trading_day_id_1, "buy", "AAPL", 10, 150.0)

    trading_day_id_2 = db.create_trading_day(
        job_id="test-job-1",
        model="gpt-4",
        date="2025-01-17",
        starting_cash=9500.0,
        starting_portfolio_value=10100.0,
        daily_profit=100.0,
        daily_return_pct=1.0,
        ending_cash=9500.0,
        ending_portfolio_value=10250.0,
        reasoning_summary="Held AAPL",
        total_actions=0,
        session_duration_seconds=30.0,
        days_since_last_trading=1
    )

    db.add_holding(trading_day_id_2, "AAPL", 10)

    return db


def test_get_results_single_date(test_db):
    """Test single date query returns detailed format."""
    app = create_app(db_path=test_db.db_path)
    app.state.test_mode = True
    client = TestClient(app)

    response = client.get("/results?start_date=2025-01-16&end_date=2025-01-16")

    assert response.status_code == 200
    data = response.json()

    assert data["count"] == 1
    assert len(data["results"]) == 1

    result = data["results"][0]
    assert result["date"] == "2025-01-16"
    assert result["model"] == "gpt-4"
    assert "starting_position" in result
    assert "daily_metrics" in result
    assert "trades" in result
    assert "final_position" in result


def test_get_results_date_range(test_db):
    """Test date range query returns metrics format."""
    app = create_app(db_path=test_db.db_path)
    app.state.test_mode = True
    client = TestClient(app)

    response = client.get("/results?start_date=2025-01-16&end_date=2025-01-17")

    assert response.status_code == 200
    data = response.json()

    assert data["count"] == 1
    assert len(data["results"]) == 1

    result = data["results"][0]
    assert result["model"] == "gpt-4"
    assert result["start_date"] == "2025-01-16"
    assert result["end_date"] == "2025-01-17"
    assert "daily_portfolio_values" in result
    assert "period_metrics" in result

    # Check daily values
    daily_values = result["daily_portfolio_values"]
    assert len(daily_values) == 2
    assert daily_values[0]["date"] == "2025-01-16"
    assert daily_values[0]["portfolio_value"] == 10100.0
    assert daily_values[1]["date"] == "2025-01-17"
    assert daily_values[1]["portfolio_value"] == 10250.0

    # Check period metrics
    metrics = result["period_metrics"]
    assert metrics["starting_portfolio_value"] == 10000.0
    assert metrics["ending_portfolio_value"] == 10250.0
    assert metrics["period_return_pct"] == 2.5
    assert metrics["calendar_days"] == 2
    assert metrics["trading_days"] == 2


def test_get_results_empty_404(test_db):
    """Test 404 when no data matches filters."""
    app = create_app(db_path=test_db.db_path)
    app.state.test_mode = True
    client = TestClient(app)

    response = client.get("/results?start_date=2025-02-01&end_date=2025-02-05")

    assert response.status_code == 404
    assert "No trading data found" in response.json()["detail"]
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/api/test_results_v2.py::test_get_results_date_range -v
```

Expected: FAIL (endpoint returns old format, not range format)

**Step 3: Rewrite the get_results endpoint**

Replace the `@router.get("/results")` function in `api/routes/results_v2.py`:

```python
from api.routes.period_metrics import calculate_period_metrics


@router.get("/results")
async def get_results(
    job_id: Optional[str] = None,
    model: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    date: Optional[str] = Query(None, deprecated=True),
    reasoning: Literal["none", "summary", "full"] = "none",
    db: Database = Depends(get_database)
):
    """Get trading results grouped by day.

    Args:
        job_id: Filter by simulation job ID
        model: Filter by model signature
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        date: DEPRECATED - Use start_date/end_date instead
        reasoning: Include reasoning logs (none/summary/full). Ignored for date ranges.
        db: Database instance (injected)

    Returns:
        JSON with day-centric trading results and performance metrics
    """
    from fastapi import HTTPException

    # Check for deprecated parameter
    if date is not None:
        raise HTTPException(
            status_code=422,
            detail="Parameter 'date' has been removed. Use 'start_date' and/or 'end_date' instead."
        )

    # Validate and resolve dates
    try:
        resolved_start, resolved_end = validate_and_resolve_dates(start_date, end_date)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Determine if single-date or range query
    is_single_date = resolved_start == resolved_end

    # Build query with filters
    query = "SELECT * FROM trading_days WHERE date >= ? AND date <= ?"
    params = [resolved_start, resolved_end]

    if job_id:
        query += " AND job_id = ?"
        params.append(job_id)

    if model:
        query += " AND model = ?"
        params.append(model)

    query += " ORDER BY model ASC, date ASC"

    # Execute query
    cursor = db.connection.execute(query, params)
    rows = cursor.fetchall()

    # Check if empty
    if not rows:
        raise HTTPException(
            status_code=404,
            detail="No trading data found for the specified filters"
        )

    # Group by model
    model_data = {}
    for row in rows:
        model_sig = row[2]  # model column
        if model_sig not in model_data:
            model_data[model_sig] = []
        model_data[model_sig].append(row)

    # Format results
    formatted_results = []

    for model_sig, model_rows in model_data.items():
        if is_single_date:
            # Single-date format (detailed)
            for row in model_rows:
                formatted_results.append(format_single_date_result(row, db, reasoning))
        else:
            # Range format (lightweight with metrics)
            formatted_results.append(format_range_result(model_sig, model_rows, db))

    return {
        "count": len(formatted_results),
        "results": formatted_results
    }


def format_single_date_result(row, db: Database, reasoning: str) -> dict:
    """Format single-date result (detailed format)."""
    trading_day_id = row[0]

    result = {
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
            "days_since_last_trading": row[14] if len(row) > 14 else 1
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
            "completed_at": row[16] if len(row) > 16 else None
        }
    }

    # Add reasoning if requested
    if reasoning == "summary":
        result["reasoning"] = row[10]  # reasoning_summary
    elif reasoning == "full":
        reasoning_full = row[11]  # reasoning_full
        result["reasoning"] = json.loads(reasoning_full) if reasoning_full else []
    else:
        result["reasoning"] = None

    return result


def format_range_result(model_sig: str, rows: list, db: Database) -> dict:
    """Format date range result (lightweight with period metrics)."""
    # Trim edges: use actual min/max dates from data
    actual_start = rows[0][3]  # date from first row
    actual_end = rows[-1][3]   # date from last row

    # Extract daily portfolio values
    daily_values = [
        {
            "date": row[3],
            "portfolio_value": row[9]  # ending_portfolio_value
        }
        for row in rows
    ]

    # Get starting and ending values
    starting_value = rows[0][5]  # starting_portfolio_value from first day
    ending_value = rows[-1][9]   # ending_portfolio_value from last day
    trading_days = len(rows)

    # Calculate period metrics
    metrics = calculate_period_metrics(
        starting_value=starting_value,
        ending_value=ending_value,
        start_date=actual_start,
        end_date=actual_end,
        trading_days=trading_days
    )

    return {
        "model": model_sig,
        "start_date": actual_start,
        "end_date": actual_end,
        "daily_portfolio_values": daily_values,
        "period_metrics": metrics
    }
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/api/test_results_v2.py::test_get_results_date_range -v
pytest tests/api/test_results_v2.py::test_get_results_single_date -v
pytest tests/api/test_results_v2.py::test_get_results_empty_404 -v
```

Expected: All tests PASS

**Step 5: Commit**

```bash
git add api/routes/results_v2.py tests/api/test_results_v2.py
git commit -m "feat: implement date range support with period metrics in results endpoint"
```

---

## Task 4: Add Database Helper Methods

**Files:**
- Modify: `api/database.py`

**Step 1: Add missing helper methods**

The endpoint uses `db.get_starting_holdings()` and `db.get_actions()` which may not exist. Add these methods to the `Database` class in `api/database.py` (after existing methods):

```python
def get_starting_holdings(self, trading_day_id: int) -> list:
    """Get starting holdings for a trading day (from previous day's ending holdings).

    Args:
        trading_day_id: Current trading day ID

    Returns:
        List of dicts with keys: symbol, quantity
    """
    # Get current trading day info
    cursor = self.connection.execute(
        "SELECT model, date FROM trading_days WHERE id = ?",
        (trading_day_id,)
    )
    row = cursor.fetchone()
    if not row:
        return []

    model, current_date = row[0], row[1]

    # Get previous trading day
    prev_day = self.get_previous_trading_day(None, model, current_date)

    if prev_day is None:
        return []  # First trading day, no previous holdings

    # Get previous day's ending holdings
    return self.get_ending_holdings(prev_day["id"])


def get_actions(self, trading_day_id: int) -> list:
    """Get all actions/trades for a trading day.

    Args:
        trading_day_id: Trading day ID

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

**Step 2: Verify methods work**

```bash
pytest tests/api/test_results_v2.py -v
```

Expected: All tests still PASS

**Step 3: Commit**

```bash
git add api/database.py
git commit -m "feat: add get_starting_holdings and get_actions helper methods to Database class"
```

---

## Task 5: Update API Documentation

**Files:**
- Modify: `API_REFERENCE.md`

**Step 1: Update /results endpoint documentation**

Replace the `### GET /results` section in `API_REFERENCE.md` (starting around line 344):

```markdown
### GET /results

Get trading results with optional date range and portfolio performance metrics.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `start_date` | string | No | Start date (YYYY-MM-DD). If provided alone, acts as single date. If omitted, defaults to 30 days ago. |
| `end_date` | string | No | End date (YYYY-MM-DD). If provided alone, acts as single date. If omitted, defaults to today. |
| `model` | string | No | Filter by model signature |
| `job_id` | string | No | Filter by job UUID |
| `reasoning` | string | No | Include reasoning: `none` (default), `summary`, or `full`. Ignored for date range queries. |

**Breaking Change:**
- The `date` parameter has been removed. Use `start_date` and/or `end_date` instead.
- Requests using `date` will receive `422 Unprocessable Entity` error.

**Default Behavior:**
- If no dates provided: Returns last 30 days (configurable via `DEFAULT_RESULTS_LOOKBACK_DAYS`)
- If only `start_date`: Single-date query (end_date = start_date)
- If only `end_date`: Single-date query (start_date = end_date)
- If both provided and equal: Single-date query (detailed format)
- If both provided and different: Date range query (metrics format)

**Response - Single Date (detailed):**

```json
{
  "count": 1,
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
      "trades": [
        {
          "action_type": "buy",
          "symbol": "MSFT",
          "quantity": 5,
          "price": 200.0,
          "created_at": "2025-01-16T14:30:00Z"
        }
      ],
      "final_position": {
        "holdings": [
          {"symbol": "AAPL", "quantity": 10},
          {"symbol": "MSFT", "quantity": 5}
        ],
        "cash": 7500.0,
        "portfolio_value": 10100.0
      },
      "metadata": {
        "total_actions": 1,
        "session_duration_seconds": 52.1,
        "completed_at": "2025-01-16T14:31:00Z"
      },
      "reasoning": null
    }
  ]
}
```

**Response - Date Range (metrics):**

```json
{
  "count": 1,
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
    }
  ]
}
```

**Period Metrics Calculations:**

- `period_return_pct` = ((ending - starting) / starting) × 100
- `annualized_return_pct` = ((ending / starting) ^ (365 / calendar_days) - 1) × 100
- `calendar_days` = Calendar days from start_date to end_date (inclusive)
- `trading_days` = Number of actual trading days with data

**Edge Trimming:**

If requested range extends beyond available data, the response is trimmed to actual data boundaries:

- Request: `start_date=2025-01-10&end_date=2025-01-20`
- Available: 2025-01-15, 2025-01-16, 2025-01-17
- Response: `start_date=2025-01-15`, `end_date=2025-01-17`

**Error Responses:**

| Status | Scenario | Response |
|--------|----------|----------|
| 404 | No data matches filters | `{"detail": "No trading data found for the specified filters"}` |
| 400 | Invalid date format | `{"detail": "Invalid date format. Expected YYYY-MM-DD"}` |
| 400 | start_date > end_date | `{"detail": "start_date must be <= end_date"}` |
| 400 | Future dates | `{"detail": "Cannot query future dates"}` |
| 422 | Using old `date` param | `{"detail": "Parameter 'date' has been removed. Use 'start_date' and/or 'end_date' instead."}` |

**Examples:**

Single date query:
```bash
curl "http://localhost:8080/results?start_date=2025-01-16&model=gpt-4"
```

Date range query:
```bash
curl "http://localhost:8080/results?start_date=2025-01-16&end_date=2025-01-20&model=gpt-4"
```

Default (last 30 days):
```bash
curl "http://localhost:8080/results"
```

With filters:
```bash
curl "http://localhost:8080/results?job_id=550e8400-...&start_date=2025-01-16&end_date=2025-01-20"
```
```

**Step 2: Verify documentation accuracy**

Manually review the documentation against the implementation.

**Step 3: Commit**

```bash
git add API_REFERENCE.md
git commit -m "docs: update /results endpoint documentation for date range support"
```

---

## Task 6: Update Environment Variables Documentation

**Files:**
- Modify: `docs/reference/environment-variables.md`

**Step 1: Add DEFAULT_RESULTS_LOOKBACK_DAYS**

Add to `docs/reference/environment-variables.md` in the appropriate section:

```markdown
### DEFAULT_RESULTS_LOOKBACK_DAYS

**Type:** Integer
**Default:** 30
**Required:** No

Number of calendar days to look back when querying `/results` endpoint without date filters.

**Example:**
```bash
# Default to last 60 days
DEFAULT_RESULTS_LOOKBACK_DAYS=60
```

**Usage:**
When no `start_date` or `end_date` parameters are provided to `/results`, the endpoint returns data from the last N days (ending today).
```

**Step 2: Commit**

```bash
git add docs/reference/environment-variables.md
git commit -m "docs: add DEFAULT_RESULTS_LOOKBACK_DAYS environment variable"
```

---

## Task 7: Update CHANGELOG

**Files:**
- Modify: `CHANGELOG.md`

**Step 1: Add entry for breaking change**

Add to the top of `CHANGELOG.md`:

```markdown
## [Unreleased]

### Added
- **Date Range Support in /results Endpoint** - Query multiple dates in single request with period performance metrics
  - `start_date` and `end_date` parameters replace deprecated `date` parameter
  - Returns lightweight format with daily portfolio values and period metrics for date ranges
  - Period metrics: period return %, annualized return %, calendar days, trading days
  - Default to last 30 days when no dates provided (configurable via `DEFAULT_RESULTS_LOOKBACK_DAYS`)
  - Automatic edge trimming when requested range exceeds available data
  - Per-model results grouping
- **Environment Variable:** `DEFAULT_RESULTS_LOOKBACK_DAYS` - Configure default lookback period (default: 30)

### Changed
- **BREAKING:** `/results` endpoint parameter `date` removed - use `start_date`/`end_date` instead
  - Single date: `?start_date=2025-01-16` or `?end_date=2025-01-16`
  - Date range: `?start_date=2025-01-16&end_date=2025-01-20`
  - Old `?date=2025-01-16` now returns 422 error with migration instructions

### Migration Guide

**Before:**
```bash
GET /results?date=2025-01-16&model=gpt-4
```

**After:**
```bash
# Option 1: Use start_date only
GET /results?start_date=2025-01-16&model=gpt-4

# Option 2: Use both (same result for single date)
GET /results?start_date=2025-01-16&end_date=2025-01-16&model=gpt-4

# New: Date range queries
GET /results?start_date=2025-01-16&end_date=2025-01-20&model=gpt-4
```

**Python Client:**
```python
# OLD (will break)
results = client.get_results(date="2025-01-16")

# NEW
results = client.get_results(start_date="2025-01-16")
results = client.get_results(start_date="2025-01-16", end_date="2025-01-20")
```
```

**Step 2: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: add changelog entry for date range support breaking change"
```

---

## Task 8: Update Client Library Examples

**Files:**
- Modify: `API_REFERENCE.md` (Python client section)

**Step 1: Update Python client example**

Find the Python client example in `API_REFERENCE.md` (around line 1008) and update the `get_results` method:

```python
def get_results(self, start_date=None, end_date=None, job_id=None, model=None, reasoning="none"):
    """Query results with optional filters and date range.

    Args:
        start_date: Start date (YYYY-MM-DD) or None
        end_date: End date (YYYY-MM-DD) or None
        job_id: Job ID filter
        model: Model signature filter
        reasoning: Reasoning level (none/summary/full)
    """
    params = {"reasoning": reasoning}
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date
    if job_id:
        params["job_id"] = job_id
    if model:
        params["model"] = model

    response = requests.get(f"{self.base_url}/results", params=params)
    response.raise_for_status()
    return response.json()
```

Update usage examples:

```python
# Single day simulation
job = client.trigger_simulation(end_date="2025-01-16", start_date="2025-01-16", models=["gpt-4"])

# Date range simulation
job = client.trigger_simulation(end_date="2025-01-20", start_date="2025-01-16")

# Wait for completion and get results
result = client.wait_for_completion(job["job_id"])
results = client.get_results(job_id=job["job_id"])

# Get results for date range
range_results = client.get_results(
    start_date="2025-01-16",
    end_date="2025-01-20",
    model="gpt-4"
)
```

**Step 2: Commit**

```bash
git add API_REFERENCE.md
git commit -m "docs: update Python client examples for date range support"
```

---

## Verification

After completing all tasks, run full test suite:

```bash
# Run all tests
pytest tests/ -v

# Run specifically results endpoint tests
pytest tests/api/test_results_v2.py -v

# Run period metrics tests
pytest tests/api/test_period_metrics.py -v
```

Expected: All tests PASS

---

## Notes

- **DRY:** Period metrics calculation is extracted to separate module for reuse
- **YAGNI:** No premature optimization, simple calendar day calculation
- **TDD:** Tests written before implementation for each component
- **Breaking Change:** Clear migration path with helpful error messages
- **Edge Cases:** Handles weekends/gaps, future dates, invalid formats
