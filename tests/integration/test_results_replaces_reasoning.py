"""Verify /results endpoint replaces /reasoning endpoint."""

import pytest
from fastapi.testclient import TestClient
from api.main import create_app
from api.database import Database


def test_results_with_full_reasoning_replaces_old_endpoint(tmp_path):
    """Test /results?reasoning=full provides same data as old /reasoning."""

    # Create test database with file path (not in-memory, to avoid sharing issues)
    import json
    db_path = str(tmp_path / "test.db")
    db = Database(db_path)

    # Create job first
    db.connection.execute("""
        INSERT INTO jobs (job_id, config_path, status, date_range, models, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, ('test-job-123', 'test_config.json', 'completed',
          json.dumps({'init_date': '2025-01-15', 'end_date': '2025-01-15'}),
          json.dumps(['test-model']), '2025-01-15T10:00:00Z'))
    db.connection.commit()

    trading_day_id = db.create_trading_day(
        job_id='test-job-123',
        model='test-model',
        date='2025-01-15',
        starting_cash=10000.0,
        starting_portfolio_value=10000.0,
        ending_cash=8500.0,
        ending_portfolio_value=10000.0,
        daily_profit=0.0,
        daily_return_pct=0.0,
        days_since_last_trading=0
    )

    # Add actions
    db.create_action(trading_day_id, 'buy', 'AAPL', 10, 150.0)

    # Add holdings
    db.create_holding(trading_day_id, 'AAPL', 10)

    # Update with reasoning
    db.connection.execute("""
        UPDATE trading_days
        SET reasoning_summary = 'Bought AAPL based on earnings',
            reasoning_full = ?,
            total_actions = 1
        WHERE id = ?
    """, (json.dumps([
        {"role": "user", "content": "System prompt"},
        {"role": "assistant", "content": "I will buy AAPL"}
    ]), trading_day_id))

    db.connection.commit()
    db.connection.close()

    # Create test app with the test database
    app = create_app(db_path=db_path)
    app.state.test_mode = True

    # Override the database dependency to use our test database
    from api.routes.results_v2 import get_database

    def override_get_database():
        return Database(db_path)

    app.dependency_overrides[get_database] = override_get_database

    client = TestClient(app)

    # Query new endpoint with explicit date to avoid default lookback filter
    response = client.get("/results?job_id=test-job-123&start_date=2025-01-15&end_date=2025-01-15&reasoning=full")

    assert response.status_code == 200
    data = response.json()

    # Verify structure matches old endpoint needs
    assert data['count'] == 1
    result = data['results'][0]

    assert result['date'] == '2025-01-15'
    assert result['model'] == 'test-model'
    assert result['trades'][0]['action_type'] == 'buy'
    assert result['trades'][0]['symbol'] == 'AAPL'
    assert isinstance(result['reasoning'], list)
    assert len(result['reasoning']) == 2


def test_reasoning_endpoint_returns_404():
    """Verify /reasoning endpoint is removed."""

    app = create_app(db_path=":memory:")
    client = TestClient(app)

    response = client.get("/reasoning?job_id=test-job-123")

    assert response.status_code == 404
