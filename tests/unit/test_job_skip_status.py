"""
Tests for job skip status tracking functionality.

Tests the skip status feature that marks dates as skipped when they:
1. Have incomplete price data (weekends/holidays)
2. Are already completed from a previous job run

Tests also verify that jobs complete properly when all dates are in
terminal states (completed/failed/skipped).
"""

import pytest
import tempfile
from pathlib import Path

from api.job_manager import JobManager
from api.database import initialize_database


@pytest.fixture
def temp_db():
    """Create temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name

    initialize_database(db_path)
    yield db_path

    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def job_manager(temp_db):
    """Create JobManager with temporary database."""
    return JobManager(db_path=temp_db)


class TestSkipStatusDatabase:
    """Test that database accepts 'skipped' status."""

    def test_skipped_status_allowed_in_job_details(self, job_manager):
        """Test job_details accepts 'skipped' status without constraint violation."""
        # Create job
        job_id = job_manager.create_job(
            config_path="test_config.json",
            date_range=["2025-10-01", "2025-10-02"],
            models=["test-model"]
        )

        # Mark a detail as skipped - should not raise constraint violation
        job_manager.update_job_detail_status(
            job_id=job_id,
            date="2025-10-01",
            model="test-model",
            status="skipped",
            error="Test skip reason"
        )

        # Verify status was set
        details = job_manager.get_job_details(job_id)
        assert len(details) == 2
        skipped_detail = next(d for d in details if d["date"] == "2025-10-01")
        assert skipped_detail["status"] == "skipped"
        assert skipped_detail["error"] == "Test skip reason"


class TestJobCompletionWithSkipped:
    """Test that jobs complete when skipped dates are counted."""

    def test_job_completes_with_all_dates_skipped(self, job_manager):
        """Test job transitions to completed when all dates are skipped."""
        # Create job with 3 dates
        job_id = job_manager.create_job(
            config_path="test_config.json",
            date_range=["2025-10-01", "2025-10-02", "2025-10-03"],
            models=["test-model"]
        )

        # Mark all as skipped
        for date in ["2025-10-01", "2025-10-02", "2025-10-03"]:
            job_manager.update_job_detail_status(
                job_id=job_id,
                date=date,
                model="test-model",
                status="skipped",
                error="Incomplete price data"
            )

        # Verify job completed
        job = job_manager.get_job(job_id)
        assert job["status"] == "completed"
        assert job["completed_at"] is not None

    def test_job_completes_with_mixed_completed_and_skipped(self, job_manager):
        """Test job completes when some dates completed, some skipped."""
        job_id = job_manager.create_job(
            config_path="test_config.json",
            date_range=["2025-10-01", "2025-10-02", "2025-10-03"],
            models=["test-model"]
        )

        # Mark some completed, some skipped
        job_manager.update_job_detail_status(
            job_id=job_id, date="2025-10-01", model="test-model",
            status="completed"
        )
        job_manager.update_job_detail_status(
            job_id=job_id, date="2025-10-02", model="test-model",
            status="skipped", error="Already completed"
        )
        job_manager.update_job_detail_status(
            job_id=job_id, date="2025-10-03", model="test-model",
            status="skipped", error="Incomplete price data"
        )

        # Verify job completed
        job = job_manager.get_job(job_id)
        assert job["status"] == "completed"

    def test_job_partial_with_mixed_completed_failed_skipped(self, job_manager):
        """Test job status 'partial' when some failed, some completed, some skipped."""
        job_id = job_manager.create_job(
            config_path="test_config.json",
            date_range=["2025-10-01", "2025-10-02", "2025-10-03"],
            models=["test-model"]
        )

        # Mix of statuses
        job_manager.update_job_detail_status(
            job_id=job_id, date="2025-10-01", model="test-model",
            status="completed"
        )
        job_manager.update_job_detail_status(
            job_id=job_id, date="2025-10-02", model="test-model",
            status="failed", error="Execution error"
        )
        job_manager.update_job_detail_status(
            job_id=job_id, date="2025-10-03", model="test-model",
            status="skipped", error="Incomplete price data"
        )

        # Verify job status is partial
        job = job_manager.get_job(job_id)
        assert job["status"] == "partial"

    def test_job_remains_running_with_pending_dates(self, job_manager):
        """Test job stays running when some dates are still pending."""
        job_id = job_manager.create_job(
            config_path="test_config.json",
            date_range=["2025-10-01", "2025-10-02", "2025-10-03"],
            models=["test-model"]
        )

        # Only mark some as terminal states
        job_manager.update_job_detail_status(
            job_id=job_id, date="2025-10-01", model="test-model",
            status="completed"
        )
        job_manager.update_job_detail_status(
            job_id=job_id, date="2025-10-02", model="test-model",
            status="skipped", error="Already completed"
        )
        # Leave 2025-10-03 as pending

        # Verify job still running (not completed)
        job = job_manager.get_job(job_id)
        assert job["status"] == "pending"  # Not yet marked as running
        assert job["completed_at"] is None


class TestProgressTrackingWithSkipped:
    """Test progress tracking includes skipped counts."""

    def test_progress_includes_skipped_count(self, job_manager):
        """Test get_job_progress returns skipped count."""
        job_id = job_manager.create_job(
            config_path="test_config.json",
            date_range=["2025-10-01", "2025-10-02", "2025-10-03", "2025-10-04"],
            models=["test-model"]
        )

        # Set various statuses
        job_manager.update_job_detail_status(
            job_id=job_id, date="2025-10-01", model="test-model",
            status="completed"
        )
        job_manager.update_job_detail_status(
            job_id=job_id, date="2025-10-02", model="test-model",
            status="skipped", error="Already completed"
        )
        job_manager.update_job_detail_status(
            job_id=job_id, date="2025-10-03", model="test-model",
            status="skipped", error="Incomplete price data"
        )
        # Leave 2025-10-04 pending

        # Check progress
        progress = job_manager.get_job_progress(job_id)

        assert progress["total_model_days"] == 4
        assert progress["completed"] == 1
        assert progress["failed"] == 0
        assert progress["pending"] == 1
        assert progress["skipped"] == 2

    def test_progress_all_skipped(self, job_manager):
        """Test progress when all dates are skipped."""
        job_id = job_manager.create_job(
            config_path="test_config.json",
            date_range=["2025-10-01", "2025-10-02"],
            models=["test-model"]
        )

        # Mark all as skipped
        for date in ["2025-10-01", "2025-10-02"]:
            job_manager.update_job_detail_status(
                job_id=job_id, date=date, model="test-model",
                status="skipped", error="Incomplete price data"
            )

        progress = job_manager.get_job_progress(job_id)

        assert progress["skipped"] == 2
        assert progress["completed"] == 0
        assert progress["pending"] == 0
        assert progress["failed"] == 0


class TestMultiModelSkipHandling:
    """Test skip status with multiple models having different completion states."""

    def test_different_models_different_skip_states(self, job_manager):
        """Test that different models can have different skip states for same date."""
        job_id = job_manager.create_job(
            config_path="test_config.json",
            date_range=["2025-10-01", "2025-10-02"],
            models=["model-a", "model-b"]
        )

        # Model A: 10/1 skipped (already completed), 10/2 completed
        job_manager.update_job_detail_status(
            job_id=job_id, date="2025-10-01", model="model-a",
            status="skipped", error="Already completed"
        )
        job_manager.update_job_detail_status(
            job_id=job_id, date="2025-10-02", model="model-a",
            status="completed"
        )

        # Model B: both dates completed
        job_manager.update_job_detail_status(
            job_id=job_id, date="2025-10-01", model="model-b",
            status="completed"
        )
        job_manager.update_job_detail_status(
            job_id=job_id, date="2025-10-02", model="model-b",
            status="completed"
        )

        # Verify details
        details = job_manager.get_job_details(job_id)

        model_a_10_01 = next(
            d for d in details
            if d["model"] == "model-a" and d["date"] == "2025-10-01"
        )
        model_b_10_01 = next(
            d for d in details
            if d["model"] == "model-b" and d["date"] == "2025-10-01"
        )

        assert model_a_10_01["status"] == "skipped"
        assert model_a_10_01["error"] == "Already completed"
        assert model_b_10_01["status"] == "completed"
        assert model_b_10_01["error"] is None

    def test_job_completes_with_per_model_skips(self, job_manager):
        """Test job completes when different models have different skip patterns."""
        job_id = job_manager.create_job(
            config_path="test_config.json",
            date_range=["2025-10-01", "2025-10-02"],
            models=["model-a", "model-b"]
        )

        # Model A: one skipped, one completed
        job_manager.update_job_detail_status(
            job_id=job_id, date="2025-10-01", model="model-a",
            status="skipped", error="Already completed"
        )
        job_manager.update_job_detail_status(
            job_id=job_id, date="2025-10-02", model="model-a",
            status="completed"
        )

        # Model B: both completed
        job_manager.update_job_detail_status(
            job_id=job_id, date="2025-10-01", model="model-b",
            status="completed"
        )
        job_manager.update_job_detail_status(
            job_id=job_id, date="2025-10-02", model="model-b",
            status="completed"
        )

        # Job should complete
        job = job_manager.get_job(job_id)
        assert job["status"] == "completed"

        # Progress should show mixed counts
        progress = job_manager.get_job_progress(job_id)
        assert progress["completed"] == 3
        assert progress["skipped"] == 1
        assert progress["total_model_days"] == 4


class TestSkipReasons:
    """Test that skip reasons are properly stored and retrievable."""

    def test_skip_reason_already_completed(self, job_manager):
        """Test 'Already completed' skip reason is stored."""
        job_id = job_manager.create_job(
            config_path="test_config.json",
            date_range=["2025-10-01"],
            models=["test-model"]
        )

        job_manager.update_job_detail_status(
            job_id=job_id, date="2025-10-01", model="test-model",
            status="skipped", error="Already completed"
        )

        details = job_manager.get_job_details(job_id)
        assert details[0]["error"] == "Already completed"

    def test_skip_reason_incomplete_price_data(self, job_manager):
        """Test 'Incomplete price data' skip reason is stored."""
        job_id = job_manager.create_job(
            config_path="test_config.json",
            date_range=["2025-10-04"],
            models=["test-model"]
        )

        job_manager.update_job_detail_status(
            job_id=job_id, date="2025-10-04", model="test-model",
            status="skipped", error="Incomplete price data"
        )

        details = job_manager.get_job_details(job_id)
        assert details[0]["error"] == "Incomplete price data"
