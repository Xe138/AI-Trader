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
from contextlib import asynccontextmanager

from api.job_manager import JobManager
from api.simulation_worker import SimulationWorker
from api.database import get_db_connection
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
    warnings: Optional[List[str]] = None


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
    warnings: Optional[List[str]] = None


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
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Initialize database on startup, cleanup on shutdown if needed"""
        print("=" * 80)
        print("🔍 DIAGNOSTIC: LIFESPAN FUNCTION CALLED!")
        print("=" * 80)

        from tools.deployment_config import is_dev_mode, get_db_path
        from api.database import initialize_dev_database, initialize_database

        # Startup - use closure to access db_path from create_app scope
        logger.info("🚀 FastAPI application starting...")
        logger.info("📊 Initializing database...")
        print(f"🔍 DIAGNOSTIC: Lifespan - db_path from closure: {db_path}")

        deployment_mode = is_dev_mode()
        print(f"🔍 DIAGNOSTIC: Lifespan - is_dev_mode() returned: {deployment_mode}")

        if deployment_mode:
            # Initialize dev database (reset unless PRESERVE_DEV_DATA=true)
            logger.info("  🔧 DEV mode detected - initializing dev database")
            print("🔍 DIAGNOSTIC: Lifespan - DEV mode detected")
            dev_db_path = get_db_path(db_path)
            print(f"🔍 DIAGNOSTIC: Lifespan - Resolved dev database path: {dev_db_path}")
            print(f"🔍 DIAGNOSTIC: Lifespan - About to call initialize_dev_database({dev_db_path})")
            initialize_dev_database(dev_db_path)
            print(f"🔍 DIAGNOSTIC: Lifespan - initialize_dev_database() completed")
            log_dev_mode_startup_warning()
        else:
            # Ensure production database schema exists
            logger.info("  🏭 PROD mode - ensuring database schema exists")
            print("🔍 DIAGNOSTIC: Lifespan - PROD mode detected")
            print(f"🔍 DIAGNOSTIC: Lifespan - About to call initialize_database({db_path})")
            initialize_database(db_path)
            print(f"🔍 DIAGNOSTIC: Lifespan - initialize_database() completed")

        logger.info("✅ Database initialized")
        logger.info("🌐 API server ready to accept requests")
        print("🔍 DIAGNOSTIC: Lifespan - Startup complete, yielding control")
        print("=" * 80)

        yield

        # Shutdown (if needed in future)
        logger.info("🛑 FastAPI application shutting down...")
        print("🔍 DIAGNOSTIC: LIFESPAN SHUTDOWN CALLED")

    app = FastAPI(
        title="AI-Trader Simulation API",
        description="REST API for triggering and monitoring AI trading simulations",
        version="1.0.0",
        lifespan=lifespan
    )

    # Store paths in app state
    app.state.db_path = db_path
    app.state.config_path = config_path

    @app.post("/simulate/trigger", response_model=SimulateTriggerResponse, status_code=200)
    async def trigger_simulation(request: SimulateTriggerRequest):
        """
        Trigger a new simulation job.

        Validates date range and creates job. Price data is downloaded
        in background by SimulationWorker.

        Supports:
        - Single date: start_date == end_date
        - Date range: start_date < end_date
        - Resume: start_date is null (each model resumes from its last completed date)

        Raises:
            HTTPException 400: Validation errors, running job, or invalid dates
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

            if request.models is not None and len(request.models) > 0:
                # Use models from request (explicit override)
                models_to_run = request.models
            else:
                # Use enabled models from config (when models is None or empty list)
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
                from datetime import timedelta
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

            # Check if can start new job
            if not job_manager.can_start_new_job():
                raise HTTPException(
                    status_code=400,
                    detail="Another simulation job is already running or pending. Please wait for it to complete."
                )

            # Get all weekdays in range (worker will filter based on data availability)
            all_dates = expand_date_range(start_date, end_date)

            # Create job immediately with all requested dates
            # Worker will handle data download and filtering
            job_id = job_manager.create_job(
                config_path=config_path,
                date_range=all_dates,
                models=models_to_run,
                model_day_filter=None  # Worker will filter based on available data
            )

            # Start worker in background thread (only if not in test mode)
            if not getattr(app.state, "test_mode", False):
                def run_worker():
                    worker = SimulationWorker(job_id=job_id, db_path=app.state.db_path)
                    worker.run()

                thread = threading.Thread(target=run_worker, daemon=True)
                thread.start()

            logger.info(f"Triggered simulation job {job_id} for {len(all_dates)} dates, {len(models_to_run)} models")

            # Build response message
            message = f"Simulation job created for {len(all_dates)} dates, {len(models_to_run)} models"

            if request.start_date is None:
                message += " (resume mode)"

            # Get deployment mode info
            deployment_info = get_deployment_mode_dict()

            response = SimulateTriggerResponse(
                job_id=job_id,
                status="pending",
                total_model_days=len(all_dates) * len(models_to_run),
                message=message,
                **deployment_info
            )

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
            Job status, progress, model-day details, and warnings

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

            # Parse warnings from JSON if present
            import json
            warnings = None
            if job.get("warnings"):
                try:
                    warnings = json.loads(job["warnings"])
                except (json.JSONDecodeError, TypeError):
                    logger.warning(f"Failed to parse warnings for job {job_id}")

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
                warnings=warnings,
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
print("=" * 80)
print("🔍 DIAGNOSTIC: Module api.main is being imported/executed")
print("=" * 80)

app = create_app()
print(f"🔍 DIAGNOSTIC: create_app() completed, app object created: {app}")

# Ensure database is initialized when module is loaded
# This handles cases where lifespan might not be triggered properly
print("🔍 DIAGNOSTIC: Starting module-level database initialization check...")
logger.info("🔧 Module-level database initialization check...")

from tools.deployment_config import is_dev_mode, get_db_path
from api.database import initialize_dev_database, initialize_database

_db_path = app.state.db_path
print(f"🔍 DIAGNOSTIC: app.state.db_path = {_db_path}")

deployment_mode = is_dev_mode()
print(f"🔍 DIAGNOSTIC: is_dev_mode() returned: {deployment_mode}")

if deployment_mode:
    print("🔍 DIAGNOSTIC: DEV mode detected - initializing dev database at module load")
    logger.info("  🔧 DEV mode - initializing dev database at module load")
    _dev_db_path = get_db_path(_db_path)
    print(f"🔍 DIAGNOSTIC: Resolved dev database path: {_dev_db_path}")
    print(f"🔍 DIAGNOSTIC: About to call initialize_dev_database({_dev_db_path})")
    initialize_dev_database(_dev_db_path)
    print(f"🔍 DIAGNOSTIC: initialize_dev_database() completed successfully")
else:
    print("🔍 DIAGNOSTIC: PROD mode - ensuring database exists at module load")
    logger.info("  🏭 PROD mode - ensuring database exists at module load")
    print(f"🔍 DIAGNOSTIC: About to call initialize_database({_db_path})")
    initialize_database(_db_path)
    print(f"🔍 DIAGNOSTIC: initialize_database() completed successfully")

print("🔍 DIAGNOSTIC: Module-level database initialization complete")
logger.info("✅ Module-level database initialization complete")
print("=" * 80)


if __name__ == "__main__":
    import uvicorn

    # Note: Database initialization happens in lifespan AND at module load
    # for maximum reliability

    uvicorn.run(app, host="0.0.0.0", port=8080)
