"""
Unit tests for api/simulation_worker.py - Job orchestration.

Coverage target: 90%+

Tests verify:
- Worker initialization
- Job execution orchestration
- Date-sequential, model-parallel execution
- Error handling and partial completion
- Job status updates
"""

import pytest
from unittest.mock import Mock, patch, call
from datetime import datetime


@pytest.mark.unit
class TestSimulationWorkerInitialization:
    """Test SimulationWorker initialization."""

    def test_init_with_job_id(self, clean_db):
        """Should initialize with job ID."""
        from api.simulation_worker import SimulationWorker

        worker = SimulationWorker(job_id="test-job-123", db_path=clean_db)

        assert worker.job_id == "test-job-123"
        assert worker.db_path == clean_db


@pytest.mark.unit
class TestSimulationWorkerExecution:
    """Test job execution orchestration."""

    def test_run_executes_all_model_days(self, clean_db):
        """Should execute all model-day combinations."""
        from api.simulation_worker import SimulationWorker
        from api.job_manager import JobManager

        # Create job with 2 dates and 2 models = 4 model-days
        manager = JobManager(db_path=clean_db)
        job_id = manager.create_job(
            config_path="configs/test.json",
            date_range=["2025-01-16", "2025-01-17"],
            models=["gpt-5", "claude-3.7-sonnet"]
        )

        worker = SimulationWorker(job_id=job_id, db_path=clean_db)

        # Mock ModelDayExecutor
        with patch("api.simulation_worker.ModelDayExecutor") as mock_executor_class:
            mock_executor = Mock()
            mock_executor.execute.return_value = {"success": True}
            mock_executor_class.return_value = mock_executor

            worker.run()

            # Should have created 4 executors (2 dates × 2 models)
            assert mock_executor_class.call_count == 4

    def test_run_date_sequential_execution(self, clean_db):
        """Should execute dates sequentially, models in parallel."""
        from api.simulation_worker import SimulationWorker
        from api.job_manager import JobManager

        manager = JobManager(db_path=clean_db)
        job_id = manager.create_job(
            config_path="configs/test.json",
            date_range=["2025-01-16", "2025-01-17"],
            models=["gpt-5", "claude-3.7-sonnet"]
        )

        worker = SimulationWorker(job_id=job_id, db_path=clean_db)

        execution_order = []

        def track_execution(job_id, date, model_sig, config_path, db_path):
            executor = Mock()
            execution_order.append((date, model_sig))
            executor.execute.return_value = {"success": True}
            return executor

        with patch("api.simulation_worker.ModelDayExecutor", side_effect=track_execution):
            worker.run()

        # All 2025-01-16 executions should come before 2025-01-17
        date_16_executions = [e for e in execution_order if e[0] == "2025-01-16"]
        date_17_executions = [e for e in execution_order if e[0] == "2025-01-17"]

        assert len(date_16_executions) == 2
        assert len(date_17_executions) == 2

        # Find last index of date 16 and first index of date 17
        last_16_idx = max(i for i, e in enumerate(execution_order) if e[0] == "2025-01-16")
        first_17_idx = min(i for i, e in enumerate(execution_order) if e[0] == "2025-01-17")

        assert last_16_idx < first_17_idx

    def test_run_updates_job_status_to_completed(self, clean_db):
        """Should update job status to completed on success."""
        from api.simulation_worker import SimulationWorker
        from api.job_manager import JobManager

        manager = JobManager(db_path=clean_db)
        job_id = manager.create_job(
            config_path="configs/test.json",
            date_range=["2025-01-16"],
            models=["gpt-5"]
        )

        worker = SimulationWorker(job_id=job_id, db_path=clean_db)

        with patch("api.simulation_worker.ModelDayExecutor") as mock_executor_class:
            mock_executor = Mock()
            mock_executor.execute.return_value = {"success": True}
            mock_executor_class.return_value = mock_executor

            worker.run()

        # Check job status
        job = manager.get_job(job_id)
        assert job["status"] == "completed"

    def test_run_handles_partial_failure(self, clean_db):
        """Should mark job as partial when some models fail."""
        from api.simulation_worker import SimulationWorker
        from api.job_manager import JobManager

        manager = JobManager(db_path=clean_db)
        job_id = manager.create_job(
            config_path="configs/test.json",
            date_range=["2025-01-16"],
            models=["gpt-5", "claude-3.7-sonnet"]
        )

        worker = SimulationWorker(job_id=job_id, db_path=clean_db)

        call_count = 0

        def mixed_results(*args, **kwargs):
            nonlocal call_count
            executor = Mock()
            # First model succeeds, second fails
            executor.execute.return_value = {"success": call_count == 0}
            call_count += 1
            return executor

        with patch("api.simulation_worker.ModelDayExecutor", side_effect=mixed_results):
            worker.run()

        # Check job status
        job = manager.get_job(job_id)
        assert job["status"] == "partial"


@pytest.mark.unit
class TestSimulationWorkerErrorHandling:
    """Test error handling."""

    def test_run_continues_on_single_model_failure(self, clean_db):
        """Should continue executing other models if one fails."""
        from api.simulation_worker import SimulationWorker
        from api.job_manager import JobManager

        manager = JobManager(db_path=clean_db)
        job_id = manager.create_job(
            config_path="configs/test.json",
            date_range=["2025-01-16"],
            models=["gpt-5", "claude-3.7-sonnet", "gemini"]
        )

        worker = SimulationWorker(job_id=job_id, db_path=clean_db)

        execution_count = 0

        def counting_executor(*args, **kwargs):
            nonlocal execution_count
            execution_count += 1
            executor = Mock()
            # Second model fails
            if execution_count == 2:
                executor.execute.return_value = {"success": False, "error": "Model failed"}
            else:
                executor.execute.return_value = {"success": True}
            return executor

        with patch("api.simulation_worker.ModelDayExecutor", side_effect=counting_executor):
            worker.run()

        # All 3 models should have been executed
        assert execution_count == 3

    def test_run_updates_job_to_failed_on_exception(self, clean_db):
        """Should update job to failed on unexpected exception."""
        from api.simulation_worker import SimulationWorker
        from api.job_manager import JobManager

        manager = JobManager(db_path=clean_db)
        job_id = manager.create_job(
            config_path="configs/test.json",
            date_range=["2025-01-16"],
            models=["gpt-5"]
        )

        worker = SimulationWorker(job_id=job_id, db_path=clean_db)

        with patch("api.simulation_worker.ModelDayExecutor", side_effect=Exception("Unexpected error")):
            worker.run()

        # Check job status
        job = manager.get_job(job_id)
        assert job["status"] == "failed"
        assert "Unexpected error" in job["error"]


@pytest.mark.unit
class TestSimulationWorkerConcurrency:
    """Test concurrent execution handling."""

    def test_run_with_threading(self, clean_db):
        """Should use threading for parallel model execution."""
        from api.simulation_worker import SimulationWorker
        from api.job_manager import JobManager

        manager = JobManager(db_path=clean_db)
        job_id = manager.create_job(
            config_path="configs/test.json",
            date_range=["2025-01-16"],
            models=["gpt-5", "claude-3.7-sonnet"]
        )

        worker = SimulationWorker(job_id=job_id, db_path=clean_db)

        with patch("api.simulation_worker.ModelDayExecutor") as mock_executor_class:
            mock_executor = Mock()
            mock_executor.execute.return_value = {"success": True}
            mock_executor_class.return_value = mock_executor

            # Mock ThreadPoolExecutor to verify it's being used
            with patch("api.simulation_worker.ThreadPoolExecutor") as mock_pool:
                mock_pool_instance = Mock()
                mock_pool.return_value.__enter__.return_value = mock_pool_instance
                mock_pool_instance.submit.return_value = Mock(result=lambda: {"success": True})

                worker.run()

                # Verify ThreadPoolExecutor was used
                mock_pool.assert_called_once()


@pytest.mark.unit
class TestSimulationWorkerJobRetrieval:
    """Test job information retrieval."""

    def test_get_job_info(self, clean_db):
        """Should retrieve job information."""
        from api.simulation_worker import SimulationWorker
        from api.job_manager import JobManager

        manager = JobManager(db_path=clean_db)
        job_id = manager.create_job(
            config_path="configs/test.json",
            date_range=["2025-01-16", "2025-01-17"],
            models=["gpt-5"]
        )

        worker = SimulationWorker(job_id=job_id, db_path=clean_db)
        job_info = worker.get_job_info()

        assert job_info["job_id"] == job_id
        assert job_info["date_range"] == ["2025-01-16", "2025-01-17"]
        assert job_info["models"] == ["gpt-5"]


# Coverage target: 90%+ for api/simulation_worker.py
