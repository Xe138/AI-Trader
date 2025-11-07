"""Test duplicate detection in job creation."""
import pytest
import tempfile
import os
from pathlib import Path
from api.job_manager import JobManager


@pytest.fixture
def temp_db():
    """Create temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)

    # Initialize schema
    from api.database import get_db_connection
    conn = get_db_connection(path)
    cursor = conn.cursor()

    # Create jobs table
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

    # Create job_details table
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

    conn.commit()
    conn.close()

    yield path

    # Cleanup
    if os.path.exists(path):
        os.remove(path)


def test_create_job_with_filter_skips_completed_simulations(temp_db):
    """Test that job creation with model_day_filter skips already-completed pairs."""
    manager = JobManager(db_path=temp_db)

    # Create first job and mark model-day as completed
    result_1 = manager.create_job(
        config_path="test_config.json",
        date_range=["2025-10-15", "2025-10-16"],
        models=["deepseek-chat-v3.1"],
        model_day_filter=[("deepseek-chat-v3.1", "2025-10-15")]
    )
    job_id_1 = result_1["job_id"]

    # Mark as completed
    manager.update_job_detail_status(
        job_id_1,
        "2025-10-15",
        "deepseek-chat-v3.1",
        "completed"
    )

    # Try to create second job with overlapping date
    model_day_filter = [
        ("deepseek-chat-v3.1", "2025-10-15"),  # Already completed
        ("deepseek-chat-v3.1", "2025-10-16")   # Not yet completed
    ]

    result_2 = manager.create_job(
        config_path="test_config.json",
        date_range=["2025-10-15", "2025-10-16"],
        models=["deepseek-chat-v3.1"],
        model_day_filter=model_day_filter
    )
    job_id_2 = result_2["job_id"]

    # Get job details for second job
    details = manager.get_job_details(job_id_2)

    # Should only have 2025-10-16 (2025-10-15 was skipped as already completed)
    assert len(details) == 1
    assert details[0]["date"] == "2025-10-16"
    assert details[0]["model"] == "deepseek-chat-v3.1"


def test_create_job_without_filter_skips_all_completed_simulations(temp_db):
    """Test that job creation without filter skips all completed model-day pairs."""
    manager = JobManager(db_path=temp_db)

    # Create first job and complete some model-days
    result_1 = manager.create_job(
        config_path="test_config.json",
        date_range=["2025-10-15"],
        models=["model-a", "model-b"]
    )
    job_id_1 = result_1["job_id"]

    # Mark model-a/2025-10-15 as completed
    manager.update_job_detail_status(job_id_1, "2025-10-15", "model-a", "completed")
    # Mark model-b/2025-10-15 as failed to complete the job
    manager.update_job_detail_status(job_id_1, "2025-10-15", "model-b", "failed")

    # Create second job with same date range and models
    result_2 = manager.create_job(
        config_path="test_config.json",
        date_range=["2025-10-15", "2025-10-16"],
        models=["model-a", "model-b"]
    )
    job_id_2 = result_2["job_id"]

    # Get job details for second job
    details = manager.get_job_details(job_id_2)

    # Should have 3 entries (skip only completed model-a/2025-10-15):
    # - model-b/2025-10-15 (failed in job 1, so not skipped - retry)
    # - model-a/2025-10-16 (new date)
    # - model-b/2025-10-16 (new date)
    assert len(details) == 3

    dates_models = [(d["date"], d["model"]) for d in details]
    assert ("2025-10-15", "model-a") not in dates_models  # Skipped (completed)
    assert ("2025-10-15", "model-b") in dates_models  # NOT skipped (failed, not completed)
    assert ("2025-10-16", "model-a") in dates_models
    assert ("2025-10-16", "model-b") in dates_models


def test_create_job_returns_warnings_for_skipped_simulations(temp_db):
    """Test that skipped simulations are returned as warnings."""
    manager = JobManager(db_path=temp_db)

    # Create and complete first simulation
    result_1 = manager.create_job(
        config_path="test_config.json",
        date_range=["2025-10-15"],
        models=["model-a"]
    )
    job_id_1 = result_1["job_id"]
    manager.update_job_detail_status(job_id_1, "2025-10-15", "model-a", "completed")

    # Try to create job with overlapping date (one completed, one new)
    result = manager.create_job(
        config_path="test_config.json",
        date_range=["2025-10-15", "2025-10-16"],  # Add new date
        models=["model-a"]
    )

    # Result should be a dict with job_id and warnings
    assert isinstance(result, dict)
    assert "job_id" in result
    assert "warnings" in result
    assert len(result["warnings"]) == 1
    assert "model-a" in result["warnings"][0]
    assert "2025-10-15" in result["warnings"][0]

    # Verify job_details only has the new date
    details = manager.get_job_details(result["job_id"])
    assert len(details) == 1
    assert details[0]["date"] == "2025-10-16"


def test_create_job_raises_error_when_all_simulations_completed(temp_db):
    """Test that ValueError is raised when ALL requested simulations are already completed."""
    manager = JobManager(db_path=temp_db)

    # Create and complete first simulation
    result_1 = manager.create_job(
        config_path="test_config.json",
        date_range=["2025-10-15", "2025-10-16"],
        models=["model-a", "model-b"]
    )
    job_id_1 = result_1["job_id"]

    # Mark all model-days as completed
    manager.update_job_detail_status(job_id_1, "2025-10-15", "model-a", "completed")
    manager.update_job_detail_status(job_id_1, "2025-10-15", "model-b", "completed")
    manager.update_job_detail_status(job_id_1, "2025-10-16", "model-a", "completed")
    manager.update_job_detail_status(job_id_1, "2025-10-16", "model-b", "completed")

    # Try to create job with same date range and models (all already completed)
    with pytest.raises(ValueError) as exc_info:
        manager.create_job(
            config_path="test_config.json",
            date_range=["2025-10-15", "2025-10-16"],
            models=["model-a", "model-b"]
        )

    # Verify error message contains expected text
    error_message = str(exc_info.value)
    assert "All requested simulations are already completed" in error_message
    assert "Skipped 4 model-day pair(s)" in error_message


def test_create_job_with_skip_completed_false_includes_all_simulations(temp_db):
    """Test that skip_completed=False includes ALL simulations, even already-completed ones."""
    manager = JobManager(db_path=temp_db)

    # Create first job and complete some model-days
    result_1 = manager.create_job(
        config_path="test_config.json",
        date_range=["2025-10-15", "2025-10-16"],
        models=["model-a", "model-b"]
    )
    job_id_1 = result_1["job_id"]

    # Mark all model-days as completed
    manager.update_job_detail_status(job_id_1, "2025-10-15", "model-a", "completed")
    manager.update_job_detail_status(job_id_1, "2025-10-15", "model-b", "completed")
    manager.update_job_detail_status(job_id_1, "2025-10-16", "model-a", "completed")
    manager.update_job_detail_status(job_id_1, "2025-10-16", "model-b", "completed")

    # Create second job with skip_completed=False
    result_2 = manager.create_job(
        config_path="test_config.json",
        date_range=["2025-10-15", "2025-10-16"],
        models=["model-a", "model-b"],
        skip_completed=False
    )
    job_id_2 = result_2["job_id"]

    # Get job details for second job
    details = manager.get_job_details(job_id_2)

    # Should have ALL 4 model-day pairs (no skipping)
    assert len(details) == 4

    dates_models = [(d["date"], d["model"]) for d in details]
    assert ("2025-10-15", "model-a") in dates_models
    assert ("2025-10-15", "model-b") in dates_models
    assert ("2025-10-16", "model-a") in dates_models
    assert ("2025-10-16", "model-b") in dates_models

    # Verify no warnings were returned
    assert result_2.get("warnings") == []
