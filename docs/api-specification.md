# AI-Trader API Service - Technical Specification

## 1. API Endpoints Specification

### 1.1 POST /simulate/trigger

**Purpose:** Trigger a catch-up simulation from the last completed date to the most recent trading day.

**Request:**
```http
POST /simulate/trigger HTTP/1.1
Content-Type: application/json

{
  "config_path": "configs/default_config.json"  // Optional: defaults to configs/default_config.json
}
```

**Response (202 Accepted):**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "accepted",
  "date_range": ["2025-01-16", "2025-01-17", "2025-01-20"],
  "models": ["claude-3.7-sonnet", "gpt-5"],
  "created_at": "2025-01-20T14:30:00Z",
  "message": "Simulation job queued successfully"
}
```

**Response (200 OK - Job Already Running):**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "running",
  "date_range": ["2025-01-16", "2025-01-17", "2025-01-20"],
  "models": ["claude-3.7-sonnet", "gpt-5"],
  "progress": {
    "total_model_days": 6,
    "completed": 3,
    "failed": 0,
    "current": {
      "date": "2025-01-17",
      "model": "gpt-5"
    }
  },
  "created_at": "2025-01-20T14:25:00Z",
  "message": "Simulation already in progress"
}
```

**Response (200 OK - Already Up To Date):**
```json
{
  "status": "current",
  "message": "Simulation already up-to-date",
  "last_simulation_date": "2025-01-20",
  "next_trading_day": "2025-01-21"
}
```

**Response (409 Conflict):**
```json
{
  "error": "conflict",
  "message": "Different simulation already running",
  "current_job_id": "previous-job-uuid",
  "current_date_range": ["2025-01-10", "2025-01-15"]
}
```

**Business Logic:**
1. Load configuration from `config_path` (or default)
2. Determine last completed date from each model's `position.jsonl`
3. Calculate date range: `max(last_dates) + 1 day` → `most_recent_trading_day`
4. Filter for weekdays only (Monday-Friday)
5. If date_range is empty, return "already up-to-date"
6. Check for existing jobs with same date range → return existing job
7. Check for running jobs with different date range → return 409
8. Create new job in SQLite with status=`pending`
9. Queue background task to execute simulation
10. Return 202 with job details

---

### 1.2 GET /simulate/status/{job_id}

**Purpose:** Poll the status and progress of a simulation job.

**Request:**
```http
GET /simulate/status/550e8400-e29b-41d4-a716-446655440000 HTTP/1.1
```

**Response (200 OK - Running):**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "running",
  "date_range": ["2025-01-16", "2025-01-17", "2025-01-20"],
  "models": ["claude-3.7-sonnet", "gpt-5"],
  "progress": {
    "total_model_days": 6,
    "completed": 3,
    "failed": 0,
    "current": {
      "date": "2025-01-17",
      "model": "gpt-5"
    },
    "details": [
      {"date": "2025-01-16", "model": "claude-3.7-sonnet", "status": "completed", "duration_seconds": 45.2},
      {"date": "2025-01-16", "model": "gpt-5", "status": "completed", "duration_seconds": 38.7},
      {"date": "2025-01-17", "model": "claude-3.7-sonnet", "status": "completed", "duration_seconds": 42.1},
      {"date": "2025-01-17", "model": "gpt-5", "status": "running", "duration_seconds": null}
    ]
  },
  "created_at": "2025-01-20T14:25:00Z",
  "updated_at": "2025-01-20T14:27:15Z"
}
```

**Response (200 OK - Completed):**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "date_range": ["2025-01-16", "2025-01-17", "2025-01-20"],
  "models": ["claude-3.7-sonnet", "gpt-5"],
  "progress": {
    "total_model_days": 6,
    "completed": 6,
    "failed": 0,
    "details": [
      {"date": "2025-01-16", "model": "claude-3.7-sonnet", "status": "completed", "duration_seconds": 45.2},
      {"date": "2025-01-16", "model": "gpt-5", "status": "completed", "duration_seconds": 38.7},
      {"date": "2025-01-17", "model": "claude-3.7-sonnet", "status": "completed", "duration_seconds": 42.1},
      {"date": "2025-01-17", "model": "gpt-5", "status": "completed", "duration_seconds": 40.3},
      {"date": "2025-01-20", "model": "claude-3.7-sonnet", "status": "completed", "duration_seconds": 43.8},
      {"date": "2025-01-20", "model": "gpt-5", "status": "completed", "duration_seconds": 39.1}
    ]
  },
  "created_at": "2025-01-20T14:25:00Z",
  "completed_at": "2025-01-20T14:29:45Z",
  "total_duration_seconds": 285.0
}
```

**Response (200 OK - Partial Failure):**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "partial",
  "date_range": ["2025-01-16", "2025-01-17", "2025-01-20"],
  "models": ["claude-3.7-sonnet", "gpt-5"],
  "progress": {
    "total_model_days": 6,
    "completed": 4,
    "failed": 2,
    "details": [
      {"date": "2025-01-16", "model": "claude-3.7-sonnet", "status": "completed", "duration_seconds": 45.2},
      {"date": "2025-01-16", "model": "gpt-5", "status": "completed", "duration_seconds": 38.7},
      {"date": "2025-01-17", "model": "claude-3.7-sonnet", "status": "failed", "error": "MCP service timeout after 3 retries", "duration_seconds": null},
      {"date": "2025-01-17", "model": "gpt-5", "status": "completed", "duration_seconds": 40.3},
      {"date": "2025-01-20", "model": "claude-3.7-sonnet", "status": "completed", "duration_seconds": 43.8},
      {"date": "2025-01-20", "model": "gpt-5", "status": "failed", "error": "AI model API timeout", "duration_seconds": null}
    ]
  },
  "created_at": "2025-01-20T14:25:00Z",
  "completed_at": "2025-01-20T14:29:45Z"
}
```

**Response (404 Not Found):**
```json
{
  "error": "not_found",
  "message": "Job not found",
  "job_id": "invalid-job-id"
}
```

**Business Logic:**
1. Query SQLite jobs table for job_id
2. If not found, return 404
3. Return job metadata + progress from job_details table
4. Status transitions: `pending` → `running` → `completed`/`partial`/`failed`

---

### 1.3 GET /simulate/current

**Purpose:** Get the most recent simulation job (for Windmill to discover job_id).

**Request:**
```http
GET /simulate/current HTTP/1.1
```

**Response (200 OK):**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "running",
  "date_range": ["2025-01-16", "2025-01-17"],
  "models": ["claude-3.7-sonnet", "gpt-5"],
  "progress": {
    "total_model_days": 4,
    "completed": 2,
    "failed": 0
  },
  "created_at": "2025-01-20T14:25:00Z"
}
```

**Response (404 Not Found):**
```json
{
  "error": "not_found",
  "message": "No simulation jobs found"
}
```

**Business Logic:**
1. Query SQLite: `SELECT * FROM jobs ORDER BY created_at DESC LIMIT 1`
2. Return job details with progress summary

---

### 1.4 GET /results

**Purpose:** Retrieve simulation results for a specific date and model.

**Request:**
```http
GET /results?date=2025-01-15&model=gpt-5&detail=minimal HTTP/1.1
```

**Query Parameters:**
- `date` (required): Trading date in YYYY-MM-DD format
- `model` (optional): Model signature (if omitted, returns all models)
- `detail` (optional): Response detail level
  - `minimal` (default): Positions + daily P&L
  - `full`: + trade history + AI reasoning logs + tool usage stats

**Response (200 OK - minimal):**
```json
{
  "date": "2025-01-15",
  "results": [
    {
      "model": "gpt-5",
      "positions": {
        "AAPL": 10,
        "MSFT": 5,
        "NVDA": 0,
        "CASH": 8500.00
      },
      "daily_pnl": {
        "profit": 150.50,
        "return_pct": 1.5,
        "portfolio_value": 10150.50
      }
    }
  ]
}
```

**Response (200 OK - full):**
```json
{
  "date": "2025-01-15",
  "results": [
    {
      "model": "gpt-5",
      "positions": {
        "AAPL": 10,
        "MSFT": 5,
        "CASH": 8500.00
      },
      "daily_pnl": {
        "profit": 150.50,
        "return_pct": 1.5,
        "portfolio_value": 10150.50
      },
      "trades": [
        {
          "id": 1,
          "action": "buy",
          "symbol": "AAPL",
          "amount": 10,
          "price": 255.88,
          "total": 2558.80
        }
      ],
      "ai_reasoning": {
        "total_steps": 15,
        "stop_signal_received": true,
        "reasoning_summary": "Market analysis indicated strong buy signal for AAPL...",
        "tool_usage": {
          "search": 3,
          "get_price": 5,
          "math": 2,
          "trade": 1
        }
      },
      "log_file_path": "data/agent_data/gpt-5/log/2025-01-15/log.jsonl"
    }
  ]
}
```

**Response (400 Bad Request):**
```json
{
  "error": "invalid_date",
  "message": "Date must be in YYYY-MM-DD format"
}
```

**Response (404 Not Found):**
```json
{
  "error": "no_data",
  "message": "No simulation data found for date 2025-01-15 and model gpt-5"
}
```

**Business Logic:**
1. Validate date format
2. Read `position.jsonl` for specified model(s) and date
3. For `detail=minimal`: Return positions + calculate daily P&L
4. For `detail=full`:
   - Parse `log.jsonl` to extract reasoning summary
   - Count tool usage from log messages
   - Extract trades from position file
5. Return aggregated results

---

### 1.5 GET /health

**Purpose:** Health check endpoint for Docker and monitoring.

**Request:**
```http
GET /health HTTP/1.1
```

**Response (200 OK):**
```json
{
  "status": "healthy",
  "timestamp": "2025-01-20T14:30:00Z",
  "services": {
    "mcp_math": {"status": "up", "url": "http://localhost:8000/mcp"},
    "mcp_search": {"status": "up", "url": "http://localhost:8001/mcp"},
    "mcp_trade": {"status": "up", "url": "http://localhost:8002/mcp"},
    "mcp_getprice": {"status": "up", "url": "http://localhost:8003/mcp"}
  },
  "storage": {
    "data_directory": "/app/data",
    "writable": true,
    "free_space_mb": 15234
  },
  "database": {
    "status": "connected",
    "path": "/app/data/jobs.db"
  }
}
```

**Response (503 Service Unavailable):**
```json
{
  "status": "unhealthy",
  "timestamp": "2025-01-20T14:30:00Z",
  "services": {
    "mcp_math": {"status": "down", "url": "http://localhost:8000/mcp", "error": "Connection refused"},
    "mcp_search": {"status": "up", "url": "http://localhost:8001/mcp"},
    "mcp_trade": {"status": "up", "url": "http://localhost:8002/mcp"},
    "mcp_getprice": {"status": "up", "url": "http://localhost:8003/mcp"}
  },
  "storage": {
    "data_directory": "/app/data",
    "writable": true
  },
  "database": {
    "status": "connected"
  }
}
```

---

## 2. Data Models

### 2.1 SQLite Schema

**Table: jobs**
```sql
CREATE TABLE jobs (
    job_id TEXT PRIMARY KEY,
    config_path TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('pending', 'running', 'completed', 'partial', 'failed')),
    date_range TEXT NOT NULL,  -- JSON array of dates
    models TEXT NOT NULL,      -- JSON array of model signatures
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    total_duration_seconds REAL,
    error TEXT
);

CREATE INDEX idx_jobs_status ON jobs(status);
CREATE INDEX idx_jobs_created_at ON jobs(created_at DESC);
```

**Table: job_details**
```sql
CREATE TABLE job_details (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    date TEXT NOT NULL,
    model TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('pending', 'running', 'completed', 'failed')),
    started_at TEXT,
    completed_at TEXT,
    duration_seconds REAL,
    error TEXT,
    FOREIGN KEY (job_id) REFERENCES jobs(job_id) ON DELETE CASCADE
);

CREATE INDEX idx_job_details_job_id ON job_details(job_id);
CREATE INDEX idx_job_details_status ON job_details(status);
```

### 2.2 Pydantic Models

**Request Models:**
```python
from pydantic import BaseModel, Field
from typing import Optional, Literal

class TriggerSimulationRequest(BaseModel):
    config_path: Optional[str] = Field(default="configs/default_config.json", description="Path to configuration file")

class ResultsQueryParams(BaseModel):
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="Date in YYYY-MM-DD format")
    model: Optional[str] = Field(None, description="Model signature filter")
    detail: Literal["minimal", "full"] = Field(default="minimal", description="Response detail level")
```

**Response Models:**
```python
class JobProgress(BaseModel):
    total_model_days: int
    completed: int
    failed: int
    current: Optional[dict] = None  # {"date": str, "model": str}
    details: Optional[list] = None  # List of JobDetailResponse

class TriggerSimulationResponse(BaseModel):
    job_id: str
    status: str
    date_range: list[str]
    models: list[str]
    created_at: str
    message: str
    progress: Optional[JobProgress] = None

class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    date_range: list[str]
    models: list[str]
    progress: JobProgress
    created_at: str
    updated_at: Optional[str] = None
    completed_at: Optional[str] = None
    total_duration_seconds: Optional[float] = None

class DailyPnL(BaseModel):
    profit: float
    return_pct: float
    portfolio_value: float

class Trade(BaseModel):
    id: int
    action: str
    symbol: str
    amount: int
    price: Optional[float] = None
    total: Optional[float] = None

class AIReasoning(BaseModel):
    total_steps: int
    stop_signal_received: bool
    reasoning_summary: str
    tool_usage: dict[str, int]

class ModelResult(BaseModel):
    model: str
    positions: dict[str, float]
    daily_pnl: DailyPnL
    trades: Optional[list[Trade]] = None
    ai_reasoning: Optional[AIReasoning] = None
    log_file_path: Optional[str] = None

class ResultsResponse(BaseModel):
    date: str
    results: list[ModelResult]
```

---

## 3. Configuration Management

### 3.1 Environment Variables

Required environment variables remain the same as batch mode:
```bash
# OpenAI API Configuration
OPENAI_API_BASE=https://api.openai.com/v1
OPENAI_API_KEY=sk-...

# Alpha Vantage API
ALPHAADVANTAGE_API_KEY=...

# Jina Search API
JINA_API_KEY=...

# Runtime Config Path (now shared by API and worker)
RUNTIME_ENV_PATH=/app/data/runtime_env.json

# MCP Service Ports
MATH_HTTP_PORT=8000
SEARCH_HTTP_PORT=8001
TRADE_HTTP_PORT=8002
GETPRICE_HTTP_PORT=8003

# API Server Configuration
API_HOST=0.0.0.0
API_PORT=8080

# Job Configuration
MAX_CONCURRENT_JOBS=1  # Only one simulation job at a time
```

### 3.2 Runtime State Management

**Challenge:** Multiple model-days running concurrently need isolated `runtime_env.json` state.

**Solution:** Per-job runtime config files
- `runtime_env_base.json` - Template
- `runtime_env_{job_id}_{model}_{date}.json` - Job-specific runtime config
- Worker passes custom `RUNTIME_ENV_PATH` to each simulation execution

**Modified `write_config_value()` and `get_config_value()`:**
- Accept optional `runtime_path` parameter
- Worker manages lifecycle: create → use → cleanup

---

## 4. Error Handling

### 4.1 Error Response Format

All errors follow this structure:
```json
{
  "error": "error_code",
  "message": "Human-readable error description",
  "details": {
    // Optional additional context
  }
}
```

### 4.2 HTTP Status Codes

- `200 OK` - Successful request
- `202 Accepted` - Job queued successfully
- `400 Bad Request` - Invalid input parameters
- `404 Not Found` - Resource not found (job, results)
- `409 Conflict` - Concurrent job conflict
- `500 Internal Server Error` - Unexpected server error
- `503 Service Unavailable` - Health check failed

### 4.3 Retry Strategy for Workers

Models run independently - failure of one model doesn't block others:
```python
async def run_model_day(job_id: str, date: str, model_config: dict):
    try:
        # Execute simulation for this model-day
        await agent.run_trading_session(date)
        update_job_detail_status(job_id, date, model, "completed")
    except Exception as e:
        # Log error, update status to failed, continue with next model-day
        update_job_detail_status(job_id, date, model, "failed", error=str(e))
        # Do NOT raise - let other models continue
```

---

## 5. Concurrency & Locking

### 5.1 Job Execution Policy

**Rule:** Maximum 1 running job at a time (configurable via `MAX_CONCURRENT_JOBS`)

**Enforcement:**
```python
def can_start_new_job() -> bool:
    running_jobs = db.query(
        "SELECT COUNT(*) FROM jobs WHERE status IN ('pending', 'running')"
    ).fetchone()[0]
    return running_jobs < MAX_CONCURRENT_JOBS
```

### 5.2 Position File Concurrency

**Challenge:** Multiple model-days writing to same model's `position.jsonl`

**Solution:** Sequential execution per model
```python
# For each date in date_range:
#   For each model in parallel:  ← Models run in parallel
#     Execute model-day sequentially  ← Dates for same model run sequentially
```

**Execution Pattern:**
```
Date 2025-01-16:
  - Model A (running)
  - Model B (running)
  - Model C (running)

Date 2025-01-17:  ← Starts only after all models finish 2025-01-16
  - Model A (running)
  - Model B (running)
  - Model C (running)
```

**Rationale:**
- Models write to different position files → No conflict
- Same model's dates run sequentially → No race condition on position.jsonl
- Date-level parallelism across models → Faster overall execution

---

## 6. Performance Considerations

### 6.1 Execution Time Estimates

Based on current implementation:
- Single model-day: ~30-60 seconds (depends on AI model latency + tool calls)
- 3 models × 5 days = 15 model-days ≈ 7.5-15 minutes (parallel execution)

### 6.2 Timeout Configuration

**API Request Timeout:**
- `/simulate/trigger`: 10 seconds (just queue job)
- `/simulate/status`: 5 seconds (read from DB)
- `/results`: 30 seconds (file I/O + parsing)

**Worker Timeout:**
- Per model-day: 5 minutes (inherited from `max_retries` × `base_delay`)
- Entire job: No timeout (job runs until all model-days complete or fail)

### 6.3 Optimization Opportunities (Future)

1. **Results caching:** Store computed daily_pnl in SQLite to avoid recomputation
2. **Parallel date execution:** If position file locking is implemented, run dates in parallel
3. **Streaming responses:** For `/simulate/status`, use SSE to push updates instead of polling

---

## 7. Logging & Observability

### 7.1 Structured Logging

All API logs use JSON format:
```json
{
  "timestamp": "2025-01-20T14:30:00Z",
  "level": "INFO",
  "logger": "api.worker",
  "message": "Starting simulation for model-day",
  "job_id": "550e8400-...",
  "date": "2025-01-16",
  "model": "gpt-5"
}
```

### 7.2 Log Levels

- `DEBUG` - Detailed execution flow (tool calls, price fetches)
- `INFO` - Job lifecycle events (created, started, completed)
- `WARNING` - Recoverable errors (retry attempts)
- `ERROR` - Model-day failures (logged but job continues)
- `CRITICAL` - System failures (MCP services down, DB corruption)

### 7.3 Audit Trail

All job state transitions logged to `api_audit.log`:
```json
{
  "timestamp": "2025-01-20T14:30:00Z",
  "event": "job_created",
  "job_id": "550e8400-...",
  "user": "windmill-service",  // Future: from auth header
  "details": {"date_range": [...], "models": [...]}
}
```

---

## 8. Security Considerations

### 8.1 Authentication (Future)

For MVP, API relies on network isolation (Docker network). Future enhancements:
- API key authentication via header: `X-API-Key: <token>`
- JWT tokens for Windmill integration
- Rate limiting per API key

### 8.2 Input Validation

- All date parameters validated with regex: `^\d{4}-\d{2}-\d{2}$`
- Config paths restricted to `configs/` directory (prevent path traversal)
- Model signatures sanitized (alphanumeric + hyphens only)

### 8.3 File Access Controls

- Results API only reads from `data/agent_data/` directory
- Config API only reads from `configs/` directory
- No arbitrary file read via API parameters

---

## 9. Deployment Configuration

### 9.1 Docker Compose

```yaml
version: '3.8'

services:
  ai-trader-api:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "8080:8080"
    volumes:
      - ./data:/app/data
      - ./configs:/app/configs
    env_file:
      - .env
    environment:
      - MODE=api
      - API_PORT=8080
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    restart: unless-stopped
```

### 9.2 Dockerfile Modifications

```dockerfile
# ... existing layers ...

# Install API dependencies
COPY requirements-api.txt /app/
RUN pip install --no-cache-dir -r requirements-api.txt

# Copy API application code
COPY api/ /app/api/

# Copy entrypoint script
COPY docker-entrypoint.sh /app/
RUN chmod +x /app/docker-entrypoint.sh

EXPOSE 8080

CMD ["/app/docker-entrypoint.sh"]
```

### 9.3 Entrypoint Script

```bash
#!/bin/bash
set -e

echo "Starting MCP services..."
cd /app/agent_tools
python start_mcp_services.py &
MCP_PID=$!

echo "Waiting for MCP services to be ready..."
sleep 10

echo "Starting API server..."
cd /app
uvicorn api.main:app --host ${API_HOST:-0.0.0.0} --port ${API_PORT:-8080} --workers 1

# Cleanup on exit
trap "kill $MCP_PID 2>/dev/null || true" EXIT
```

---

## 10. API Versioning (Future)

For v2 and beyond:
- URL prefix: `/api/v1/simulate/trigger`, `/api/v2/simulate/trigger`
- Header-based: `Accept: application/vnd.ai-trader.v1+json`

MVP uses unversioned endpoints (implied v1).

---

## Next Steps

After reviewing this specification, we'll proceed to:
1. **Component 2:** Job Manager & SQLite Schema Implementation
2. **Component 3:** Background Worker Architecture
3. **Component 4:** BaseAgent Refactoring for Single-Day Execution
4. **Component 5:** Docker & Deployment Configuration
5. **Component 6:** Windmill Integration Flows

Please review this API specification and provide feedback or approval to continue.
