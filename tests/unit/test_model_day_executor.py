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
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from pathlib import Path


def create_mock_agent(reasoning_steps=None, tool_usage=None, session_result=None,
                     conversation_history=None):
    """Helper to create properly mocked agent."""
    mock_agent = Mock()

    # Note: Removed get_positions, get_last_trade, get_current_prices
    # These methods don't exist in BaseAgent and were only used by
    # the now-deleted _write_results_to_db() method

    mock_agent.get_reasoning_steps.return_value = reasoning_steps or []
    mock_agent.get_tool_usage.return_value = tool_usage or {}
    mock_agent.get_conversation_history.return_value = conversation_history or []

    # Async methods - use AsyncMock
    mock_agent.set_context = AsyncMock()
    mock_agent.run_trading_session = AsyncMock(return_value=session_result or {"success": True})
    mock_agent.generate_summary = AsyncMock(return_value="Mock summary")
    mock_agent.summarize_message = AsyncMock(return_value="Mock message summary")

    # Mock model for summary generation
    mock_agent.model = Mock()

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

    def test_execute_success(self, clean_db, sample_job_data, tmp_path):
        """Should execute trading session and write results to DB."""
        from api.model_day_executor import ModelDayExecutor
        from api.job_manager import JobManager
        import json

        # Create a temporary config file
        config_path = tmp_path / "test_config.json"
        config_data = {
            "agent_type": "BaseAgent",
            "models": [],
            "agent_config": {
                "initial_cash": 10000.0
            }
        }
        config_path.write_text(json.dumps(config_data))

        # Create job and job_detail
        manager = JobManager(db_path=clean_db)
        job_id = manager.create_job(
            config_path=str(config_path),
            date_range=["2025-01-16"],
            models=["gpt-5"]
        )

        # Mock agent execution
        mock_agent = create_mock_agent(
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
                config_path=str(config_path),
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

    def test_creates_initial_position(self, clean_db, tmp_path):
        """Should create initial position record (action_id=0) on first day."""
        from api.model_day_executor import ModelDayExecutor
        from api.job_manager import JobManager
        from api.database import get_db_connection
        import json

        # Create a temporary config file
        config_path = tmp_path / "test_config.json"
        config_data = {
            "agent_type": "BaseAgent",
            "models": [],
            "agent_config": {
                "initial_cash": 10000.0
            }
        }
        config_path.write_text(json.dumps(config_data))

        # Create job
        manager = JobManager(db_path=clean_db)
        job_id = manager.create_job(
            config_path=str(config_path),
            date_range=["2025-01-16"],
            models=["gpt-5"]
        )

        # Mock successful execution (no trades)
        mock_agent = create_mock_agent(
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
                config_path=str(config_path),
                db_path=clean_db
            )

            with patch.object(executor, '_initialize_agent', return_value=mock_agent):
                executor.execute()

        # Verify initial position created (action_id=0)
        conn = get_db_connection(clean_db)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT job_id, date, model, action_id, action_type, cash, portfolio_value
            FROM positions
            WHERE job_id = ? AND date = ? AND model = ?
        """, (job_id, "2025-01-16", "gpt-5"))

        row = cursor.fetchone()
        assert row is not None, "Should create initial position record"
        assert row[0] == job_id
        assert row[1] == "2025-01-16"
        assert row[2] == "gpt-5"
        assert row[3] == 0, "Initial position should have action_id=0"
        assert row[4] == "no_trade"
        assert row[5] == 10000.0, "Initial cash should be $10,000"
        assert row[6] == 10000.0, "Initial portfolio value should be $10,000"

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

        # NOTE: Reasoning logs are now stored differently (see test_model_day_executor_reasoning.py)
        # This test is deprecated but kept to ensure backward compatibility
        pytest.skip("Test deprecated - reasoning logs schema changed. See test_model_day_executor_reasoning.py")


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

    @pytest.mark.skip(reason="Method _calculate_portfolio_value() removed - portfolio value calculated by trade tools")
    def test_calculates_portfolio_value(self, clean_db):
        """DEPRECATED: Portfolio value is now calculated by trade tools, not ModelDayExecutor."""
        pass


# Coverage target: 90%+ for api/model_day_executor.py
