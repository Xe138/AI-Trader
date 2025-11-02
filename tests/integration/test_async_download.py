import pytest
import time
from api.database import initialize_database
from api.job_manager import JobManager
from api.simulation_worker import SimulationWorker
from unittest.mock import Mock, patch

def test_worker_prepares_data_before_execution(tmp_path):
    """Test that worker calls _prepare_data before executing trades."""
    db_path = str(tmp_path / "test.db")
    initialize_database(db_path)
    job_manager = JobManager(db_path=db_path)

    # Create job
    job_id = job_manager.create_job(
        config_path="configs/default_config.json",
        date_range=["2025-10-01"],
        models=["gpt-5"]
    )

    worker = SimulationWorker(job_id=job_id, db_path=db_path)

    # Mock _prepare_data to track call
    original_prepare = worker._prepare_data
    prepare_called = []

    def mock_prepare(*args, **kwargs):
        prepare_called.append(True)
        return (["2025-10-01"], [])  # Return available dates, no warnings

    worker._prepare_data = mock_prepare

    # Mock _execute_date to avoid actual execution
    worker._execute_date = Mock()

    # Run worker
    result = worker.run()

    # Verify _prepare_data was called
    assert len(prepare_called) == 1
    assert result["success"] is True

def test_worker_handles_no_available_dates(tmp_path):
    """Test worker fails gracefully when no dates are available."""
    db_path = str(tmp_path / "test.db")
    initialize_database(db_path)
    job_manager = JobManager(db_path=db_path)

    job_id = job_manager.create_job(
        config_path="configs/default_config.json",
        date_range=["2025-10-01"],
        models=["gpt-5"]
    )

    worker = SimulationWorker(job_id=job_id, db_path=db_path)

    # Mock _prepare_data to return empty dates
    worker._prepare_data = Mock(return_value=([], []))

    # Run worker
    result = worker.run()

    # Should fail with descriptive error
    assert result["success"] is False
    assert "No trading dates available" in result["error"]

    # Job should be marked as failed
    job = job_manager.get_job(job_id)
    assert job["status"] == "failed"

def test_worker_stores_warnings(tmp_path):
    """Test worker stores warnings from prepare_data."""
    db_path = str(tmp_path / "test.db")
    initialize_database(db_path)
    job_manager = JobManager(db_path=db_path)

    job_id = job_manager.create_job(
        config_path="configs/default_config.json",
        date_range=["2025-10-01"],
        models=["gpt-5"]
    )

    worker = SimulationWorker(job_id=job_id, db_path=db_path)

    # Mock _prepare_data to return warnings
    warnings = ["Rate limited", "Skipped 1 date"]
    worker._prepare_data = Mock(return_value=(["2025-10-01"], warnings))
    worker._execute_date = Mock()

    # Run worker
    result = worker.run()

    # Verify warnings in result
    assert result["warnings"] == warnings

    # Verify warnings stored in database
    import json
    job = job_manager.get_job(job_id)
    stored_warnings = json.loads(job["warnings"])
    assert stored_warnings == warnings
