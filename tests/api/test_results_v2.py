"""Tests for results_v2 endpoint date validation."""

import pytest
import json
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from api.routes.results_v2 import validate_and_resolve_dates
from api.main import create_app
from api.database import Database


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


@pytest.fixture
def test_db(tmp_path):
    """Create test database with sample data."""
    db_path = str(tmp_path / "test.db")
    db = Database(db_path)

    # Create a job first (required by foreign key constraint)
    db.connection.execute(
        """
        INSERT INTO jobs (job_id, config_path, date_range, models, status, created_at)
        VALUES (?, ?, ?, ?, ?, datetime('now'))
        """,
        ("test-job-1", "config.json", '["2024-01-16", "2024-01-17"]', '["gpt-4"]', "completed")
    )
    db.connection.commit()

    # Create sample trading days (use dates in the past)
    trading_day_id_1 = db.create_trading_day(
        job_id="test-job-1",
        model="gpt-4",
        date="2024-01-16",
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

    db.create_holding(trading_day_id_1, "AAPL", 10)
    db.create_action(trading_day_id_1, "buy", "AAPL", 10, 150.0)

    trading_day_id_2 = db.create_trading_day(
        job_id="test-job-1",
        model="gpt-4",
        date="2024-01-17",
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

    db.create_holding(trading_day_id_2, "AAPL", 10)

    return db


def test_get_results_single_date(test_db):
    """Test single date query returns detailed format."""
    app = create_app(db_path=test_db.db_path)
    app.state.test_mode = True

    # Override the database dependency to use our test database
    from api.routes.results_v2 import get_database

    def override_get_database():
        return test_db

    app.dependency_overrides[get_database] = override_get_database

    client = TestClient(app)

    response = client.get("/results?start_date=2024-01-16&end_date=2024-01-16")

    assert response.status_code == 200
    data = response.json()

    assert data["count"] == 1
    assert len(data["results"]) == 1

    result = data["results"][0]
    assert result["date"] == "2024-01-16"
    assert result["model"] == "gpt-4"
    assert "starting_position" in result
    assert "daily_metrics" in result
    assert "trades" in result
    assert "final_position" in result


def test_get_results_date_range(test_db):
    """Test date range query returns metrics format."""
    app = create_app(db_path=test_db.db_path)
    app.state.test_mode = True

    # Override the database dependency to use our test database
    from api.routes.results_v2 import get_database

    def override_get_database():
        return test_db

    app.dependency_overrides[get_database] = override_get_database

    client = TestClient(app)

    response = client.get("/results?start_date=2024-01-16&end_date=2024-01-17")

    assert response.status_code == 200
    data = response.json()

    assert data["count"] == 1
    assert len(data["results"]) == 1

    result = data["results"][0]
    assert result["model"] == "gpt-4"
    assert result["start_date"] == "2024-01-16"
    assert result["end_date"] == "2024-01-17"
    assert "daily_portfolio_values" in result
    assert "period_metrics" in result

    # Check daily values
    daily_values = result["daily_portfolio_values"]
    assert len(daily_values) == 2
    assert daily_values[0]["date"] == "2024-01-16"
    assert daily_values[0]["portfolio_value"] == 10100.0
    assert daily_values[1]["date"] == "2024-01-17"
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

    # Override the database dependency to use our test database
    from api.routes.results_v2 import get_database

    def override_get_database():
        return test_db

    app.dependency_overrides[get_database] = override_get_database

    client = TestClient(app)

    response = client.get("/results?start_date=2024-02-01&end_date=2024-02-05")

    assert response.status_code == 404
    assert "No trading data found" in response.json()["detail"]
