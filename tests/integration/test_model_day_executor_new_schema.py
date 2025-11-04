"""Test model_day_executor uses new schema exclusively."""

import pytest
from api.model_day_executor import ModelDayExecutor
from api.database import Database


@pytest.mark.asyncio
async def test_executor_writes_only_to_new_schema(tmp_path, monkeypatch):
    """Verify executor writes to trading_days, not old tables."""

    # Create test database
    db_path = str(tmp_path / "test.db")
    db = Database(db_path)

    # Create jobs and job_details tables (required by ModelDayExecutor)
    db.connection.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            job_id TEXT PRIMARY KEY,
            config_path TEXT NOT NULL,
            status TEXT NOT NULL,
            date_range TEXT NOT NULL,
            models TEXT NOT NULL,
            created_at TEXT NOT NULL,
            started_at TEXT,
            updated_at TEXT,
            completed_at TEXT
        )
    """)

    db.connection.execute("""
        CREATE TABLE IF NOT EXISTS job_details (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            date TEXT NOT NULL,
            model TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT,
            updated_at TEXT,
            started_at TEXT,
            completed_at TEXT,
            duration_seconds REAL,
            error TEXT,
            FOREIGN KEY (job_id) REFERENCES jobs(job_id)
        )
    """)

    # Create job records (prerequisite)
    db.connection.execute("""
        INSERT INTO jobs (job_id, status, created_at, config_path, date_range, models)
        VALUES ('test-job-123', 'running', '2025-01-15T10:00:00Z', 'test_config.json',
                '{"start": "2025-01-15", "end": "2025-01-15"}', '["test-model"]')
    """)

    db.connection.execute("""
        INSERT INTO job_details (job_id, date, model, status)
        VALUES ('test-job-123', '2025-01-15', 'test-model', 'pending')
    """)

    db.connection.commit()

    # Create test config
    config_path = str(tmp_path / "config.json")
    import json
    with open(config_path, 'w') as f:
        json.dump({
            "models": [{
                "signature": "test-model",
                "basemodel": "gpt-3.5-turbo",
                "enabled": True
            }],
            "agent_config": {
                "stock_symbols": ["AAPL"],
                "initial_cash": 10000.0,
                "max_steps": 10
            },
            "log_config": {"log_path": str(tmp_path / "logs")}
        }, f)

    # Mock agent initialization and execution
    from unittest.mock import AsyncMock, MagicMock, patch
    mock_agent = MagicMock()

    # Mock agent to create trading_day record when run
    async def mock_run_trading_session(date):
        # Simulate BaseAgent creating trading_day record
        trading_day_id = db.create_trading_day(
            job_id='test-job-123',
            model='test-model',
            date='2025-01-15',
            starting_cash=10000.0,
            starting_portfolio_value=10000.0,
            daily_profit=0.0,
            daily_return_pct=0.0,
            ending_cash=10000.0,
            ending_portfolio_value=10000.0,
            days_since_last_trading=0
        )
        db.connection.commit()
        return {"success": True}

    mock_agent.run_trading_session = mock_run_trading_session
    mock_agent.get_conversation_history = MagicMock(return_value=[])
    mock_agent.initialize = AsyncMock()
    mock_agent.set_context = AsyncMock()

    async def mock_init_agent(self):
        return mock_agent

    monkeypatch.setattr('api.model_day_executor.ModelDayExecutor._initialize_agent',
                       mock_init_agent)

    # Mock get_config_value to return None for TRADING_DAY_ID (not yet implemented)
    monkeypatch.setattr('tools.general_tools.get_config_value',
                       lambda key: None if key == 'TRADING_DAY_ID' else 'test-value')

    # Execute
    executor = ModelDayExecutor(
        job_id='test-job-123',
        date='2025-01-15',
        model_sig='test-model',
        config_path=config_path,
        db_path=db_path
    )

    result = await executor.execute_async()

    # Verify: trading_days record exists
    cursor = db.connection.execute("""
        SELECT COUNT(*) FROM trading_days
        WHERE job_id = ? AND date = ? AND model = ?
    """, ('test-job-123', '2025-01-15', 'test-model'))

    count = cursor.fetchone()[0]
    assert count == 1, "Should have exactly one trading_days record"

    # Verify: NO trading_sessions records
    cursor = db.connection.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='trading_sessions'
    """)
    assert cursor.fetchone() is None, "trading_sessions table should not exist"

    # Verify: NO reasoning_logs records
    cursor = db.connection.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='reasoning_logs'
    """)
    assert cursor.fetchone() is None, "reasoning_logs table should not exist"
