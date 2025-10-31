"""
Simulation job orchestration worker.

This module provides:
- Job execution orchestration
- Date-sequential, model-parallel execution
- Progress tracking and status updates
- Error handling and recovery
"""

import logging
from typing import Dict, Any, List
from concurrent.futures import ThreadPoolExecutor, as_completed

from api.job_manager import JobManager
from api.model_day_executor import ModelDayExecutor

logger = logging.getLogger(__name__)


class SimulationWorker:
    """
    Orchestrates execution of a simulation job.

    Responsibilities:
        - Execute all model-day combinations for a job
        - Date-sequential execution (one date at a time)
        - Model-parallel execution (all models for a date run concurrently)
        - Update job status throughout execution
        - Handle failures gracefully

    Execution Strategy:
        For each date in job.date_range:
            Execute all models in parallel using ThreadPoolExecutor
            Wait for all models to complete before moving to next date

    Status Transitions:
        pending → running → completed (all succeeded)
                         → partial (some failed)
                         → failed (job-level error)
    """

    def __init__(self, job_id: str, db_path: str = "data/jobs.db", max_workers: int = 4):
        """
        Initialize SimulationWorker.

        Args:
            job_id: Job UUID to execute
            db_path: Path to SQLite database
            max_workers: Maximum concurrent model executions per date
        """
        self.job_id = job_id
        self.db_path = db_path
        self.max_workers = max_workers
        self.job_manager = JobManager(db_path=db_path)

        logger.info(f"Initialized worker for job {job_id}")

    def run(self) -> Dict[str, Any]:
        """
        Execute the simulation job.

        Returns:
            Result dict with success status and summary

        Process:
            1. Get job details (dates, models, config)
            2. For each date sequentially:
                a. Execute all models in parallel
                b. Wait for all to complete
                c. Update progress
            3. Determine final job status
            4. Update job with final status

        Error Handling:
            - Individual model failures: Mark detail as failed, continue with others
            - Job-level errors: Mark entire job as failed
        """
        try:
            # Get job info
            job = self.job_manager.get_job(self.job_id)
            if not job:
                raise ValueError(f"Job {self.job_id} not found")

            date_range = job["date_range"]
            models = job["models"]
            config_path = job["config_path"]

            logger.info(f"Starting job {self.job_id}: {len(date_range)} dates, {len(models)} models")

            # Execute date-by-date (sequential)
            for date in date_range:
                logger.info(f"Processing date {date} with {len(models)} models")
                self._execute_date(date, models, config_path)

            # Job completed - determine final status
            progress = self.job_manager.get_job_progress(self.job_id)

            if progress["failed"] == 0:
                final_status = "completed"
            elif progress["completed"] > 0:
                final_status = "partial"
            else:
                final_status = "failed"

            # Note: Job status is already updated by model_day_executor's detail status updates
            # We don't need to explicitly call update_job_status here as it's handled automatically
            # by the status transition logic in JobManager.update_job_detail_status

            logger.info(f"Job {self.job_id} finished with status: {final_status}")

            return {
                "success": True,
                "job_id": self.job_id,
                "status": final_status,
                "total_model_days": progress["total_model_days"],
                "completed": progress["completed"],
                "failed": progress["failed"]
            }

        except Exception as e:
            error_msg = f"Job execution failed: {str(e)}"
            logger.error(f"Job {self.job_id}: {error_msg}", exc_info=True)

            # Update job to failed
            self.job_manager.update_job_status(self.job_id, "failed", error=error_msg)

            return {
                "success": False,
                "job_id": self.job_id,
                "error": error_msg
            }

    def _execute_date(self, date: str, models: List[str], config_path: str) -> None:
        """
        Execute all models for a single date in parallel.

        Args:
            date: Trading date (YYYY-MM-DD)
            models: List of model signatures to execute
            config_path: Path to configuration file

        Uses ThreadPoolExecutor to run all models concurrently for this date.
        Waits for all models to complete before returning.
        """
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all model executions for this date
            futures = []
            for model in models:
                future = executor.submit(
                    self._execute_model_day,
                    date,
                    model,
                    config_path
                )
                futures.append(future)

            # Wait for all to complete
            for future in as_completed(futures):
                try:
                    result = future.result()
                    if result["success"]:
                        logger.debug(f"Completed {result['model']} on {result['date']}")
                    else:
                        logger.warning(f"Failed {result['model']} on {result['date']}: {result.get('error')}")
                except Exception as e:
                    logger.error(f"Exception in model execution: {e}", exc_info=True)

    def _execute_model_day(self, date: str, model: str, config_path: str) -> Dict[str, Any]:
        """
        Execute a single model for a single date.

        Args:
            date: Trading date (YYYY-MM-DD)
            model: Model signature
            config_path: Path to configuration file

        Returns:
            Execution result dict
        """
        try:
            executor = ModelDayExecutor(
                job_id=self.job_id,
                date=date,
                model_sig=model,
                config_path=config_path,
                db_path=self.db_path
            )

            result = executor.execute()
            return result

        except Exception as e:
            logger.error(f"Failed to execute {model} on {date}: {e}", exc_info=True)
            return {
                "success": False,
                "job_id": self.job_id,
                "date": date,
                "model": model,
                "error": str(e)
            }

    def get_job_info(self) -> Dict[str, Any]:
        """
        Get job information.

        Returns:
            Job data dict
        """
        return self.job_manager.get_job(self.job_id)
