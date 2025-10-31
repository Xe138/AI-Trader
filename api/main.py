"""
FastAPI REST API for AI-Trader simulation service.

Provides endpoints for:
- Triggering simulation jobs
- Checking job status
- Querying results
- Health checks
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from api.job_manager import JobManager
from api.simulation_worker import SimulationWorker
from api.database import get_db_connection
import threading
import time

logger = logging.getLogger(__name__)


# Pydantic models for request/response validation
class SimulateTriggerRequest(BaseModel):
    """Request body for POST /simulate/trigger."""
    config_path: str = Field(..., description="Path to configuration file")
    date_range: List[str] = Field(..., min_length=1, description="List of trading dates (YYYY-MM-DD)")
    models: Optional[List[str]] = Field(
        None,
        description="Optional: List of model signatures to simulate. If not provided, uses enabled models from config."
    )

    @field_validator("date_range")
    @classmethod
    def validate_date_range(cls, v):
        """Validate date format."""
        for date in v:
            try:
                datetime.strptime(date, "%Y-%m-%d")
            except ValueError:
                raise ValueError(f"Invalid date format: {date}. Expected YYYY-MM-DD")
        return v


class SimulateTriggerResponse(BaseModel):
    """Response body for POST /simulate/trigger."""
    job_id: str
    status: str
    total_model_days: int
    message: str


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


class HealthResponse(BaseModel):
    """Response body for GET /health."""
    status: str
    database: str
    timestamp: str


def create_app(db_path: str = "data/jobs.db") -> FastAPI:
    """
    Create FastAPI application instance.

    Args:
        db_path: Path to SQLite database

    Returns:
        Configured FastAPI app
    """
    app = FastAPI(
        title="AI-Trader Simulation API",
        description="REST API for triggering and monitoring AI trading simulations",
        version="1.0.0"
    )

    # Store db_path in app state
    app.state.db_path = db_path

    @app.post("/simulate/trigger", response_model=SimulateTriggerResponse, status_code=200)
    async def trigger_simulation(request: SimulateTriggerRequest):
        """
        Trigger a new simulation job.

        Creates a job with specified config, dates, and models from config file.
        If models not specified in request, uses enabled models from config.
        Job runs asynchronously in background thread.

        Raises:
            HTTPException 400: If another job is already running or config invalid
            HTTPException 422: If request validation fails
        """
        try:
            # Validate config path exists
            if not Path(request.config_path).exists():
                raise HTTPException(
                    status_code=400,
                    detail=f"Config path does not exist: {request.config_path}"
                )

            # Determine which models to run
            import json
            with open(request.config_path, 'r') as f:
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

            # Check if can start new job
            if not job_manager.can_start_new_job():
                raise HTTPException(
                    status_code=400,
                    detail="Another simulation job is already running or pending. Please wait for it to complete."
                )

            # Create job
            job_id = job_manager.create_job(
                config_path=request.config_path,
                date_range=request.date_range,
                models=models_to_run
            )

            # Start worker in background thread (only if not in test mode)
            if not getattr(app.state, "test_mode", False):
                def run_worker():
                    worker = SimulationWorker(job_id=job_id, db_path=app.state.db_path)
                    worker.run()

                thread = threading.Thread(target=run_worker, daemon=True)
                thread.start()

            logger.info(f"Triggered simulation job {job_id}")

            return SimulateTriggerResponse(
                job_id=job_id,
                status="pending",
                total_model_days=len(request.date_range) * len(models_to_run),
                message=f"Simulation job {job_id} created and started with {len(models_to_run)} models"
            )

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
                details=details
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

        return HealthResponse(
            status="healthy" if database_status == "connected" else "unhealthy",
            database=database_status,
            timestamp=datetime.utcnow().isoformat() + "Z"
        )

    return app


# Create default app instance
app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
