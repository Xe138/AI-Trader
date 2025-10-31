"""
Unit tests for api/model_day_executor.py - Single model-day execution.

Coverage target: 90%+

Tests verify:
- Executor initialization
- Trading session execution
- Result persistence to SQLite
- Error handling and recovery
- Position tracking
- AI reasoning logs
"""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path


def create_mock_agent(positions=None, last_trade=None, current_prices=None,
                     reasoning_steps=None, tool_usage=None, session_result=None):
    """Helper to create properly mocked agent."""
    mock_agent = Mock()

    # Default values
    mock_agent.get_positions.return_value = positions or {"CASH": 10000.0}
    mock_agent.get_last_trade.return_value = last_trade
    mock_agent.get_current_prices.return_value = current_prices or {}
    mock_agent.get_reasoning_steps.return_value = reasoning_steps or []
    mock_agent.get_tool_usage.return_value = tool_usage or {}
    mock_agent.run_trading_session.return_value = session_result or {"success": True}

    return mock_agent


@pytest.mark.unit
class TestModelDayExecutorInitialization:
    """Test ModelDayExecutor initialization."""

    def test_init_with_required_params(self, clean_db):
        """Should initialize with required parameters."""
        from api.model_day_executor import ModelDayExecutor

        executor = ModelDayExecutor(
            job_id="test-job-123",
            date="2025-01-16",
            model_sig="gpt-5",
            config_path="configs/test.json",
            db_path=clean_db
        )

        assert executor.job_id == "test-job-123"
        assert executor.date == "2025-01-16"
        assert executor.model_sig == "gpt-5"
        assert executor.config_path == "configs/test.json"

    def test_init_creates_runtime_config(self, clean_db):
        """Should create isolated runtime config file."""
        from api.model_day_executor import ModelDayExecutor

        with patch("api.model_day_executor.RuntimeConfigManager") as mock_runtime:
            mock_instance = Mock()
            mock_instance.create_runtime_config.return_value = "/tmp/runtime_test.json"
            mock_runtime.return_value = mock_instance

            executor = ModelDayExecutor(
                job_id="test-job-123",
                date="2025-01-16",
                model_sig="gpt-5",
                config_path="configs/test.json",
                db_path=clean_db
            )

            # Verify runtime config created
            mock_instance.create_runtime_config.assert_called_once_with(
                job_id="test-job-123",
                model_sig="gpt-5",
                date="2025-01-16"
            )


@pytest.mark.unit
class TestModelDayExecutorExecution:
    """Test trading session execution."""

    def test_execute_success(self, clean_db, sample_job_data):
        """Should execute trading session and write results to DB."""
        from api.model_day_executor import ModelDayExecutor
        from api.job_manager import JobManager

        # Create job and job_detail
        manager = JobManager(db_path=clean_db)
        job_id = manager.create_job(
            config_path="configs/test.json",
            date_range=["2025-01-16"],
            models=["gpt-5"]
        )

        # Mock agent execution
        mock_agent = create_mock_agent(
            positions={"AAPL": 10, "CASH": 7500.0},
            current_prices={"AAPL": 250.0},
            session_result={"success": True, "total_steps": 15, "stop_signal_received": True}
        )

        with patch("api.model_day_executor.RuntimeConfigManager") as mock_runtime:
            mock_instance = Mock()
            mock_instance.create_runtime_config.return_value = "/tmp/runtime_test.json"
            mock_runtime.return_value = mock_instance

            executor = ModelDayExecutor(
                job_id=job_id,
                date="2025-01-16",
                model_sig="gpt-5",
                config_path="configs/test.json",
                db_path=clean_db
            )

            # Mock the _initialize_agent method
            with patch.object(executor, '_initialize_agent', return_value=mock_agent):
                result = executor.execute()

                assert result["success"] is True
                assert result["job_id"] == job_id
                assert result["date"] == "2025-01-16"
                assert result["model"] == "gpt-5"

        # Verify job_detail status updated
        progress = manager.get_job_progress(job_id)
        assert progress["completed"] == 1

    def test_execute_failure_updates_status(self, clean_db):
        """Should update status to failed on execution error."""
        from api.model_day_executor import ModelDayExecutor
        from api.job_manager import JobManager

        # Create job
        manager = JobManager(db_path=clean_db)
        job_id = manager.create_job(
            config_path="configs/test.json",
            date_range=["2025-01-16"],
            models=["gpt-5"]
        )

        # Mock agent to raise error
        with patch("api.model_day_executor.RuntimeConfigManager") as mock_runtime:
            mock_instance = Mock()
            mock_instance.create_runtime_config.return_value = "/tmp/runtime_test.json"
            mock_runtime.return_value = mock_instance

            executor = ModelDayExecutor(
                job_id=job_id,
                date="2025-01-16",
                model_sig="gpt-5",
                config_path="configs/test.json",
                db_path=clean_db
            )

            # Mock _initialize_agent to raise error
            with patch.object(executor, '_initialize_agent', side_effect=Exception("Agent initialization failed")):
                result = executor.execute()

                assert result["success"] is False
                assert "error" in result

        # Verify job_detail marked as failed
        progress = manager.get_job_progress(job_id)
        assert progress["failed"] == 1


@pytest.mark.unit
class TestModelDayExecutorDataPersistence:
    """Test result persistence to SQLite."""

    def test_writes_position_to_database(self, clean_db):
        """Should write position record to SQLite."""
        from api.model_day_executor import ModelDayExecutor
        from api.job_manager import JobManager
        from api.database import get_db_connection

        # Create job
        manager = JobManager(db_path=clean_db)
        job_id = manager.create_job(
            config_path="configs/test.json",
            date_range=["2025-01-16"],
            models=["gpt-5"]
        )

        # Mock successful execution
        mock_agent = create_mock_agent(
            positions={"AAPL": 10, "CASH": 7500.0},
            last_trade={"action": "buy", "symbol": "AAPL", "amount": 10, "price": 250.0},
            current_prices={"AAPL": 250.0},
            session_result={"success": True, "total_steps": 10}
        )

        with patch("api.model_day_executor.RuntimeConfigManager") as mock_runtime:
            mock_instance = Mock()
            mock_instance.create_runtime_config.return_value = "/tmp/runtime_test.json"
            mock_runtime.return_value = mock_instance

            executor = ModelDayExecutor(
                job_id=job_id,
                date="2025-01-16",
                model_sig="gpt-5",
                config_path="configs/test.json",
                db_path=clean_db
            )

            with patch.object(executor, '_initialize_agent', return_value=mock_agent):
                executor.execute()

        # Verify position written to database
        conn = get_db_connection(clean_db)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT job_id, date, model, action_id, action_type
            FROM positions
            WHERE job_id = ? AND date = ? AND model = ?
        """, (job_id, "2025-01-16", "gpt-5"))

        row = cursor.fetchone()
        assert row is not None
        assert row[0] == job_id
        assert row[1] == "2025-01-16"
        assert row[2] == "gpt-5"

        conn.close()

    def test_writes_holdings_to_database(self, clean_db):
        """Should write holdings records to SQLite."""
        from api.model_day_executor import ModelDayExecutor
        from api.job_manager import JobManager
        from api.database import get_db_connection

        # Create job
        manager = JobManager(db_path=clean_db)
        job_id = manager.create_job(
            config_path="configs/test.json",
            date_range=["2025-01-16"],
            models=["gpt-5"]
        )

        # Mock successful execution
        mock_agent = create_mock_agent(
            positions={"AAPL": 10, "MSFT": 5, "CASH": 7500.0},
            current_prices={"AAPL": 250.0, "MSFT": 300.0},
            session_result={"success": True}
        )

        with patch("api.model_day_executor.RuntimeConfigManager") as mock_runtime:
            mock_instance = Mock()
            mock_instance.create_runtime_config.return_value = "/tmp/runtime_test.json"
            mock_runtime.return_value = mock_instance

            executor = ModelDayExecutor(
                job_id=job_id,
                date="2025-01-16",
                model_sig="gpt-5",
                config_path="configs/test.json",
                db_path=clean_db
            )

            with patch.object(executor, '_initialize_agent', return_value=mock_agent):
                executor.execute()

        # Verify holdings written
        conn = get_db_connection(clean_db)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT h.symbol, h.quantity
            FROM holdings h
            JOIN positions p ON h.position_id = p.id
            WHERE p.job_id = ? AND p.date = ? AND p.model = ?
            ORDER BY h.symbol
        """, (job_id, "2025-01-16", "gpt-5"))

        holdings = cursor.fetchall()
        assert len(holdings) == 3
        assert holdings[0][0] == "AAPL"
        assert holdings[0][1] == 10.0

        conn.close()

    def test_writes_reasoning_logs(self, clean_db):
        """Should write AI reasoning logs to SQLite."""
        from api.model_day_executor import ModelDayExecutor
        from api.job_manager import JobManager
        from api.database import get_db_connection

        # Create job
        manager = JobManager(db_path=clean_db)
        job_id = manager.create_job(
            config_path="configs/test.json",
            date_range=["2025-01-16"],
            models=["gpt-5"]
        )

        # Mock execution with reasoning
        mock_agent = create_mock_agent(
            positions={"CASH": 10000.0},
            reasoning_steps=[
                {"step": 1, "reasoning": "Analyzing market data"},
                {"step": 2, "reasoning": "Evaluating risk"}
            ],
            session_result={
                "success": True,
                "total_steps": 5,
                "stop_signal_received": True,
                "reasoning_summary": "Market analysis indicates upward trend"
            }
        )

        with patch("api.model_day_executor.RuntimeConfigManager") as mock_runtime:
            mock_instance = Mock()
            mock_instance.create_runtime_config.return_value = "/tmp/runtime_test.json"
            mock_runtime.return_value = mock_instance

            executor = ModelDayExecutor(
                job_id=job_id,
                date="2025-01-16",
                model_sig="gpt-5",
                config_path="configs/test.json",
                db_path=clean_db
            )

            with patch.object(executor, '_initialize_agent', return_value=mock_agent):
                executor.execute()

        # Verify reasoning logs
        conn = get_db_connection(clean_db)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT step_number, content
            FROM reasoning_logs
            WHERE job_id = ? AND date = ? AND model = ?
            ORDER BY step_number
        """, (job_id, "2025-01-16", "gpt-5"))

        logs = cursor.fetchall()
        assert len(logs) == 2
        assert logs[0][0] == 1

        conn.close()


@pytest.mark.unit
class TestModelDayExecutorCleanup:
    """Test cleanup operations."""

    def test_cleanup_runtime_config_on_success(self, clean_db):
        """Should cleanup runtime config after successful execution."""
        from api.model_day_executor import ModelDayExecutor
        from api.job_manager import JobManager

        manager = JobManager(db_path=clean_db)
        job_id = manager.create_job(
            config_path="configs/test.json",
            date_range=["2025-01-16"],
            models=["gpt-5"]
        )

        mock_agent = create_mock_agent(
            positions={"CASH": 10000.0},
            session_result={"success": True}
        )

        with patch("api.model_day_executor.RuntimeConfigManager") as mock_runtime:
            mock_instance = Mock()
            mock_instance.create_runtime_config.return_value = "/tmp/runtime.json"
            mock_runtime.return_value = mock_instance

            executor = ModelDayExecutor(
                job_id=job_id,
                date="2025-01-16",
                model_sig="gpt-5",
                config_path="configs/test.json",
                db_path=clean_db
            )

            with patch.object(executor, '_initialize_agent', return_value=mock_agent):
                executor.execute()

            # Verify cleanup called
            mock_instance.cleanup_runtime_config.assert_called_once_with("/tmp/runtime.json")

    def test_cleanup_runtime_config_on_failure(self, clean_db):
        """Should cleanup runtime config even after failure."""
        from api.model_day_executor import ModelDayExecutor
        from api.job_manager import JobManager

        manager = JobManager(db_path=clean_db)
        job_id = manager.create_job(
            config_path="configs/test.json",
            date_range=["2025-01-16"],
            models=["gpt-5"]
        )

        with patch("api.model_day_executor.RuntimeConfigManager") as mock_runtime:
            mock_instance = Mock()
            mock_instance.create_runtime_config.return_value = "/tmp/runtime.json"
            mock_runtime.return_value = mock_instance

            executor = ModelDayExecutor(
                job_id=job_id,
                date="2025-01-16",
                model_sig="gpt-5",
                config_path="configs/test.json",
                db_path=clean_db
            )

            # Mock _initialize_agent to raise error
            with patch.object(executor, '_initialize_agent', side_effect=Exception("Agent failed")):
                executor.execute()

            # Verify cleanup called even on failure
            mock_instance.cleanup_runtime_config.assert_called_once_with("/tmp/runtime.json")


@pytest.mark.unit
class TestModelDayExecutorPositionCalculations:
    """Test position and P&L calculations."""

    def test_calculates_portfolio_value(self, clean_db):
        """Should calculate total portfolio value."""
        from api.model_day_executor import ModelDayExecutor
        from api.job_manager import JobManager
        from api.database import get_db_connection

        manager = JobManager(db_path=clean_db)
        job_id = manager.create_job(
            config_path="configs/test.json",
            date_range=["2025-01-16"],
            models=["gpt-5"]
        )

        mock_agent = create_mock_agent(
            positions={"AAPL": 10, "CASH": 7500.0},  # 10 shares @ $250 = $2500
            current_prices={"AAPL": 250.0},
            session_result={"success": True}
        )

        with patch("api.model_day_executor.RuntimeConfigManager") as mock_runtime:
            mock_instance = Mock()
            mock_instance.create_runtime_config.return_value = "/tmp/runtime_test.json"
            mock_runtime.return_value = mock_instance

            executor = ModelDayExecutor(
                job_id=job_id,
                date="2025-01-16",
                model_sig="gpt-5",
                config_path="configs/test.json",
                db_path=clean_db
            )

            with patch.object(executor, '_initialize_agent', return_value=mock_agent):
                executor.execute()

        # Verify portfolio value calculated correctly
        conn = get_db_connection(clean_db)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT portfolio_value
            FROM positions
            WHERE job_id = ? AND date = ? AND model = ?
        """, (job_id, "2025-01-16", "gpt-5"))

        row = cursor.fetchone()
        assert row is not None
        # Portfolio value should be 2500 (stocks) + 7500 (cash) = 10000
        assert row[0] == 10000.0

        conn.close()


# Coverage target: 90%+ for api/model_day_executor.py
