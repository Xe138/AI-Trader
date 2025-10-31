"""
Pydantic data models for AI-Trader API.

This module defines:
- Request models (input validation)
- Response models (output serialization)
- Nested models for complex data structures
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Literal, Any
from datetime import datetime


# ==================== Request Models ====================

class TriggerSimulationRequest(BaseModel):
    """Request model for POST /simulate/trigger endpoint."""

    config_path: str = Field(
        default="configs/default_config.json",
        description="Path to configuration file"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "config_path": "configs/default_config.json"
            }
        }


class ResultsQueryParams(BaseModel):
    """Query parameters for GET /results endpoint."""

    date: str = Field(
        ...,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="Date in YYYY-MM-DD format"
    )
    model: Optional[str] = Field(
        None,
        description="Model signature filter (optional)"
    )
    detail: Literal["minimal", "full"] = Field(
        default="minimal",
        description="Response detail level"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "date": "2025-01-16",
                "model": "gpt-5",
                "detail": "minimal"
            }
        }


# ==================== Nested Response Models ====================

class JobProgress(BaseModel):
    """Progress tracking for simulation jobs."""

    total_model_days: int = Field(
        ...,
        description="Total number of model-days to execute"
    )
    completed: int = Field(
        ...,
        description="Number of model-days completed"
    )
    failed: int = Field(
        ...,
        description="Number of model-days that failed"
    )
    current: Optional[Dict[str, str]] = Field(
        None,
        description="Currently executing model-day (if any)"
    )
    details: Optional[List[Dict]] = Field(
        None,
        description="Detailed progress for each model-day"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "total_model_days": 4,
                "completed": 2,
                "failed": 0,
                "current": {"date": "2025-01-16", "model": "gpt-5"},
                "details": [
                    {
                        "date": "2025-01-16",
                        "model": "gpt-5",
                        "status": "completed",
                        "duration_seconds": 45.2
                    }
                ]
            }
        }


class DailyPnL(BaseModel):
    """Daily profit and loss metrics."""

    profit: float = Field(
        ...,
        description="Daily profit in dollars"
    )
    return_pct: float = Field(
        ...,
        description="Daily return percentage"
    )
    portfolio_value: float = Field(
        ...,
        description="Total portfolio value"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "profit": 150.50,
                "return_pct": 1.51,
                "portfolio_value": 10150.50
            }
        }


class Trade(BaseModel):
    """Individual trade record."""

    id: int = Field(
        ...,
        description="Trade sequence ID"
    )
    action: str = Field(
        ...,
        description="Trade action (buy/sell)"
    )
    symbol: str = Field(
        ...,
        description="Stock symbol"
    )
    amount: int = Field(
        ...,
        description="Number of shares"
    )
    price: Optional[float] = Field(
        None,
        description="Trade price per share"
    )
    total: Optional[float] = Field(
        None,
        description="Total trade value"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "id": 1,
                "action": "buy",
                "symbol": "AAPL",
                "amount": 10,
                "price": 255.88,
                "total": 2558.80
            }
        }


class AIReasoning(BaseModel):
    """AI reasoning and decision-making summary."""

    total_steps: int = Field(
        ...,
        description="Total reasoning steps taken"
    )
    stop_signal_received: bool = Field(
        ...,
        description="Whether AI sent stop signal"
    )
    reasoning_summary: str = Field(
        ...,
        description="Summary of AI reasoning"
    )
    tool_usage: Dict[str, int] = Field(
        ...,
        description="Tool usage counts"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "total_steps": 15,
                "stop_signal_received": True,
                "reasoning_summary": "Market analysis indicates...",
                "tool_usage": {
                    "search": 3,
                    "get_price": 5,
                    "math": 2,
                    "trade": 1
                }
            }
        }


class ModelResult(BaseModel):
    """Simulation results for a single model on a single date."""

    model: str = Field(
        ...,
        description="Model signature"
    )
    positions: Dict[str, float] = Field(
        ...,
        description="Current positions (symbol: quantity)"
    )
    daily_pnl: DailyPnL = Field(
        ...,
        description="Daily P&L metrics"
    )
    trades: Optional[List[Trade]] = Field(
        None,
        description="Trades executed (detail=full only)"
    )
    ai_reasoning: Optional[AIReasoning] = Field(
        None,
        description="AI reasoning summary (detail=full only)"
    )
    log_file_path: Optional[str] = Field(
        None,
        description="Path to detailed log file (detail=full only)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "model": "gpt-5",
                "positions": {
                    "AAPL": 10,
                    "MSFT": 5,
                    "CASH": 7500.0
                },
                "daily_pnl": {
                    "profit": 150.50,
                    "return_pct": 1.51,
                    "portfolio_value": 10150.50
                }
            }
        }


# ==================== Response Models ====================

class TriggerSimulationResponse(BaseModel):
    """Response model for POST /simulate/trigger endpoint."""

    job_id: str = Field(
        ...,
        description="Unique job identifier"
    )
    status: str = Field(
        ...,
        description="Job status (accepted/running/current)"
    )
    date_range: List[str] = Field(
        ...,
        description="Dates to be simulated"
    )
    models: List[str] = Field(
        ...,
        description="Models to execute"
    )
    created_at: str = Field(
        ...,
        description="Job creation timestamp (ISO 8601)"
    )
    message: str = Field(
        ...,
        description="Human-readable status message"
    )
    progress: Optional[JobProgress] = Field(
        None,
        description="Progress (if job already running)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "job_id": "550e8400-e29b-41d4-a716-446655440000",
                "status": "accepted",
                "date_range": ["2025-01-16", "2025-01-17"],
                "models": ["gpt-5", "claude-3.7-sonnet"],
                "created_at": "2025-01-20T14:30:00Z",
                "message": "Simulation job queued successfully"
            }
        }


class JobStatusResponse(BaseModel):
    """Response model for GET /simulate/status/{job_id} endpoint."""

    job_id: str = Field(
        ...,
        description="Job identifier"
    )
    status: str = Field(
        ...,
        description="Job status (pending/running/completed/partial/failed)"
    )
    date_range: List[str] = Field(
        ...,
        description="Dates being simulated"
    )
    models: List[str] = Field(
        ...,
        description="Models being executed"
    )
    progress: JobProgress = Field(
        ...,
        description="Execution progress"
    )
    created_at: str = Field(
        ...,
        description="Job creation timestamp"
    )
    updated_at: Optional[str] = Field(
        None,
        description="Last update timestamp"
    )
    completed_at: Optional[str] = Field(
        None,
        description="Job completion timestamp"
    )
    total_duration_seconds: Optional[float] = Field(
        None,
        description="Total execution duration"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "job_id": "550e8400-e29b-41d4-a716-446655440000",
                "status": "running",
                "date_range": ["2025-01-16", "2025-01-17"],
                "models": ["gpt-5"],
                "progress": {
                    "total_model_days": 2,
                    "completed": 1,
                    "failed": 0,
                    "current": {"date": "2025-01-17", "model": "gpt-5"}
                },
                "created_at": "2025-01-20T14:30:00Z"
            }
        }


class ResultsResponse(BaseModel):
    """Response model for GET /results endpoint."""

    date: str = Field(
        ...,
        description="Trading date"
    )
    results: List[ModelResult] = Field(
        ...,
        description="Results for each model"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "date": "2025-01-16",
                "results": [
                    {
                        "model": "gpt-5",
                        "positions": {"AAPL": 10, "CASH": 7500.0},
                        "daily_pnl": {
                            "profit": 150.50,
                            "return_pct": 1.51,
                            "portfolio_value": 10150.50
                        }
                    }
                ]
            }
        }


class HealthCheckResponse(BaseModel):
    """Response model for GET /health endpoint."""

    status: str = Field(
        ...,
        description="Overall health status (healthy/unhealthy)"
    )
    timestamp: str = Field(
        ...,
        description="Health check timestamp"
    )
    services: Dict[str, Dict] = Field(
        ...,
        description="Status of each service"
    )
    storage: Dict[str, Any] = Field(
        ...,
        description="Storage status"
    )
    database: Dict[str, Any] = Field(
        ...,
        description="Database status"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "status": "healthy",
                "timestamp": "2025-01-20T14:30:00Z",
                "services": {
                    "mcp_math": {"status": "up", "url": "http://localhost:8000/mcp"},
                    "mcp_search": {"status": "up", "url": "http://localhost:8001/mcp"}
                },
                "storage": {
                    "data_directory": "/app/data",
                    "writable": True,
                    "free_space_mb": 15234
                },
                "database": {
                    "status": "connected",
                    "path": "/app/data/jobs.db"
                }
            }
        }


class ErrorResponse(BaseModel):
    """Standard error response model."""

    error: str = Field(
        ...,
        description="Error code/type"
    )
    message: str = Field(
        ...,
        description="Human-readable error message"
    )
    details: Optional[Dict] = Field(
        None,
        description="Additional error details"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "error": "invalid_date",
                "message": "Date must be in YYYY-MM-DD format",
                "details": {"provided": "2025/01/16"}
            }
        }
