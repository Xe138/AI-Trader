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


@pytest.mark.unit
class TestSimulationWorkerHelperMethods:
    """Test worker helper methods."""

    def test_download_price_data_success(self, clean_db):
        """Test successful price data download."""
        from api.simulation_worker import SimulationWorker
        from api.database import initialize_database

        db_path = clean_db
        initialize_database(db_path)

        worker = SimulationWorker(job_id="test-123", db_path=db_path)

        # Mock price manager
        mock_price_manager = Mock()
        mock_price_manager.download_missing_data_prioritized.return_value = {
            "downloaded": ["AAPL", "MSFT"],
            "failed": [],
            "rate_limited": False
        }

        warnings = []
        missing_coverage = {"AAPL": {"2025-10-01"}, "MSFT": {"2025-10-01"}}

        worker._download_price_data(mock_price_manager, missing_coverage, ["2025-10-01"], warnings)

        # Verify download was called
        mock_price_manager.download_missing_data_prioritized.assert_called_once()

        # No warnings for successful download
        assert len(warnings) == 0

    def test_download_price_data_rate_limited(self, clean_db):
        """Test price download with rate limit."""
        from api.simulation_worker import SimulationWorker
        from api.database import initialize_database

        db_path = clean_db
        initialize_database(db_path)

        worker = SimulationWorker(job_id="test-456", db_path=db_path)

        # Mock price manager
        mock_price_manager = Mock()
        mock_price_manager.download_missing_data_prioritized.return_value = {
            "downloaded": ["AAPL"],
            "failed": ["MSFT"],
            "rate_limited": True
        }

        warnings = []
        missing_coverage = {"AAPL": {"2025-10-01"}, "MSFT": {"2025-10-01"}}

        worker._download_price_data(mock_price_manager, missing_coverage, ["2025-10-01"], warnings)

        # Should add rate limit warning
        assert len(warnings) == 1
        assert "Rate limit" in warnings[0]

    def test_filter_completed_dates_all_new(self, clean_db):
        """Test filtering when no dates are completed."""
        from api.simulation_worker import SimulationWorker
        from api.database import initialize_database

        db_path = clean_db
        initialize_database(db_path)

        worker = SimulationWorker(job_id="test-789", db_path=db_path)

        # Mock job_manager to return empty completed dates
        mock_job_manager = Mock()
        mock_job_manager.get_completed_model_dates.return_value = {}
        worker.job_manager = mock_job_manager

        available_dates = ["2025-10-01", "2025-10-02"]
        models = ["gpt-5"]

        result = worker._filter_completed_dates(available_dates, models)

        # All dates should be returned
        assert result == available_dates

    def test_filter_completed_dates_some_completed(self, clean_db):
        """Test filtering when some dates are completed."""
        from api.simulation_worker import SimulationWorker
        from api.database import initialize_database

        db_path = clean_db
        initialize_database(db_path)

        worker = SimulationWorker(job_id="test-abc", db_path=db_path)

        # Mock job_manager to return one completed date
        mock_job_manager = Mock()
        mock_job_manager.get_completed_model_dates.return_value = {
            "gpt-5": ["2025-10-01"]
        }
        worker.job_manager = mock_job_manager

        available_dates = ["2025-10-01", "2025-10-02", "2025-10-03"]
        models = ["gpt-5"]

        result = worker._filter_completed_dates(available_dates, models)

        # Should exclude completed date
        assert result == ["2025-10-02", "2025-10-03"]

    def test_add_job_warnings(self, clean_db):
        """Test adding warnings to job via worker."""
        from api.simulation_worker import SimulationWorker
        from api.job_manager import JobManager
        from api.database import initialize_database
        import json

        db_path = clean_db
        initialize_database(db_path)
        job_manager = JobManager(db_path=db_path)

        # Create job
        job_id = job_manager.create_job(
            config_path="config.json",
            date_range=["2025-10-01"],
            models=["gpt-5"]
        )

        worker = SimulationWorker(job_id=job_id, db_path=db_path)

        # Add warnings
        warnings = ["Warning 1", "Warning 2"]
        worker._add_job_warnings(warnings)

        # Verify warnings were stored
        job = job_manager.get_job(job_id)
        assert job["warnings"] is not None
        stored_warnings = json.loads(job["warnings"])
        assert stored_warnings == warnings

    def test_prepare_data_no_missing_data(self, clean_db, monkeypatch):
        """Test prepare_data when all data is available."""
        from api.simulation_worker import SimulationWorker
        from api.job_manager import JobManager
        from api.database import initialize_database

        db_path = clean_db
        initialize_database(db_path)
        job_manager = JobManager(db_path=db_path)

        # Create job
        job_id = job_manager.create_job(
            config_path="config.json",
            date_range=["2025-10-01"],
            models=["gpt-5"]
        )

        worker = SimulationWorker(job_id=job_id, db_path=db_path)

        # Mock PriceDataManager
        mock_price_manager = Mock()
        mock_price_manager.get_missing_coverage.return_value = {}  # No missing data
        mock_price_manager.get_available_trading_dates.return_value = ["2025-10-01"]

        # Patch PriceDataManager import where it's used
        def mock_pdm_init(db_path):
            return mock_price_manager

        monkeypatch.setattr("api.price_data_manager.PriceDataManager", mock_pdm_init)

        # Mock get_completed_model_dates
        worker.job_manager.get_completed_model_dates = Mock(return_value={})

        # Execute
        available_dates, warnings = worker._prepare_data(
            requested_dates=["2025-10-01"],
            models=["gpt-5"],
            config_path="config.json"
        )

        # Verify results
        assert available_dates == ["2025-10-01"]
        assert len(warnings) == 0

        # Verify status was updated to running
        job = job_manager.get_job(job_id)
        assert job["status"] == "running"

    def test_prepare_data_with_download(self, clean_db, monkeypatch):
        """Test prepare_data when data needs downloading."""
        from api.simulation_worker import SimulationWorker
        from api.job_manager import JobManager
        from api.database import initialize_database

        db_path = clean_db
        initialize_database(db_path)
        job_manager = JobManager(db_path=db_path)

        job_id = job_manager.create_job(
            config_path="config.json",
            date_range=["2025-10-01"],
            models=["gpt-5"]
        )

        worker = SimulationWorker(job_id=job_id, db_path=db_path)

        # Mock PriceDataManager
        mock_price_manager = Mock()
        mock_price_manager.get_missing_coverage.return_value = {"AAPL": {"2025-10-01"}}
        mock_price_manager.download_missing_data_prioritized.return_value = {
            "downloaded": ["AAPL"],
            "failed": [],
            "rate_limited": False
        }
        mock_price_manager.get_available_trading_dates.return_value = ["2025-10-01"]

        def mock_pdm_init(db_path):
            return mock_price_manager

        monkeypatch.setattr("api.price_data_manager.PriceDataManager", mock_pdm_init)
        worker.job_manager.get_completed_model_dates = Mock(return_value={})

        # Execute
        available_dates, warnings = worker._prepare_data(
            requested_dates=["2025-10-01"],
            models=["gpt-5"],
            config_path="config.json"
        )

        # Verify download was called
        mock_price_manager.download_missing_data_prioritized.assert_called_once()

        # Verify status transitions
        job = job_manager.get_job(job_id)
        assert job["status"] == "running"


# Coverage target: 90%+ for api/simulation_worker.py
