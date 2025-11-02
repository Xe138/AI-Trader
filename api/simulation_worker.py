"""
Simulation job orchestration worker.

This module provides:
- Job execution orchestration
- Date-sequential, model-parallel execution
- Progress tracking and status updates
- Error handling and recovery
"""

import logging
from typing import Dict, Any, List, Set
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
            2. Prepare data (download if needed)
            3. For each date sequentially:
                a. Execute all models in parallel
                b. Wait for all to complete
                c. Update progress
            4. Determine final job status
            5. Store warnings if any

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

            # NEW: Prepare price data (download if needed)
            available_dates, warnings = self._prepare_data(date_range, models, config_path)

            if not available_dates:
                error_msg = "No trading dates available after price data preparation"
                self.job_manager.update_job_status(self.job_id, "failed", error=error_msg)
                return {"success": False, "error": error_msg}

            # Execute available dates only
            for date in available_dates:
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

            # Add warnings if any dates were skipped
            if warnings:
                self._add_job_warnings(warnings)

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
                "failed": progress["failed"],
                "warnings": warnings
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

    def _download_price_data(
        self,
        price_manager,
        missing_coverage: Dict[str, Set[str]],
        requested_dates: List[str],
        warnings: List[str]
    ) -> None:
        """Download missing price data with progress logging."""
        logger.info(f"Job {self.job_id}: Starting prioritized download...")

        requested_dates_set = set(requested_dates)

        download_result = price_manager.download_missing_data_prioritized(
            missing_coverage,
            requested_dates_set
        )

        downloaded = len(download_result["downloaded"])
        failed = len(download_result["failed"])
        total = downloaded + failed

        logger.info(
            f"Job {self.job_id}: Download complete - "
            f"{downloaded}/{total} symbols succeeded"
        )

        if download_result["rate_limited"]:
            msg = f"Rate limit reached - downloaded {downloaded}/{total} symbols"
            warnings.append(msg)
            logger.warning(f"Job {self.job_id}: {msg}")

        if failed > 0 and not download_result["rate_limited"]:
            msg = f"{failed} symbols failed to download"
            warnings.append(msg)
            logger.warning(f"Job {self.job_id}: {msg}")

    def _filter_completed_dates(
        self,
        available_dates: List[str],
        models: List[str]
    ) -> List[str]:
        """
        Filter out dates that are already completed for all models.

        Implements idempotent job behavior - skip model-days that already
        have completed data.

        Args:
            available_dates: List of dates with complete price data
            models: List of model signatures

        Returns:
            List of dates that need processing
        """
        if not available_dates:
            return []

        # Get completed dates from job_manager
        start_date = available_dates[0]
        end_date = available_dates[-1]

        completed_dates = self.job_manager.get_completed_model_dates(
            models,
            start_date,
            end_date
        )

        # Build list of dates that need processing
        dates_to_process = []
        for date in available_dates:
            # Check if any model needs this date
            needs_processing = False
            for model in models:
                if date not in completed_dates.get(model, []):
                    needs_processing = True
                    break

            if needs_processing:
                dates_to_process.append(date)

        return dates_to_process

    def _add_job_warnings(self, warnings: List[str]) -> None:
        """Store warnings in job metadata."""
        self.job_manager.add_job_warnings(self.job_id, warnings)

    def _prepare_data(
        self,
        requested_dates: List[str],
        models: List[str],
        config_path: str
    ) -> tuple:
        """
        Prepare price data for simulation.

        Steps:
        1. Update job status to "downloading_data"
        2. Check what data is missing
        3. Download missing data (with rate limit handling)
        4. Determine available trading dates
        5. Filter out already-completed model-days (idempotent)
        6. Update job status to "running"

        Args:
            requested_dates: All dates requested for simulation
            models: Model signatures to simulate
            config_path: Path to configuration file

        Returns:
            Tuple of (available_dates, warnings)
        """
        from api.price_data_manager import PriceDataManager

        warnings = []

        # Update status
        self.job_manager.update_job_status(self.job_id, "downloading_data")
        logger.info(f"Job {self.job_id}: Checking price data availability...")

        # Initialize price manager
        price_manager = PriceDataManager(db_path=self.db_path)

        # Check missing coverage
        start_date = requested_dates[0]
        end_date = requested_dates[-1]
        missing_coverage = price_manager.get_missing_coverage(start_date, end_date)

        # Download if needed
        if missing_coverage:
            logger.info(f"Job {self.job_id}: Missing data for {len(missing_coverage)} symbols")
            self._download_price_data(price_manager, missing_coverage, requested_dates, warnings)
        else:
            logger.info(f"Job {self.job_id}: All price data available")

        # Get available dates after download
        available_dates = price_manager.get_available_trading_dates(start_date, end_date)

        # Warn about skipped dates
        skipped = set(requested_dates) - set(available_dates)
        if skipped:
            warnings.append(f"Skipped {len(skipped)} dates due to incomplete price data: {sorted(list(skipped))}")
            logger.warning(f"Job {self.job_id}: {warnings[-1]}")

        # Filter already-completed model-days (idempotent behavior)
        available_dates = self._filter_completed_dates(available_dates, models)

        # Update to running
        self.job_manager.update_job_status(self.job_id, "running")
        logger.info(f"Job {self.job_id}: Starting execution - {len(available_dates)} dates, {len(models)} models")

        return available_dates, warnings

    def get_job_info(self) -> Dict[str, Any]:
        """
        Get job information.

        Returns:
            Job data dict
        """
        return self.job_manager.get_job(self.job_id)
