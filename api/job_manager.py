"""
Job lifecycle manager for simulation orchestration.

This module provides:
- Job creation and validation
- Status transitions (state machine)
- Progress tracking across model-days
- Concurrency control (single job at a time)
- Job retrieval and queries
- Cleanup operations
"""

import sqlite3
import json
import uuid
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from pathlib import Path
import logging

from api.database import get_db_connection

logger = logging.getLogger(__name__)


class JobManager:
    """
    Manages simulation job lifecycle and orchestration.

    Responsibilities:
        - Create jobs with date ranges and model lists
        - Track job status (pending → running → completed/partial/failed)
        - Monitor progress across model-days
        - Enforce single-job concurrency
        - Provide job queries and retrieval
        - Cleanup old jobs

    State Machine:
        pending → running → completed (all succeeded)
                         → partial (some failed)
                         → failed (job-level error)
    """

    def __init__(self, db_path: str = "data/jobs.db"):
        """
        Initialize JobManager.

        Args:
            db_path: Path to SQLite database
        """
        self.db_path = db_path

    def create_job(
        self,
        config_path: str,
        date_range: List[str],
        models: List[str],
        model_day_filter: Optional[List[tuple]] = None
    ) -> str:
        """
        Create new simulation job.

        Args:
            config_path: Path to configuration file
            date_range: List of dates to simulate (YYYY-MM-DD)
            models: List of model signatures to execute
            model_day_filter: Optional list of (model, date) tuples to limit job_details.
                             If None, creates job_details for all model-date combinations.

        Returns:
            job_id: UUID of created job

        Raises:
            ValueError: If another job is already running/pending
        """
        if not self.can_start_new_job():
            raise ValueError("Another simulation job is already running or pending")

        job_id = str(uuid.uuid4())
        created_at = datetime.utcnow().isoformat() + "Z"

        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        try:
            # Insert job
            cursor.execute("""
                INSERT INTO jobs (
                    job_id, config_path, status, date_range, models, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                job_id,
                config_path,
                "pending",
                json.dumps(date_range),
                json.dumps(models),
                created_at
            ))

            # Create job_details based on filter
            if model_day_filter is not None:
                # Only create job_details for specified model-day pairs
                for model, date in model_day_filter:
                    cursor.execute("""
                        INSERT INTO job_details (
                            job_id, date, model, status
                        )
                        VALUES (?, ?, ?, ?)
                    """, (job_id, date, model, "pending"))

                logger.info(f"Created job {job_id} with {len(model_day_filter)} model-day tasks (filtered)")
            else:
                # Create job_details for all model-day combinations
                for date in date_range:
                    for model in models:
                        cursor.execute("""
                            INSERT INTO job_details (
                                job_id, date, model, status
                            )
                            VALUES (?, ?, ?, ?)
                        """, (job_id, date, model, "pending"))

                logger.info(f"Created job {job_id} with {len(date_range)} dates and {len(models)} models")

            conn.commit()

            return job_id

        finally:
            conn.close()

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get job by ID.

        Args:
            job_id: Job UUID

        Returns:
            Job data dict or None if not found
        """
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT
                    job_id, config_path, status, date_range, models,
                    created_at, started_at, updated_at, completed_at,
                    total_duration_seconds, error, warnings
                FROM jobs
                WHERE job_id = ?
            """, (job_id,))

            row = cursor.fetchone()
            if not row:
                return None

            return {
                "job_id": row[0],
                "config_path": row[1],
                "status": row[2],
                "date_range": json.loads(row[3]),
                "models": json.loads(row[4]),
                "created_at": row[5],
                "started_at": row[6],
                "updated_at": row[7],
                "completed_at": row[8],
                "total_duration_seconds": row[9],
                "error": row[10],
                "warnings": row[11]
            }

        finally:
            conn.close()

    def get_current_job(self) -> Optional[Dict[str, Any]]:
        """
        Get most recent job.

        Returns:
            Most recent job data or None if no jobs exist
        """
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT
                    job_id, config_path, status, date_range, models,
                    created_at, started_at, updated_at, completed_at,
                    total_duration_seconds, error, warnings
                FROM jobs
                ORDER BY created_at DESC
                LIMIT 1
            """)

            row = cursor.fetchone()
            if not row:
                return None

            return {
                "job_id": row[0],
                "config_path": row[1],
                "status": row[2],
                "date_range": json.loads(row[3]),
                "models": json.loads(row[4]),
                "created_at": row[5],
                "started_at": row[6],
                "updated_at": row[7],
                "completed_at": row[8],
                "total_duration_seconds": row[9],
                "error": row[10],
                "warnings": row[11]
            }

        finally:
            conn.close()

    def find_job_by_date_range(self, date_range: List[str]) -> Optional[Dict[str, Any]]:
        """
        Find job with matching date range.

        Args:
            date_range: List of dates to match

        Returns:
            Job data or None if not found
        """
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        try:
            date_range_json = json.dumps(date_range)

            cursor.execute("""
                SELECT
                    job_id, config_path, status, date_range, models,
                    created_at, started_at, updated_at, completed_at,
                    total_duration_seconds, error, warnings
                FROM jobs
                WHERE date_range = ?
                ORDER BY created_at DESC
                LIMIT 1
            """, (date_range_json,))

            row = cursor.fetchone()
            if not row:
                return None

            return {
                "job_id": row[0],
                "config_path": row[1],
                "status": row[2],
                "date_range": json.loads(row[3]),
                "models": json.loads(row[4]),
                "created_at": row[5],
                "started_at": row[6],
                "updated_at": row[7],
                "completed_at": row[8],
                "total_duration_seconds": row[9],
                "error": row[10],
                "warnings": row[11]
            }

        finally:
            conn.close()

    def update_job_status(
        self,
        job_id: str,
        status: str,
        error: Optional[str] = None
    ) -> None:
        """
        Update job status.

        Args:
            job_id: Job UUID
            status: New status (pending/running/completed/partial/failed)
            error: Optional error message
        """
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        try:
            updated_at = datetime.utcnow().isoformat() + "Z"

            # Set timestamps based on status
            if status == "running":
                cursor.execute("""
                    UPDATE jobs
                    SET status = ?, started_at = ?, updated_at = ?
                    WHERE job_id = ?
                """, (status, updated_at, updated_at, job_id))

            elif status in ("completed", "partial", "failed"):
                # Calculate duration
                cursor.execute("""
                    SELECT started_at FROM jobs WHERE job_id = ?
                """, (job_id,))

                row = cursor.fetchone()
                duration_seconds = None

                if row and row[0]:
                    started_at = datetime.fromisoformat(row[0].replace("Z", ""))
                    completed_at = datetime.fromisoformat(updated_at.replace("Z", ""))
                    duration_seconds = (completed_at - started_at).total_seconds()

                cursor.execute("""
                    UPDATE jobs
                    SET status = ?, completed_at = ?, updated_at = ?,
                        total_duration_seconds = ?, error = ?
                    WHERE job_id = ?
                """, (status, updated_at, updated_at, duration_seconds, error, job_id))

            else:
                # Just update status
                cursor.execute("""
                    UPDATE jobs
                    SET status = ?, updated_at = ?, error = ?
                    WHERE job_id = ?
                """, (status, updated_at, error, job_id))

            conn.commit()
            logger.debug(f"Updated job {job_id} status to {status}")

        finally:
            conn.close()

    def add_job_warnings(self, job_id: str, warnings: List[str]) -> None:
        """
        Store warnings for a job.

        Args:
            job_id: Job UUID
            warnings: List of warning messages
        """
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        try:
            warnings_json = json.dumps(warnings)

            cursor.execute("""
                UPDATE jobs
                SET warnings = ?
                WHERE job_id = ?
            """, (warnings_json, job_id))

            conn.commit()
            logger.info(f"Added {len(warnings)} warnings to job {job_id}")

        finally:
            conn.close()

    def update_job_detail_status(
        self,
        job_id: str,
        date: str,
        model: str,
        status: str,
        error: Optional[str] = None
    ) -> None:
        """
        Update model-day status and auto-update job status.

        Args:
            job_id: Job UUID
            date: Trading date (YYYY-MM-DD)
            model: Model signature
            status: New status (pending/running/completed/failed)
            error: Optional error message
        """
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        try:
            updated_at = datetime.utcnow().isoformat() + "Z"

            if status == "running":
                cursor.execute("""
                    UPDATE job_details
                    SET status = ?, started_at = ?
                    WHERE job_id = ? AND date = ? AND model = ?
                """, (status, updated_at, job_id, date, model))

                # Update job to running if not already
                cursor.execute("""
                    UPDATE jobs
                    SET status = 'running', started_at = COALESCE(started_at, ?), updated_at = ?
                    WHERE job_id = ? AND status = 'pending'
                """, (updated_at, updated_at, job_id))

            elif status in ("completed", "failed"):
                # Calculate duration for detail
                cursor.execute("""
                    SELECT started_at FROM job_details
                    WHERE job_id = ? AND date = ? AND model = ?
                """, (job_id, date, model))

                row = cursor.fetchone()
                duration_seconds = None

                if row and row[0]:
                    started_at = datetime.fromisoformat(row[0].replace("Z", ""))
                    completed_at = datetime.fromisoformat(updated_at.replace("Z", ""))
                    duration_seconds = (completed_at - started_at).total_seconds()

                cursor.execute("""
                    UPDATE job_details
                    SET status = ?, completed_at = ?, duration_seconds = ?, error = ?
                    WHERE job_id = ? AND date = ? AND model = ?
                """, (status, updated_at, duration_seconds, error, job_id, date, model))

                # Check if all details are done
                cursor.execute("""
                    SELECT
                        COUNT(*) as total,
                        SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                        SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
                        SUM(CASE WHEN status = 'skipped' THEN 1 ELSE 0 END) as skipped
                    FROM job_details
                    WHERE job_id = ?
                """, (job_id,))

                total, completed, failed, skipped = cursor.fetchone()

                # Job is done when all details are in terminal states
                if completed + failed + skipped == total:
                    # All done - determine final status
                    if failed == 0:
                        final_status = "completed"
                    elif completed > 0:
                        final_status = "partial"
                    else:
                        final_status = "failed"

                    # Calculate job duration
                    cursor.execute("""
                        SELECT started_at FROM jobs WHERE job_id = ?
                    """, (job_id,))

                    row = cursor.fetchone()
                    job_duration = None

                    if row and row[0]:
                        started_at = datetime.fromisoformat(row[0].replace("Z", ""))
                        completed_at = datetime.fromisoformat(updated_at.replace("Z", ""))
                        job_duration = (completed_at - started_at).total_seconds()

                    cursor.execute("""
                        UPDATE jobs
                        SET status = ?, completed_at = ?, updated_at = ?, total_duration_seconds = ?
                        WHERE job_id = ?
                    """, (final_status, updated_at, updated_at, job_duration, job_id))

            conn.commit()
            logger.debug(f"Updated job_detail {job_id}/{date}/{model} to {status}")

        finally:
            conn.close()

    def get_job_details(self, job_id: str) -> List[Dict[str, Any]]:
        """
        Get all model-day execution details for a job.

        Args:
            job_id: Job UUID

        Returns:
            List of job_detail records with date, model, status, error
        """
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT date, model, status, error, started_at, completed_at, duration_seconds
                FROM job_details
                WHERE job_id = ?
                ORDER BY date, model
            """, (job_id,))

            rows = cursor.fetchall()

            details = []
            for row in rows:
                details.append({
                    "date": row[0],
                    "model": row[1],
                    "status": row[2],
                    "error": row[3],
                    "started_at": row[4],
                    "completed_at": row[5],
                    "duration_seconds": row[6]
                })

            return details

        finally:
            conn.close()

    def get_job_progress(self, job_id: str) -> Dict[str, Any]:
        """
        Get job progress summary.

        Args:
            job_id: Job UUID

        Returns:
            Progress dict with total_model_days, completed, failed, current, details
        """
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
                    SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
                    SUM(CASE WHEN status = 'skipped' THEN 1 ELSE 0 END) as skipped
                FROM job_details
                WHERE job_id = ?
            """, (job_id,))

            total, completed, failed, pending, skipped = cursor.fetchone()

            # Get currently running model-day
            cursor.execute("""
                SELECT date, model
                FROM job_details
                WHERE job_id = ? AND status = 'running'
                LIMIT 1
            """, (job_id,))

            current_row = cursor.fetchone()
            current = {"date": current_row[0], "model": current_row[1]} if current_row else None

            # Get all details
            cursor.execute("""
                SELECT date, model, status, duration_seconds, error
                FROM job_details
                WHERE job_id = ?
                ORDER BY date, model
            """, (job_id,))

            details = []
            for row in cursor.fetchall():
                details.append({
                    "date": row[0],
                    "model": row[1],
                    "status": row[2],
                    "duration_seconds": row[3],
                    "error": row[4]
                })

            return {
                "total_model_days": total,
                "completed": completed or 0,
                "failed": failed or 0,
                "pending": pending or 0,
                "skipped": skipped or 0,
                "current": current,
                "details": details
            }

        finally:
            conn.close()

    def can_start_new_job(self) -> bool:
        """
        Check if new job can be started.

        Returns:
            True if no jobs are pending/running, False otherwise
        """
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT COUNT(*)
                FROM jobs
                WHERE status IN ('pending', 'running')
            """)

            count = cursor.fetchone()[0]
            return count == 0

        finally:
            conn.close()

    def get_running_jobs(self) -> List[Dict[str, Any]]:
        """
        Get all running/pending jobs.

        Returns:
            List of job dicts
        """
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT
                    job_id, config_path, status, date_range, models,
                    created_at, started_at, updated_at, completed_at,
                    total_duration_seconds, error, warnings
                FROM jobs
                WHERE status IN ('pending', 'running')
                ORDER BY created_at DESC
            """)

            jobs = []
            for row in cursor.fetchall():
                jobs.append({
                    "job_id": row[0],
                    "config_path": row[1],
                    "status": row[2],
                    "date_range": json.loads(row[3]),
                    "models": json.loads(row[4]),
                    "created_at": row[5],
                    "started_at": row[6],
                    "updated_at": row[7],
                    "completed_at": row[8],
                    "total_duration_seconds": row[9],
                    "error": row[10],
                    "warnings": row[11]
                })

            return jobs

        finally:
            conn.close()

    def get_last_completed_date_for_model(self, model: str) -> Optional[str]:
        """
        Get last completed simulation date for a specific model.

        Args:
            model: Model signature

        Returns:
            Last completed date (YYYY-MM-DD) or None if no data exists
        """
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT date
                FROM job_details
                WHERE model = ? AND status = 'completed'
                ORDER BY date DESC
                LIMIT 1
            """, (model,))

            row = cursor.fetchone()
            return row[0] if row else None

        finally:
            conn.close()

    def get_completed_model_dates(self, models: List[str], start_date: str, end_date: str) -> Dict[str, List[str]]:
        """
        Get all completed dates for each model within a date range.

        Args:
            models: List of model signatures
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)

        Returns:
            Dict mapping model signature to list of completed dates
        """
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        try:
            result = {model: [] for model in models}

            for model in models:
                cursor.execute("""
                    SELECT DISTINCT date
                    FROM job_details
                    WHERE model = ? AND status = 'completed' AND date >= ? AND date <= ?
                    ORDER BY date
                """, (model, start_date, end_date))

                result[model] = [row[0] for row in cursor.fetchall()]

            return result

        finally:
            conn.close()

    def cleanup_old_jobs(self, days: int = 30) -> Dict[str, int]:
        """
        Delete jobs older than threshold.

        Args:
            days: Delete jobs older than this many days

        Returns:
            Dict with jobs_deleted count
        """
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        try:
            cutoff_date = (datetime.utcnow() - timedelta(days=days)).isoformat() + "Z"

            # Get count before deletion
            cursor.execute("""
                SELECT COUNT(*)
                FROM jobs
                WHERE created_at < ? AND status IN ('completed', 'partial', 'failed')
            """, (cutoff_date,))

            count = cursor.fetchone()[0]

            # Delete old jobs (foreign key cascade will delete related records)
            cursor.execute("""
                DELETE FROM jobs
                WHERE created_at < ? AND status IN ('completed', 'partial', 'failed')
            """, (cutoff_date,))

            conn.commit()
            logger.info(f"Cleaned up {count} jobs older than {days} days")

            return {"jobs_deleted": count}

        finally:
            conn.close()
