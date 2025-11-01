"""
FastAPI REST API for AI-Trader simulation service.

Provides endpoints for:
- Triggering simulation jobs
- Checking job status
- Querying results
- Health checks
"""

import logging
import os
from typing import Optional, List, Dict, Any
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from api.job_manager import JobManager
from api.simulation_worker import SimulationWorker
from api.database import get_db_connection
from api.price_data_manager import PriceDataManager
from api.date_utils import validate_date_range, expand_date_range, get_max_simulation_days
from tools.deployment_config import get_deployment_mode_dict, log_dev_mode_startup_warning
import threading
import time

logger = logging.getLogger(__name__)


# Pydantic models for request/response validation
class SimulateTriggerRequest(BaseModel):
    """Request body for POST /simulate/trigger."""
    start_date: Optional[str] = Field(None, description="Start date for simulation (YYYY-MM-DD). If null/omitted, resumes from last completed date per model.")
    end_date: str = Field(..., description="End date for simulation (YYYY-MM-DD). Required.")
    models: Optional[List[str]] = Field(
        None,
        description="Optional: List of model signatures to simulate. If not provided, uses enabled models from config."
    )
    replace_existing: bool = Field(
        False,
        description="If true, replaces existing simulation data. If false (default), skips dates that already have data (idempotent)."
    )

    @field_validator("start_date", "end_date")
    @classmethod
    def validate_date_format(cls, v):
        """Validate date format."""
        if v is None or v == "":
            return None
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError(f"Invalid date format: {v}. Expected YYYY-MM-DD")
        return v

    @field_validator("end_date")
    @classmethod
    def validate_end_date_required(cls, v):
        """Ensure end_date is not null or empty."""
        if v is None or v == "":
            raise ValueError("end_date is required and cannot be null or empty")
        return v


class SimulateTriggerResponse(BaseModel):
    """Response body for POST /simulate/trigger."""
    job_id: str
    status: str
    total_model_days: int
    message: str
    deployment_mode: str
    is_dev_mode: bool
    preserve_dev_data: Optional[bool] = None


class JobProgress(BaseModel):
    """Job progress information."""
    total_model_days: int
    completed: int
    failed: int
    pending: int


class JobStatusResponse(BaseModel):
    """Response body for GET /simulate/status/{job_id}."""
    job_id: str
    status: str
    progress: JobProgress
    date_range: List[str]
    models: List[str]
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    total_duration_seconds: Optional[float] = None
    error: Optional[str] = None
    details: List[Dict[str, Any]]
    deployment_mode: str
    is_dev_mode: bool
    preserve_dev_data: Optional[bool] = None


class HealthResponse(BaseModel):
    """Response body for GET /health."""
    status: str
    database: str
    timestamp: str
    deployment_mode: str
    is_dev_mode: bool
    preserve_dev_data: Optional[bool] = None


def create_app(
    db_path: str = "data/jobs.db",
    config_path: str = "configs/default_config.json"
) -> FastAPI:
    """
    Create FastAPI application instance.

    Args:
        db_path: Path to SQLite database
        config_path: Path to default configuration file

    Returns:
        Configured FastAPI app
    """
    app = FastAPI(
        title="AI-Trader Simulation API",
        description="REST API for triggering and monitoring AI trading simulations",
        version="1.0.0"
    )

    # Store paths in app state
    app.state.db_path = db_path
    app.state.config_path = config_path

    @app.on_event("startup")
    async def startup_event():
        """Display DEV mode warning on startup if applicable"""
        log_dev_mode_startup_warning()

    @app.post("/simulate/trigger", response_model=SimulateTriggerResponse, status_code=200)
    async def trigger_simulation(request: SimulateTriggerRequest):
        """
        Trigger a new simulation job.

        Validates date range, downloads missing price data if needed,
        and creates job with available trading dates.

        Supports:
        - Single date: start_date == end_date
        - Date range: start_date < end_date
        - Resume: start_date is null (each model resumes from its last completed date)
        - Idempotent: replace_existing=false skips already completed model-days

        Raises:
            HTTPException 400: Validation errors, running job, or invalid dates
            HTTPException 503: Price data download failed
        """
        try:
            # Use config path from app state
            config_path = app.state.config_path

            # Validate config path exists
            if not Path(config_path).exists():
                raise HTTPException(
                    status_code=500,
                    detail=f"Server configuration file not found: {config_path}"
                )

            end_date = request.end_date

            # Determine which models to run
            import json
            with open(config_path, 'r') as f:
                config = json.load(f)

            if request.models is not None:
                # Use models from request (explicit override)
                models_to_run = request.models
            else:
                # Use enabled models from config
                models_to_run = [
                    model["signature"]
                    for model in config.get("models", [])
                    if model.get("enabled", False)
                ]

                if not models_to_run:
                    raise HTTPException(
                        status_code=400,
                        detail="No enabled models found in config. Either enable models in config or specify them in request."
                    )

            job_manager = JobManager(db_path=app.state.db_path)

            # Handle resume logic (start_date is null)
            if request.start_date is None:
                # Resume mode: determine start date per model
                model_start_dates = {}

                for model in models_to_run:
                    last_date = job_manager.get_last_completed_date_for_model(model)

                    if last_date is None:
                        # Cold start: use end_date as single-day simulation
                        model_start_dates[model] = end_date
                    else:
                        # Resume from next day after last completed
                        last_dt = datetime.strptime(last_date, "%Y-%m-%d")
                        next_dt = last_dt + timedelta(days=1)
                        model_start_dates[model] = next_dt.strftime("%Y-%m-%d")

                # For validation purposes, use earliest start date
                earliest_start = min(model_start_dates.values())
                start_date = earliest_start
            else:
                # Explicit start date provided
                start_date = request.start_date
                model_start_dates = {model: start_date for model in models_to_run}

            # Validate date range
            max_days = get_max_simulation_days()
            validate_date_range(start_date, end_date, max_days=max_days)

            # Check price data and download if needed
            auto_download = os.getenv("AUTO_DOWNLOAD_PRICE_DATA", "true").lower() == "true"
            price_manager = PriceDataManager(db_path=app.state.db_path)

            # Check what's missing (use computed start_date, not request.start_date which may be None)
            missing_coverage = price_manager.get_missing_coverage(
                start_date,
                end_date
            )

            download_info = None

            # Download missing data if enabled
            if any(missing_coverage.values()):
                if not auto_download:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Missing price data for {len(missing_coverage)} symbols and auto-download is disabled. "
                               f"Enable AUTO_DOWNLOAD_PRICE_DATA or pre-populate data."
                    )

                logger.info(f"Downloading missing price data for {len(missing_coverage)} symbols")

                requested_dates = set(expand_date_range(start_date, end_date))

                download_result = price_manager.download_missing_data_prioritized(
                    missing_coverage,
                    requested_dates
                )

                if not download_result["success"]:
                    raise HTTPException(
                        status_code=503,
                        detail="Failed to download any price data. Check ALPHAADVANTAGE_API_KEY."
                    )

                download_info = {
                    "symbols_downloaded": len(download_result["downloaded"]),
                    "symbols_failed": len(download_result["failed"]),
                    "rate_limited": download_result["rate_limited"]
                }

                logger.info(
                    f"Downloaded {len(download_result['downloaded'])} symbols, "
                    f"{len(download_result['failed'])} failed, rate_limited={download_result['rate_limited']}"
                )

            # Get available trading dates (after potential download)
            available_dates = price_manager.get_available_trading_dates(
                start_date,
                end_date
            )

            if not available_dates:
                raise HTTPException(
                    status_code=400,
                    detail=f"No trading dates with complete price data in range "
                           f"{start_date} to {end_date}. "
                           f"All symbols must have data for a date to be tradeable."
                )

            # Handle idempotent behavior (skip already completed model-days)
            if not request.replace_existing:
                # Get existing completed dates per model
                completed_dates = job_manager.get_completed_model_dates(
                    models_to_run,
                    start_date,
                    end_date
                )

                # Build list of model-day tuples to simulate
                model_day_tasks = []
                for model in models_to_run:
                    # Filter dates for this model
                    model_start = model_start_dates[model]

                    for date in available_dates:
                        # Skip if before model's start date
                        if date < model_start:
                            continue

                        # Skip if already completed (idempotent)
                        if date in completed_dates.get(model, []):
                            continue

                        model_day_tasks.append((model, date))

                if not model_day_tasks:
                    raise HTTPException(
                        status_code=400,
                        detail="No new model-days to simulate. All requested dates are already completed. "
                               "Use replace_existing=true to re-run."
                    )

                # Extract unique dates that will actually be run
                dates_to_run = sorted(list(set([date for _, date in model_day_tasks])))
            else:
                # Replace mode: run all model-date combinations
                dates_to_run = available_dates
                model_day_tasks = [
                    (model, date)
                    for model in models_to_run
                    for date in available_dates
                    if date >= model_start_dates[model]
                ]

            # Check if can start new job
            if not job_manager.can_start_new_job():
                raise HTTPException(
                    status_code=400,
                    detail="Another simulation job is already running or pending. Please wait for it to complete."
                )

            # Create job with dates that will be run
            # Pass model_day_tasks to only create job_details for tasks that will actually run
            job_id = job_manager.create_job(
                config_path=config_path,
                date_range=dates_to_run,
                models=models_to_run,
                model_day_filter=model_day_tasks
            )

            # Start worker in background thread (only if not in test mode)
            if not getattr(app.state, "test_mode", False):
                def run_worker():
                    worker = SimulationWorker(job_id=job_id, db_path=app.state.db_path)
                    worker.run()

                thread = threading.Thread(target=run_worker, daemon=True)
                thread.start()

            logger.info(f"Triggered simulation job {job_id} with {len(model_day_tasks)} model-day tasks")

            # Build response message
            total_model_days = len(model_day_tasks)
            message_parts = [f"Simulation job created with {total_model_days} model-day tasks"]

            if request.start_date is None:
                message_parts.append("(resume mode)")

            if not request.replace_existing:
                # Calculate how many were skipped
                total_possible = len(models_to_run) * len(available_dates)
                skipped = total_possible - total_model_days
                if skipped > 0:
                    message_parts.append(f"({skipped} already completed, skipped)")

            if download_info and download_info["rate_limited"]:
                message_parts.append("(rate limit reached - partial data)")

            message = " ".join(message_parts)

            # Get deployment mode info
            deployment_info = get_deployment_mode_dict()

            response = SimulateTriggerResponse(
                job_id=job_id,
                status="pending",
                total_model_days=total_model_days,
                message=message,
                **deployment_info
            )

            # Add download info if we downloaded
            if download_info:
                # Note: Need to add download_info field to response model
                logger.info(f"Download info: {download_info}")

            return response

        except HTTPException:
            raise
        except ValueError as e:
            logger.error(f"Validation error: {e}")
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error(f"Failed to trigger simulation: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

    @app.get("/simulate/status/{job_id}", response_model=JobStatusResponse)
    async def get_job_status(job_id: str):
        """
        Get status and progress of a simulation job.

        Args:
            job_id: Job UUID

        Returns:
            Job status, progress, and model-day details

        Raises:
            HTTPException 404: If job not found
        """
        try:
            job_manager = JobManager(db_path=app.state.db_path)

            # Get job info
            job = job_manager.get_job(job_id)
            if not job:
                raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

            # Get progress
            progress = job_manager.get_job_progress(job_id)

            # Get model-day details
            details = job_manager.get_job_details(job_id)

            # Calculate pending (total - completed - failed)
            pending = progress["total_model_days"] - progress["completed"] - progress["failed"]

            # Get deployment mode info
            deployment_info = get_deployment_mode_dict()

            return JobStatusResponse(
                job_id=job["job_id"],
                status=job["status"],
                progress=JobProgress(
                    total_model_days=progress["total_model_days"],
                    completed=progress["completed"],
                    failed=progress["failed"],
                    pending=pending
                ),
                date_range=job["date_range"],
                models=job["models"],
                created_at=job["created_at"],
                started_at=job.get("started_at"),
                completed_at=job.get("completed_at"),
                total_duration_seconds=job.get("total_duration_seconds"),
                error=job.get("error"),
                details=details,
                **deployment_info
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to get job status: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

    @app.get("/results")
    async def get_results(
        job_id: Optional[str] = Query(None, description="Filter by job ID"),
        date: Optional[str] = Query(None, description="Filter by date (YYYY-MM-DD)"),
        model: Optional[str] = Query(None, description="Filter by model signature")
    ):
        """
        Query simulation results.

        Supports filtering by job_id, date, and/or model.
        Returns position data with holdings.

        Args:
            job_id: Optional job UUID filter
            date: Optional date filter (YYYY-MM-DD)
            model: Optional model signature filter

        Returns:
            List of position records with holdings
        """
        try:
            conn = get_db_connection(app.state.db_path)
            cursor = conn.cursor()

            # Build query with filters
            query = """
                SELECT
                    p.id,
                    p.job_id,
                    p.date,
                    p.model,
                    p.action_id,
                    p.action_type,
                    p.symbol,
                    p.amount,
                    p.price,
                    p.cash,
                    p.portfolio_value,
                    p.daily_profit,
                    p.daily_return_pct,
                    p.created_at
                FROM positions p
                WHERE 1=1
            """
            params = []

            if job_id:
                query += " AND p.job_id = ?"
                params.append(job_id)

            if date:
                query += " AND p.date = ?"
                params.append(date)

            if model:
                query += " AND p.model = ?"
                params.append(model)

            query += " ORDER BY p.date, p.model, p.action_id"

            cursor.execute(query, params)
            rows = cursor.fetchall()

            results = []
            for row in rows:
                position_id = row[0]

                # Get holdings for this position
                cursor.execute("""
                    SELECT symbol, quantity
                    FROM holdings
                    WHERE position_id = ?
                    ORDER BY symbol
                """, (position_id,))

                holdings = [{"symbol": h[0], "quantity": h[1]} for h in cursor.fetchall()]

                results.append({
                    "id": row[0],
                    "job_id": row[1],
                    "date": row[2],
                    "model": row[3],
                    "action_id": row[4],
                    "action_type": row[5],
                    "symbol": row[6],
                    "amount": row[7],
                    "price": row[8],
                    "cash": row[9],
                    "portfolio_value": row[10],
                    "daily_profit": row[11],
                    "daily_return_pct": row[12],
                    "created_at": row[13],
                    "holdings": holdings
                })

            conn.close()

            return {"results": results, "count": len(results)}

        except Exception as e:
            logger.error(f"Failed to query results: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

    @app.get("/health", response_model=HealthResponse)
    async def health_check():
        """
        Health check endpoint.

        Verifies database connectivity and service status.

        Returns:
            Health status and timestamp
        """
        try:
            # Test database connection
            conn = get_db_connection(app.state.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            conn.close()

            database_status = "connected"

        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            database_status = "disconnected"

        # Get deployment mode info
        deployment_info = get_deployment_mode_dict()

        return HealthResponse(
            status="healthy" if database_status == "connected" else "unhealthy",
            database=database_status,
            timestamp=datetime.utcnow().isoformat() + "Z",
            **deployment_info
        )

    return app


# Create default app instance
app = create_app()


if __name__ == "__main__":
    import uvicorn

    # Display DEV mode warning if applicable
    log_dev_mode_startup_warning()

    uvicorn.run(app, host="0.0.0.0", port=8080)
