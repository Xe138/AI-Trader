"""
Unit tests for api/job_manager.py - Job lifecycle management.

Coverage target: 95%+

Tests verify:
- Job creation and validation
- Status transitions (state machine)
- Progress tracking
- Concurrency control
- Job retrieval and queries
- Cleanup operations
"""

import pytest
import json
from datetime import datetime, timedelta


@pytest.mark.unit
class TestJobCreation:
    """Test job creation and validation."""

    def test_create_job_success(self, clean_db):
        """Should create job with pending status."""
        from api.job_manager import JobManager

        manager = JobManager(db_path=clean_db)
        job_id = manager.create_job(
            config_path="configs/test.json",
            date_range=["2025-01-16", "2025-01-17"],
            models=["gpt-5", "claude-3.7-sonnet"]
        )

        assert job_id is not None
        job = manager.get_job(job_id)
        assert job["status"] == "pending"
        assert job["date_range"] == ["2025-01-16", "2025-01-17"]
        assert job["models"] == ["gpt-5", "claude-3.7-sonnet"]
        assert job["created_at"] is not None

    def test_create_job_with_job_details(self, clean_db):
        """Should create job_details for each model-day."""
        from api.job_manager import JobManager

        manager = JobManager(db_path=clean_db)
        job_id = manager.create_job(
            config_path="configs/test.json",
            date_range=["2025-01-16", "2025-01-17"],
            models=["gpt-5"]
        )

        progress = manager.get_job_progress(job_id)
        assert progress["total_model_days"] == 2  # 2 dates × 1 model
        assert progress["completed"] == 0
        assert progress["failed"] == 0

    def test_create_job_blocks_concurrent(self, clean_db):
        """Should prevent creating second job while first is pending."""
        from api.job_manager import JobManager

        manager = JobManager(db_path=clean_db)
        job1_id = manager.create_job(
            "configs/test.json",
            ["2025-01-16"],
            ["gpt-5"]
        )

        with pytest.raises(ValueError, match="Another simulation job is already running"):
            manager.create_job(
                "configs/test.json",
                ["2025-01-17"],
                ["gpt-5"]
            )

    def test_create_job_after_completion(self, clean_db):
        """Should allow new job after previous completes."""
        from api.job_manager import JobManager

        manager = JobManager(db_path=clean_db)
        job1_id = manager.create_job(
            "configs/test.json",
            ["2025-01-16"],
            ["gpt-5"]
        )

        manager.update_job_status(job1_id, "completed")

        # Now second job should be allowed
        job2_id = manager.create_job(
            "configs/test.json",
            ["2025-01-17"],
            ["gpt-5"]
        )
        assert job2_id is not None


@pytest.mark.unit
class TestJobStatusTransitions:
    """Test job status state machine."""

    def test_pending_to_running(self, clean_db):
        """Should transition from pending to running."""
        from api.job_manager import JobManager

        manager = JobManager(db_path=clean_db)
        job_id = manager.create_job(
            "configs/test.json",
            ["2025-01-16"],
            ["gpt-5"]
        )

        # Update detail to running
        manager.update_job_detail_status(job_id, "2025-01-16", "gpt-5", "running")

        job = manager.get_job(job_id)
        assert job["status"] == "running"
        assert job["started_at"] is not None

    def test_running_to_completed(self, clean_db):
        """Should transition to completed when all details complete."""
        from api.job_manager import JobManager

        manager = JobManager(db_path=clean_db)
        job_id = manager.create_job(
            "configs/test.json",
            ["2025-01-16"],
            ["gpt-5"]
        )

        manager.update_job_detail_status(job_id, "2025-01-16", "gpt-5", "running")
        manager.update_job_detail_status(job_id, "2025-01-16", "gpt-5", "completed")

        job = manager.get_job(job_id)
        assert job["status"] == "completed"
        assert job["completed_at"] is not None
        assert job["total_duration_seconds"] is not None

    def test_partial_completion(self, clean_db):
        """Should mark as partial when some models fail."""
        from api.job_manager import JobManager

        manager = JobManager(db_path=clean_db)
        job_id = manager.create_job(
            "configs/test.json",
            ["2025-01-16"],
            ["gpt-5", "claude-3.7-sonnet"]
        )

        # First model succeeds
        manager.update_job_detail_status(job_id, "2025-01-16", "gpt-5", "running")
        manager.update_job_detail_status(job_id, "2025-01-16", "gpt-5", "completed")

        # Second model fails
        manager.update_job_detail_status(job_id, "2025-01-16", "claude-3.7-sonnet", "running")
        manager.update_job_detail_status(
            job_id, "2025-01-16", "claude-3.7-sonnet", "failed",
            error="API timeout"
        )

        job = manager.get_job(job_id)
        assert job["status"] == "partial"

        progress = manager.get_job_progress(job_id)
        assert progress["completed"] == 1
        assert progress["failed"] == 1


@pytest.mark.unit
class TestJobRetrieval:
    """Test job query operations."""

    def test_get_nonexistent_job(self, clean_db):
        """Should return None for nonexistent job."""
        from api.job_manager import JobManager

        manager = JobManager(db_path=clean_db)
        job = manager.get_job("nonexistent-id")
        assert job is None

    def test_get_current_job(self, clean_db):
        """Should return most recent job."""
        from api.job_manager import JobManager

        manager = JobManager(db_path=clean_db)
        job1_id = manager.create_job("configs/test.json", ["2025-01-16"], ["gpt-5"])
        manager.update_job_status(job1_id, "completed")

        job2_id = manager.create_job("configs/test.json", ["2025-01-17"], ["gpt-5"])

        current = manager.get_current_job()
        assert current["job_id"] == job2_id

    def test_get_current_job_empty(self, clean_db):
        """Should return None when no jobs exist."""
        from api.job_manager import JobManager

        manager = JobManager(db_path=clean_db)
        current = manager.get_current_job()
        assert current is None

    def test_find_job_by_date_range(self, clean_db):
        """Should find existing job with same date range."""
        from api.job_manager import JobManager

        manager = JobManager(db_path=clean_db)
        job_id = manager.create_job(
            "configs/test.json",
            ["2025-01-16", "2025-01-17"],
            ["gpt-5"]
        )

        found = manager.find_job_by_date_range(["2025-01-16", "2025-01-17"])
        assert found["job_id"] == job_id

    def test_find_job_by_date_range_not_found(self, clean_db):
        """Should return None when no matching job exists."""
        from api.job_manager import JobManager

        manager = JobManager(db_path=clean_db)
        manager.create_job(
            "configs/test.json",
            ["2025-01-16"],
            ["gpt-5"]
        )

        found = manager.find_job_by_date_range(["2025-01-20", "2025-01-21"])
        assert found is None


@pytest.mark.unit
class TestJobProgress:
    """Test job progress tracking."""

    def test_progress_all_pending(self, clean_db):
        """Should show 0 completed when all pending."""
        from api.job_manager import JobManager

        manager = JobManager(db_path=clean_db)
        job_id = manager.create_job(
            "configs/test.json",
            ["2025-01-16", "2025-01-17"],
            ["gpt-5"]
        )

        progress = manager.get_job_progress(job_id)
        assert progress["total_model_days"] == 2
        assert progress["completed"] == 0
        assert progress["failed"] == 0
        assert progress["current"] is None

    def test_progress_with_running(self, clean_db):
        """Should identify currently running model-day."""
        from api.job_manager import JobManager

        manager = JobManager(db_path=clean_db)
        job_id = manager.create_job(
            "configs/test.json",
            ["2025-01-16"],
            ["gpt-5"]
        )

        manager.update_job_detail_status(job_id, "2025-01-16", "gpt-5", "running")

        progress = manager.get_job_progress(job_id)
        assert progress["current"] == {"date": "2025-01-16", "model": "gpt-5"}

    def test_progress_details(self, clean_db):
        """Should return detailed progress for all model-days."""
        from api.job_manager import JobManager

        manager = JobManager(db_path=clean_db)
        job_id = manager.create_job(
            "configs/test.json",
            ["2025-01-16"],
            ["gpt-5", "claude-3.7-sonnet"]
        )

        manager.update_job_detail_status(job_id, "2025-01-16", "gpt-5", "completed")

        progress = manager.get_job_progress(job_id)
        assert len(progress["details"]) == 2

        # Find the gpt-5 detail (order may vary)
        gpt5_detail = next(d for d in progress["details"] if d["model"] == "gpt-5")
        assert gpt5_detail["status"] == "completed"


@pytest.mark.unit
class TestConcurrencyControl:
    """Test concurrency control mechanisms."""

    def test_can_start_new_job_when_empty(self, clean_db):
        """Should allow job when none exist."""
        from api.job_manager import JobManager

        manager = JobManager(db_path=clean_db)
        assert manager.can_start_new_job() is True

    def test_can_start_new_job_blocks_pending(self, clean_db):
        """Should block when job is pending."""
        from api.job_manager import JobManager

        manager = JobManager(db_path=clean_db)
        manager.create_job("configs/test.json", ["2025-01-16"], ["gpt-5"])

        assert manager.can_start_new_job() is False

    def test_can_start_new_job_blocks_running(self, clean_db):
        """Should block when job is running."""
        from api.job_manager import JobManager

        manager = JobManager(db_path=clean_db)
        job_id = manager.create_job("configs/test.json", ["2025-01-16"], ["gpt-5"])
        manager.update_job_status(job_id, "running")

        assert manager.can_start_new_job() is False

    def test_can_start_new_job_allows_after_completion(self, clean_db):
        """Should allow new job after previous completes."""
        from api.job_manager import JobManager

        manager = JobManager(db_path=clean_db)
        job_id = manager.create_job("configs/test.json", ["2025-01-16"], ["gpt-5"])
        manager.update_job_status(job_id, "completed")

        assert manager.can_start_new_job() is True

    def test_get_running_jobs(self, clean_db):
        """Should return all running/pending jobs."""
        from api.job_manager import JobManager

        manager = JobManager(db_path=clean_db)
        job1_id = manager.create_job("configs/test.json", ["2025-01-16"], ["gpt-5"])

        # Complete first job
        manager.update_job_status(job1_id, "completed")

        # Create second job
        job2_id = manager.create_job("configs/test.json", ["2025-01-17"], ["gpt-5"])

        running = manager.get_running_jobs()
        assert len(running) == 1
        assert running[0]["job_id"] == job2_id


@pytest.mark.unit
class TestJobCleanup:
    """Test maintenance operations."""

    def test_cleanup_old_jobs(self, clean_db):
        """Should delete jobs older than threshold."""
        from api.job_manager import JobManager
        from api.database import get_db_connection

        manager = JobManager(db_path=clean_db)

        # Create old job (manually set created_at)
        conn = get_db_connection(clean_db)
        cursor = conn.cursor()

        old_date = (datetime.utcnow() - timedelta(days=35)).isoformat() + "Z"
        cursor.execute("""
            INSERT INTO jobs (job_id, config_path, status, date_range, models, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, ("old-job", "configs/test.json", "completed", '["2025-01-01"]', '["gpt-5"]', old_date))
        conn.commit()
        conn.close()

        # Create recent job
        recent_id = manager.create_job("configs/test.json", ["2025-01-16"], ["gpt-5"])

        # Cleanup jobs older than 30 days
        result = manager.cleanup_old_jobs(days=30)

        assert result["jobs_deleted"] == 1
        assert manager.get_job("old-job") is None
        assert manager.get_job(recent_id) is not None


@pytest.mark.unit
class TestJobUpdateOperations:
    """Test job update methods."""

    def test_update_job_status_with_error(self, clean_db):
        """Should record error message when job fails."""
        from api.job_manager import JobManager

        manager = JobManager(db_path=clean_db)
        job_id = manager.create_job("configs/test.json", ["2025-01-16"], ["gpt-5"])

        manager.update_job_status(job_id, "failed", error="MCP service unavailable")

        job = manager.get_job(job_id)
        assert job["status"] == "failed"
        assert job["error"] == "MCP service unavailable"

    def test_update_job_detail_records_duration(self, clean_db):
        """Should calculate duration for completed model-days."""
        from api.job_manager import JobManager
        import time

        manager = JobManager(db_path=clean_db)
        job_id = manager.create_job("configs/test.json", ["2025-01-16"], ["gpt-5"])

        # Start
        manager.update_job_detail_status(job_id, "2025-01-16", "gpt-5", "running")

        # Small delay
        time.sleep(0.1)

        # Complete
        manager.update_job_detail_status(job_id, "2025-01-16", "gpt-5", "completed")

        progress = manager.get_job_progress(job_id)
        detail = progress["details"][0]

        assert detail["duration_seconds"] is not None
        assert detail["duration_seconds"] > 0


@pytest.mark.unit
class TestJobWarnings:
    """Test job warnings management."""

    def test_add_job_warnings(self, clean_db):
        """Test adding warnings to a job."""
        from api.job_manager import JobManager
        from api.database import initialize_database

        initialize_database(clean_db)
        job_manager = JobManager(db_path=clean_db)

        # Create a job
        job_id = job_manager.create_job(
            config_path="config.json",
            date_range=["2025-10-01"],
            models=["gpt-5"]
        )

        # Add warnings
        warnings = ["Rate limit reached", "Skipped 2 dates"]
        job_manager.add_job_warnings(job_id, warnings)

        # Verify warnings were stored
        job = job_manager.get_job(job_id)
        stored_warnings = json.loads(job["warnings"])
        assert stored_warnings == warnings


# Coverage target: 95%+ for api/job_manager.py
