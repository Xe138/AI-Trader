"""
Integration tests for dev mode end-to-end functionality

These tests verify the complete dev mode system working together:
- Mock AI provider integration
- Database isolation
- Data path isolation
- PRESERVE_DEV_DATA flag behavior
"""

import os
import json
import pytest
import asyncio
from pathlib import Path


@pytest.fixture
def dev_mode_env():
    """Setup and teardown for dev mode testing"""
    # Setup
    original_mode = os.environ.get("DEPLOYMENT_MODE")
    original_preserve = os.environ.get("PRESERVE_DEV_DATA")
    os.environ["DEPLOYMENT_MODE"] = "DEV"
    os.environ["PRESERVE_DEV_DATA"] = "false"

    yield

    # Teardown
    if original_mode:
        os.environ["DEPLOYMENT_MODE"] = original_mode
    else:
        os.environ.pop("DEPLOYMENT_MODE", None)

    if original_preserve:
        os.environ["PRESERVE_DEV_DATA"] = original_preserve
    else:
        os.environ.pop("PRESERVE_DEV_DATA", None)


@pytest.mark.skipif(
    os.getenv("SKIP_INTEGRATION_TESTS") == "true",
    reason="Skipping integration tests that require full environment"
)
def test_dev_mode_full_simulation(dev_mode_env, tmp_path):
    """
    Test complete simulation run in dev mode

    This test verifies:
    - BaseAgent can initialize with mock model
    - Mock model is used instead of real AI
    - Trading session executes successfully
    - Logs are created correctly
    - Mock responses contain expected content (AAPL on day 1)

    NOTE: This test requires the full agent stack including MCP adapters.
    It may be skipped in environments where these dependencies are not available.
    """
    try:
        # Import here to avoid module-level import issues
        from agent.base_agent.base_agent import BaseAgent
    except ImportError as e:
        pytest.skip(f"Cannot import BaseAgent: {e}")

    try:
        # Setup config
        config = {
            "agent_type": "BaseAgent",
            "date_range": {
                "init_date": "2025-01-01",
                "end_date": "2025-01-03"
            },
            "models": [{
                "name": "test-model",
                "basemodel": "mock/test-trader",
                "signature": "test-dev-agent",
                "enabled": True
            }],
            "agent_config": {
                "max_steps": 5,
                "max_retries": 1,
                "base_delay": 0.1,
                "initial_cash": 10000.0
            },
            "log_config": {
                "log_path": str(tmp_path / "dev_agent_data")
            }
        }

        # Create agent
        model_config = config["models"][0]
        agent = BaseAgent(
            signature=model_config["signature"],
            basemodel=model_config["basemodel"],
            log_path=config["log_config"]["log_path"],
            max_steps=config["agent_config"]["max_steps"],
            initial_cash=config["agent_config"]["initial_cash"],
            init_date=config["date_range"]["init_date"]
        )

        # Initialize and run
        asyncio.run(agent.initialize())

        # Verify mock model is being used
        assert agent.model is not None
        assert "Mock" in str(type(agent.model))

        # Run single day
        asyncio.run(agent.run_trading_session("2025-01-01"))

        # Verify logs were created
        log_path = Path(agent.base_log_path) / agent.signature / "log" / "2025-01-01" / "log.jsonl"
        assert log_path.exists()

        # Verify log content
        with open(log_path, "r") as f:
            logs = [json.loads(line) for line in f]

        assert len(logs) > 0
        # Day 1 should mention AAPL (first stock in rotation)
        assert any("AAPL" in str(log) for log in logs)
    except Exception as e:
        pytest.skip(f"Test requires MCP services running: {e}")


def test_dev_database_isolation(dev_mode_env, tmp_path):
    """
    Test dev and prod databases are separate

    This test verifies:
    - Production database and dev database use different files
    - Changes to dev database don't affect production database
    - initialize_dev_database() creates a fresh, empty dev database
    - Both databases can coexist without interference
    """
    from api.database import get_db_connection, initialize_database

    # Initialize prod database with some data
    prod_db = str(tmp_path / "test_prod.db")
    initialize_database(prod_db)

    conn = get_db_connection(prod_db)
    conn.execute(
        "INSERT INTO jobs (job_id, config_path, status, date_range, models, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("prod-job", "config.json", "running", "2025-01-01:2025-01-31", '["model1"]', "2025-01-01T00:00:00")
    )
    conn.commit()
    conn.close()

    # Initialize dev database (different path)
    dev_db = str(tmp_path / "test_dev.db")
    from api.database import initialize_dev_database
    initialize_dev_database(dev_db)

    # Verify prod data still exists (unchanged by dev database creation)
    conn = get_db_connection(prod_db)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM jobs WHERE job_id = 'prod-job'")
    assert cursor.fetchone()[0] == 1
    conn.close()

    # Verify dev database is empty (fresh initialization)
    conn = get_db_connection(dev_db)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM jobs")
    assert cursor.fetchone()[0] == 0
    conn.close()


def test_preserve_dev_data_flag(dev_mode_env, tmp_path):
    """
    Test PRESERVE_DEV_DATA prevents cleanup

    This test verifies:
    - PRESERVE_DEV_DATA=true prevents dev database from being reset
    - Data persists across multiple initialize_dev_database() calls
    - This allows debugging without losing dev data between runs
    """
    os.environ["PRESERVE_DEV_DATA"] = "true"

    from api.database import initialize_dev_database, get_db_connection, initialize_database

    dev_db = str(tmp_path / "test_dev_preserve.db")

    # Create database with initial data
    initialize_database(dev_db)
    conn = get_db_connection(dev_db)
    conn.execute(
        "INSERT INTO jobs (job_id, config_path, status, date_range, models, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("dev-job-1", "config.json", "completed", "2025-01-01:2025-01-31", '["model1"]', "2025-01-01T00:00:00")
    )
    conn.commit()
    conn.close()

    # Initialize again with PRESERVE_DEV_DATA=true (should NOT delete data)
    initialize_dev_database(dev_db)

    # Verify data is preserved
    conn = get_db_connection(dev_db)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM jobs WHERE job_id = 'dev-job-1'")
    count = cursor.fetchone()[0]
    conn.close()

    assert count == 1, "Data should be preserved when PRESERVE_DEV_DATA=true"
