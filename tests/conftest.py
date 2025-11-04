"""
Shared pytest fixtures for AI-Trader API tests.

This module provides reusable fixtures for:
- Test database setup/teardown
- Mock configurations
- Test data factories
"""

import pytest
import tempfile
import os
from pathlib import Path
from api.database import initialize_database, get_db_connection


@pytest.fixture(scope="session")
def test_db_path():
    """Create temporary database file for testing session."""
    temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    temp_db.close()

    yield temp_db.name

    # Cleanup after all tests
    try:
        os.unlink(temp_db.name)
    except FileNotFoundError:
        pass


@pytest.fixture(scope="function")
def clean_db(test_db_path):
    """
    Provide clean database for each test function.

    This fixture:
    1. Initializes schema if needed
    2. Clears all data before test
    3. Returns database path

    Usage:
        def test_something(clean_db):
            conn = get_db_connection(clean_db)
            # ... test code
    """
    # Ensure schema exists (both old initialize_database and new Database class)
    initialize_database(test_db_path)

    # Also ensure new schema exists (trading_days, holdings, actions)
    from api.database import Database
    db = Database(test_db_path)
    db.connection.close()

    # Clear all tables
    conn = get_db_connection(test_db_path)
    cursor = conn.cursor()

    # Get list of tables that exist
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name NOT LIKE 'sqlite_%'
    """)
    tables = [row[0] for row in cursor.fetchall()]

    # Delete in correct order (respecting foreign keys), only if table exists
    if 'tool_usage' in tables:
        cursor.execute("DELETE FROM tool_usage")
    if 'actions' in tables:
        cursor.execute("DELETE FROM actions")
    if 'holdings' in tables:
        cursor.execute("DELETE FROM holdings")
    if 'trading_days' in tables:
        cursor.execute("DELETE FROM trading_days")
    if 'simulation_runs' in tables:
        cursor.execute("DELETE FROM simulation_runs")
    if 'job_details' in tables:
        cursor.execute("DELETE FROM job_details")
    if 'jobs' in tables:
        cursor.execute("DELETE FROM jobs")
    if 'price_data_coverage' in tables:
        cursor.execute("DELETE FROM price_data_coverage")
    if 'price_data' in tables:
        cursor.execute("DELETE FROM price_data")

    conn.commit()
    conn.close()

    return test_db_path


@pytest.fixture
def sample_job_data():
    """Sample job data for testing."""
    return {
        "job_id": "test-job-123",
        "config_path": "configs/test.json",
        "status": "pending",
        "date_range": '["2025-01-16", "2025-01-17"]',
        "models": '["gpt-5", "claude-3.7-sonnet"]',
        "created_at": "2025-01-20T14:30:00Z"
    }


@pytest.fixture
def sample_position_data():
    """Sample position data for testing."""
    return {
        "job_id": "test-job-123",
        "date": "2025-01-16",
        "model": "gpt-5",
        "action_id": 1,
        "action_type": "buy",
        "symbol": "AAPL",
        "amount": 10,
        "price": 255.88,
        "cash": 7441.2,
        "portfolio_value": 10000.0,
        "daily_profit": 0.0,
        "daily_return_pct": 0.0,
        "cumulative_profit": 0.0,
        "cumulative_return_pct": 0.0,
        "created_at": "2025-01-16T09:30:00Z"
    }


@pytest.fixture
def mock_config():
    """Mock configuration for testing."""
    return {
        "agent_type": "BaseAgent",
        "date_range": {
            "init_date": "2025-01-16",
            "end_date": "2025-01-17"
        },
        "models": [
            {
                "name": "test-model",
                "basemodel": "openai/gpt-4",
                "signature": "test-model",
                "enabled": True
            }
        ],
        "agent_config": {
            "max_steps": 10,
            "max_retries": 3,
            "base_delay": 0.5,
            "initial_cash": 10000.0
        },
        "log_config": {
            "log_path": "./data/agent_data"
        }
    }


# Pytest configuration hooks
def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line("markers", "unit: Unit tests (fast, isolated)")
    config.addinivalue_line("markers", "integration: Integration tests (with dependencies)")
    config.addinivalue_line("markers", "performance: Performance and benchmark tests")
    config.addinivalue_line("markers", "security: Security tests")
    config.addinivalue_line("markers", "e2e: End-to-end tests (Docker required)")
    config.addinivalue_line("markers", "slow: Tests that take >10 seconds")
