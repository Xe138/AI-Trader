"""Integration test for duplicate simulation prevention."""
import pytest
import tempfile
import os
import json
from pathlib import Path
from api.job_manager import JobManager
from api.model_day_executor import ModelDayExecutor
from api.database import get_db_connection


pytestmark = pytest.mark.integration


@pytest.fixture
def temp_env(tmp_path):
    """Create temporary environment with db and config."""
    # Create temp database
    db_path = str(tmp_path / "test_jobs.db")

    # Initialize database
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    # Create schema
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            job_id TEXT PRIMARY KEY,
            config_path TEXT NOT NULL,
            status TEXT NOT NULL,
            date_range TEXT NOT NULL,
            models TEXT NOT NULL,
            created_at TEXT NOT NULL,
            started_at TEXT,
            updated_at TEXT,
            completed_at TEXT,
            total_duration_seconds REAL,
            error TEXT,
            warnings TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS job_details (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            date TEXT NOT NULL,
            model TEXT NOT NULL,
            status TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            duration_seconds REAL,
            error TEXT,
            FOREIGN KEY (job_id) REFERENCES jobs(job_id) ON DELETE CASCADE,
            UNIQUE(job_id, date, model)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trading_days (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            model TEXT NOT NULL,
            date TEXT NOT NULL,
            starting_cash REAL NOT NULL,
            ending_cash REAL NOT NULL,
            profit REAL NOT NULL,
            return_pct REAL NOT NULL,
            portfolio_value REAL NOT NULL,
            reasoning_summary TEXT,
            reasoning_full TEXT,
            completed_at TEXT,
            session_duration_seconds REAL,
            UNIQUE(job_id, model, date)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS holdings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trading_day_id INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            FOREIGN KEY (trading_day_id) REFERENCES trading_days(id) ON DELETE CASCADE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trading_day_id INTEGER NOT NULL,
            action_type TEXT NOT NULL,
            symbol TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            price REAL NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (trading_day_id) REFERENCES trading_days(id) ON DELETE CASCADE
        )
    """)

    conn.commit()
    conn.close()

    # Create mock config
    config_path = str(tmp_path / "test_config.json")
    config = {
        "models": [
            {
                "signature": "test-model",
                "basemodel": "mock/model",
                "enabled": True
            }
        ],
        "agent_config": {
            "max_steps": 10,
            "initial_cash": 10000.0
        },
        "log_config": {
            "log_path": str(tmp_path / "logs")
        },
        "date_range": {
            "init_date": "2025-10-13"
        }
    }

    with open(config_path, 'w') as f:
        json.dump(config, f)

    yield {
        "db_path": db_path,
        "config_path": config_path,
        "data_dir": str(tmp_path)
    }


def test_duplicate_simulation_is_skipped(temp_env):
    """Test that overlapping job skips already-completed simulation."""
    manager = JobManager(db_path=temp_env["db_path"])

    # Create first job
    result_1 = manager.create_job(
        config_path=temp_env["config_path"],
        date_range=["2025-10-15"],
        models=["test-model"]
    )
    job_id_1 = result_1["job_id"]

    # Simulate completion by manually inserting trading_day record
    conn = get_db_connection(temp_env["db_path"])
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO trading_days (
            job_id, model, date, starting_cash, ending_cash,
            profit, return_pct, portfolio_value, completed_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        job_id_1,
        "test-model",
        "2025-10-15",
        10000.0,
        9500.0,
        -500.0,
        -5.0,
        9500.0,
        "2025-11-07T01:00:00Z"
    ))

    conn.commit()
    conn.close()

    # Mark job_detail as completed
    manager.update_job_detail_status(
        job_id_1,
        "2025-10-15",
        "test-model",
        "completed"
    )

    # Try to create second job with same model-day
    result_2 = manager.create_job(
        config_path=temp_env["config_path"],
        date_range=["2025-10-15", "2025-10-16"],
        models=["test-model"]
    )

    # Should have warnings about skipped simulation
    assert len(result_2["warnings"]) == 1
    assert "2025-10-15" in result_2["warnings"][0]

    # Should only create job_detail for 2025-10-16
    details = manager.get_job_details(result_2["job_id"])
    assert len(details) == 1
    assert details[0]["date"] == "2025-10-16"


def test_portfolio_continues_from_previous_job(temp_env):
    """Test that new job continues portfolio from previous job's last day."""
    manager = JobManager(db_path=temp_env["db_path"])

    # Create and complete first job
    result_1 = manager.create_job(
        config_path=temp_env["config_path"],
        date_range=["2025-10-13"],
        models=["test-model"]
    )
    job_id_1 = result_1["job_id"]

    # Insert completed trading_day with holdings
    conn = get_db_connection(temp_env["db_path"])
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO trading_days (
            job_id, model, date, starting_cash, ending_cash,
            profit, return_pct, portfolio_value, completed_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        job_id_1,
        "test-model",
        "2025-10-13",
        10000.0,
        5000.0,
        0.0,
        0.0,
        15000.0,
        "2025-11-07T01:00:00Z"
    ))

    trading_day_id = cursor.lastrowid

    cursor.execute("""
        INSERT INTO holdings (trading_day_id, symbol, quantity)
        VALUES (?, ?, ?)
    """, (trading_day_id, "AAPL", 10))

    conn.commit()

    # Mark as completed
    manager.update_job_detail_status(job_id_1, "2025-10-13", "test-model", "completed")
    manager.update_job_status(job_id_1, "completed")

    # Create second job for next day
    result_2 = manager.create_job(
        config_path=temp_env["config_path"],
        date_range=["2025-10-14"],
        models=["test-model"]
    )
    job_id_2 = result_2["job_id"]

    # Get starting position for 2025-10-14
    from agent_tools.tool_trade import get_current_position_from_db
    import agent_tools.tool_trade as trade_module
    original_get_db_connection = trade_module.get_db_connection

    def mock_get_db_connection(path):
        return get_db_connection(temp_env["db_path"])

    trade_module.get_db_connection = mock_get_db_connection

    try:
        position, _ = get_current_position_from_db(
            job_id=job_id_2,
            model="test-model",
            date="2025-10-14",
            initial_cash=10000.0
        )

        # Should continue from job 1's ending position
        assert position["CASH"] == 5000.0
        assert position["AAPL"] == 10
    finally:
        # Restore original function
        trade_module.get_db_connection = original_get_db_connection

    conn.close()
