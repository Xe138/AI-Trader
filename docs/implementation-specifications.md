# Implementation Specifications: Agent, Docker, and Windmill Integration

## Part 1: BaseAgent Refactoring

### 1.1 Current State Analysis

**Current `base_agent.py` structure:**
- `run_date_range(init_date, end_date)` - Loops through all dates
- `run_trading_session(today_date)` - Executes single day
- `get_trading_dates()` - Calculates dates from position.jsonl

**What works well:**
- `run_trading_session()` is already isolated for single-day execution ✅
- Agent initialization is separate from execution ✅
- Position tracking via position.jsonl ✅

**What needs modification:**
- `runtime_env.json` management (move to RuntimeConfigManager)
- `get_trading_dates()` logic (move to API layer for date range calculation)

### 1.2 Required Changes

#### Change 1: No modifications needed to core execution logic

**Rationale:** `BaseAgent.run_trading_session(today_date)` already supports single-day execution. The worker will call this method directly.

```python
# Current code (already suitable for API mode):
async def run_trading_session(self, today_date: str) -> None:
    """Run single day trading session"""
    # This method is perfect as-is for worker to call
```

**Action:** ✅ No changes needed

---

#### Change 2: Make runtime config path injectable

**Current issue:**
```python
# In base_agent.py, uses global config
from tools.general_tools import get_config_value, write_config_value
```

**Problem:** `get_config_value()` reads from `os.environ["RUNTIME_ENV_PATH"]`, which the worker will override per execution.

**Solution:** Already works! The worker sets `RUNTIME_ENV_PATH` before calling agent methods:

```python
# In executor.py
os.environ["RUNTIME_ENV_PATH"] = runtime_config_path
await agent.run_trading_session(date)
```

**Action:** ✅ No changes needed (env var override is sufficient)

---

#### Change 3: Optional - Separate agent initialization from date-range logic

**Current code in `main.py`:**
```python
# Creates agent
agent = AgentClass(...)
await agent.initialize()

# Runs all dates
await agent.run_date_range(INIT_DATE, END_DATE)
```

**For API mode:**
```python
# Worker creates agent
agent = AgentClass(...)
await agent.initialize()

# Worker calls run_trading_session directly for each date
for date in date_range:
    await agent.run_trading_session(date)
```

**Action:** ✅ Worker will not use `run_date_range()` method. No changes needed to agent.

---

### 1.3 Summary: BaseAgent Changes

**Result:** **NO CODE CHANGES REQUIRED** to `base_agent.py`!

The existing architecture is already compatible with the API worker pattern:
- `run_trading_session()` is the perfect interface
- Runtime config is managed via environment variables
- Position tracking works as-is

**Only change needed:** Worker must call `agent.register_agent()` if position file doesn't exist (already handled by `get_trading_dates()` logic).

---

## Part 2: Docker Configuration

### 2.1 Current Docker Setup

**Existing files:**
- `Dockerfile` - Multi-stage build for batch mode
- `docker-compose.yml` - Service definition
- `docker-entrypoint.sh` - Launches data fetch + main.py

### 2.2 Modified Dockerfile

```dockerfile
# Existing stages remain the same...
FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt requirements-api.txt ./
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir -r requirements-api.txt

# Copy application code
COPY . /app

# Create data directories
RUN mkdir -p /app/data /app/configs

# Copy and set permissions for entrypoint
COPY docker-entrypoint-api.sh /app/
RUN chmod +x /app/docker-entrypoint-api.sh

# Expose API port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Run API service
CMD ["/app/docker-entrypoint-api.sh"]
```

### 2.3 New requirements-api.txt

```
fastapi==0.109.0
uvicorn[standard]==0.27.0
pydantic==2.5.3
pydantic-settings==2.1.0
python-multipart==0.0.6
```

### 2.4 New docker-entrypoint-api.sh

```bash
#!/bin/bash
set -e

echo "=================================="
echo "AI-Trader API Service Starting"
echo "=================================="

# Cleanup stale runtime configs from previous runs
echo "Cleaning up stale runtime configs..."
python3 -c "from api.runtime_manager import RuntimeConfigManager; RuntimeConfigManager().cleanup_all_runtime_configs()"

# Start MCP services in background
echo "Starting MCP services..."
cd /app/agent_tools
python3 start_mcp_services.py &
MCP_PID=$!

# Wait for MCP services to be ready
echo "Waiting for MCP services to initialize..."
sleep 10

# Verify MCP services are running
echo "Verifying MCP services..."
for port in ${MATH_HTTP_PORT:-8000} ${SEARCH_HTTP_PORT:-8001} ${TRADE_HTTP_PORT:-8002} ${GETPRICE_HTTP_PORT:-8003}; do
    if ! curl -f -s http://localhost:$port/health > /dev/null 2>&1; then
        echo "WARNING: MCP service on port $port not responding"
    else
        echo "✓ MCP service on port $port is healthy"
    fi
done

# Start API server
echo "Starting FastAPI server..."
cd /app

# Use environment variables for host and port
API_HOST=${API_HOST:-0.0.0.0}
API_PORT=${API_PORT:-8080}

echo "API will be available at http://${API_HOST}:${API_PORT}"
echo "=================================="

# Start uvicorn with single worker (for simplicity in MVP)
exec uvicorn api.main:app \
    --host ${API_HOST} \
    --port ${API_PORT} \
    --workers 1 \
    --log-level info

# Cleanup function (called on exit)
trap "echo 'Shutting down...'; kill $MCP_PID 2>/dev/null || true" EXIT SIGTERM SIGINT
```

### 2.5 Updated docker-compose.yml

```yaml
version: '3.8'

services:
  ai-trader:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: ai-trader-api
    ports:
      - "8080:8080"
    volumes:
      - ./data:/app/data
      - ./configs:/app/configs
      - ./logs:/app/logs
    env_file:
      - .env
    environment:
      - API_HOST=0.0.0.0
      - API_PORT=8080
      - RUNTIME_ENV_PATH=/app/data/runtime_env.json
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    restart: unless-stopped
    networks:
      - ai-trader-network

networks:
  ai-trader-network:
    driver: bridge
```

### 2.6 Environment Variables Reference

```bash
# .env file example for API mode

# OpenAI Configuration
OPENAI_API_BASE=https://api.openai.com/v1
OPENAI_API_KEY=sk-...

# API Keys
ALPHAADVANTAGE_API_KEY=your_alpha_vantage_key
JINA_API_KEY=your_jina_key

# MCP Service Ports
MATH_HTTP_PORT=8000
SEARCH_HTTP_PORT=8001
TRADE_HTTP_PORT=8002
GETPRICE_HTTP_PORT=8003

# API Configuration
API_HOST=0.0.0.0
API_PORT=8080

# Runtime Config
RUNTIME_ENV_PATH=/app/data/runtime_env.json

# Job Configuration
MAX_CONCURRENT_JOBS=1
```

### 2.7 Docker Commands Reference

```bash
# Build image
docker-compose build

# Start service
docker-compose up

# Start in background
docker-compose up -d

# View logs
docker-compose logs -f

# Check health
docker-compose ps

# Stop service
docker-compose down

# Restart service
docker-compose restart

# Execute command in running container
docker-compose exec ai-trader python3 -c "from api.job_manager import JobManager; jm = JobManager(); print(jm.get_current_job())"

# Access container shell
docker-compose exec ai-trader bash
```

---

## Part 3: Windmill Integration

### 3.1 Windmill Overview

Windmill (windmill.dev) is a workflow automation platform that can:
- Schedule cron jobs
- Execute TypeScript/Python scripts
- Store state between runs
- Build UI dashboards

**Integration approach:**
1. Windmill cron job triggers simulation daily
2. Windmill polls for job completion
3. Windmill retrieves results and stores in internal database
4. Windmill dashboard displays performance metrics

### 3.2 Flow 1: Daily Simulation Trigger

**File:** `windmill/trigger_simulation.ts`

```typescript
import { Resource } from "https://deno.land/x/windmill@v1.0.0/mod.ts";

export async function main(
  ai_trader_api: Resource<"ai_trader_api">
) {
  const apiUrl = ai_trader_api.base_url; // e.g., "http://ai-trader:8080"

  // Trigger simulation
  const response = await fetch(`${apiUrl}/simulate/trigger`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      config_path: "configs/default_config.json"
    }),
  });

  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`);
  }

  const data = await response.json();

  // Handle different response types
  if (data.status === "current") {
    console.log("Simulation already up-to-date");
    return {
      action: "skipped",
      message: data.message,
      last_date: data.last_simulation_date
    };
  }

  // Store job_id in Windmill state for poller to pick up
  await Deno.writeTextFile(
    `/tmp/current_job_id.txt`,
    data.job_id
  );

  console.log(`Simulation triggered: ${data.job_id}`);
  console.log(`Date range: ${data.date_range.join(", ")}`);
  console.log(`Models: ${data.models.join(", ")}`);

  return {
    action: "triggered",
    job_id: data.job_id,
    date_range: data.date_range,
    models: data.models,
    status: data.status
  };
}
```

**Windmill Resource Configuration:**
```json
{
  "resource_type": "ai_trader_api",
  "base_url": "http://ai-trader:8080"
}
```

**Schedule:** Every day at 6:00 AM

---

### 3.3 Flow 2: Job Status Poller

**File:** `windmill/poll_simulation_status.ts`

```typescript
import { Resource } from "https://deno.land/x/windmill@v1.0.0/mod.ts";

export async function main(
  ai_trader_api: Resource<"ai_trader_api">,
  job_id?: string
) {
  const apiUrl = ai_trader_api.base_url;

  // Get job_id from parameter or from current job file
  let jobId = job_id;
  if (!jobId) {
    try {
      jobId = await Deno.readTextFile("/tmp/current_job_id.txt");
    } catch {
      // No current job
      return {
        status: "no_job",
        message: "No active simulation job"
      };
    }
  }

  // Poll status
  const response = await fetch(`${apiUrl}/simulate/status/${jobId}`);

  if (!response.ok) {
    if (response.status === 404) {
      return {
        status: "not_found",
        message: "Job not found",
        job_id: jobId
      };
    }
    throw new Error(`API error: ${response.status}`);
  }

  const data = await response.json();

  console.log(`Job ${jobId}: ${data.status}`);
  console.log(`Progress: ${data.progress.completed}/${data.progress.total_model_days} model-days`);

  // If job is complete, retrieve results
  if (data.status === "completed" || data.status === "partial") {
    console.log("Job finished, retrieving results...");

    const results = [];
    for (const date of data.date_range) {
      const resultsResponse = await fetch(
        `${apiUrl}/results?date=${date}&detail=minimal`
      );

      if (resultsResponse.ok) {
        const dateResults = await resultsResponse.json();
        results.push(dateResults);
      }
    }

    // Clean up job_id file
    try {
      await Deno.remove("/tmp/current_job_id.txt");
    } catch {
      // Ignore
    }

    return {
      status: data.status,
      job_id: jobId,
      completed_at: data.completed_at,
      duration_seconds: data.total_duration_seconds,
      results: results
    };
  }

  // Job still running
  return {
    status: data.status,
    job_id: jobId,
    progress: data.progress,
    started_at: data.created_at
  };
}
```

**Schedule:** Every 5 minutes (will skip if no active job)

---

### 3.4 Flow 3: Results Retrieval and Storage

**File:** `windmill/store_simulation_results.py`

```python
import wmill
from datetime import datetime

def main(
    job_results: dict,
    database: str = "simulation_results"
):
    """
    Store simulation results in Windmill's internal database.

    Args:
        job_results: Output from poll_simulation_status flow
        database: Database name for storage
    """
    if job_results.get("status") not in ("completed", "partial"):
        return {"message": "Job not complete, skipping storage"}

    # Extract results
    job_id = job_results["job_id"]
    results = job_results.get("results", [])

    stored_count = 0

    for date_result in results:
        date = date_result["date"]

        for model_result in date_result["results"]:
            model = model_result["model"]
            positions = model_result["positions"]
            pnl = model_result["daily_pnl"]

            # Store in Windmill database
            record = {
                "job_id": job_id,
                "date": date,
                "model": model,
                "cash": positions.get("CASH", 0),
                "portfolio_value": pnl["portfolio_value"],
                "daily_profit": pnl["profit"],
                "daily_return_pct": pnl["return_pct"],
                "stored_at": datetime.utcnow().isoformat()
            }

            # Use Windmill's internal storage
            wmill.set_variable(
                path=f"{database}/{model}/{date}",
                value=record
            )

            stored_count += 1

    return {
        "stored_count": stored_count,
        "job_id": job_id,
        "message": f"Stored {stored_count} model-day results"
    }
```

---

### 3.5 Windmill Dashboard Example

**File:** `windmill/dashboard.json` (Windmill App Builder)

```json
{
  "grid": [
    {
      "type": "table",
      "id": "performance_table",
      "configuration": {
        "title": "Model Performance Summary",
        "data_source": {
          "type": "script",
          "path": "f/simulation_results/get_latest_performance"
        },
        "columns": [
          {"field": "model", "header": "Model"},
          {"field": "latest_date", "header": "Latest Date"},
          {"field": "portfolio_value", "header": "Portfolio Value"},
          {"field": "total_return_pct", "header": "Total Return %"},
          {"field": "daily_return_pct", "header": "Daily Return %"}
        ]
      }
    },
    {
      "type": "chart",
      "id": "portfolio_chart",
      "configuration": {
        "title": "Portfolio Value Over Time",
        "chart_type": "line",
        "data_source": {
          "type": "script",
          "path": "f/simulation_results/get_timeseries"
        },
        "x_axis": "date",
        "y_axis": "portfolio_value",
        "series": "model"
      }
    }
  ]
}
```

**Supporting Script:** `windmill/get_latest_performance.py`

```python
import wmill

def main(database: str = "simulation_results"):
    """Get latest performance for each model"""

    # Query Windmill variables
    all_vars = wmill.list_variables(path_prefix=f"{database}/")

    # Group by model
    models = {}
    for var in all_vars:
        parts = var["path"].split("/")
        if len(parts) >= 3:
            model = parts[1]
            date = parts[2]

            value = wmill.get_variable(var["path"])

            if model not in models:
                models[model] = []
            models[model].append(value)

    # Compute summary for each model
    summary = []
    for model, records in models.items():
        # Sort by date
        records.sort(key=lambda x: x["date"], reverse=True)
        latest = records[0]

        # Calculate total return
        initial_value = 10000  # Initial cash
        total_return_pct = ((latest["portfolio_value"] - initial_value) / initial_value) * 100

        summary.append({
            "model": model,
            "latest_date": latest["date"],
            "portfolio_value": latest["portfolio_value"],
            "total_return_pct": round(total_return_pct, 2),
            "daily_return_pct": latest["daily_return_pct"]
        })

    return summary
```

---

### 3.6 Windmill Workflow Orchestration

**Main Workflow:** `windmill/daily_simulation_workflow.yaml`

```yaml
name: Daily AI Trader Simulation
description: Trigger simulation, poll status, and store results

triggers:
  - type: cron
    schedule: "0 6 * * *"  # Every day at 6 AM

steps:
  - id: trigger
    name: Trigger Simulation
    script: f/ai_trader/trigger_simulation
    outputs:
      - job_id
      - action

  - id: wait
    name: Wait for Job Start
    type: sleep
    duration: 10s

  - id: poll_loop
    name: Poll Until Complete
    type: loop
    max_iterations: 60  # Poll for up to 5 hours (60 × 5min)
    interval: 5m
    script: f/ai_trader/poll_simulation_status
    inputs:
      job_id: ${{ steps.trigger.outputs.job_id }}
    break_condition: |
      ${{ steps.poll_loop.outputs.status in ['completed', 'partial', 'failed'] }}

  - id: store_results
    name: Store Results in Database
    script: f/ai_trader/store_simulation_results
    inputs:
      job_results: ${{ steps.poll_loop.outputs }}
    condition: |
      ${{ steps.poll_loop.outputs.status in ['completed', 'partial'] }}

  - id: notify
    name: Send Notification
    type: email
    to: admin@example.com
    subject: "AI Trader Simulation Complete"
    body: |
      Simulation completed for ${{ steps.poll_loop.outputs.job_id }}
      Status: ${{ steps.poll_loop.outputs.status }}
      Duration: ${{ steps.poll_loop.outputs.duration_seconds }}s
```

---

### 3.7 Testing Windmill Integration Locally

**1. Start AI-Trader API:**
```bash
docker-compose up -d
```

**2. Test trigger endpoint:**
```bash
curl -X POST http://localhost:8080/simulate/trigger \
  -H "Content-Type: application/json" \
  -d '{"config_path": "configs/default_config.json"}'
```

**3. Test status polling:**
```bash
JOB_ID="<job_id_from_step_2>"
curl http://localhost:8080/simulate/status/$JOB_ID
```

**4. Test results retrieval:**
```bash
curl "http://localhost:8080/results?date=2025-01-16&model=gpt-5&detail=minimal"
```

**5. Deploy to Windmill:**
```bash
# Install Windmill CLI
npm install -g windmill-cli

# Login to your Windmill instance
wmill login https://your-windmill-instance.com

# Deploy scripts
wmill script push windmill/trigger_simulation.ts
wmill script push windmill/poll_simulation_status.ts
wmill script push windmill/store_simulation_results.py

# Deploy workflow
wmill flow push windmill/daily_simulation_workflow.yaml
```

---

## Part 4: Complete File Structure

After implementation, the project structure will be:

```
AI-Trader/
├── api/
│   ├── __init__.py
│   ├── main.py                 # FastAPI application
│   ├── models.py               # Pydantic request/response models
│   ├── job_manager.py          # Job lifecycle management
│   ├── database.py             # SQLite utilities
│   ├── worker.py               # Background simulation worker
│   ├── executor.py             # Single model-day execution
│   └── runtime_manager.py      # Runtime config isolation
│
├── docs/
│   ├── api-specification.md
│   ├── job-manager-specification.md
│   ├── worker-specification.md
│   └── implementation-specifications.md
│
├── windmill/
│   ├── trigger_simulation.ts
│   ├── poll_simulation_status.ts
│   ├── store_simulation_results.py
│   ├── get_latest_performance.py
│   ├── daily_simulation_workflow.yaml
│   └── dashboard.json
│
├── agent/
│   └── base_agent/
│       └── base_agent.py       # NO CHANGES NEEDED
│
├── agent_tools/
│   └── ... (existing MCP tools)
│
├── data/
│   ├── jobs.db                 # SQLite database (created automatically)
│   ├── runtime_env*.json       # Runtime configs (temporary)
│   ├── agent_data/             # Existing position/log data
│   └── merged.jsonl            # Existing price data
│
├── Dockerfile                  # Updated for API mode
├── docker-compose.yml          # Updated service definition
├── docker-entrypoint-api.sh    # New API entrypoint
├── requirements-api.txt        # FastAPI dependencies
├── .env                        # Environment configuration
└── main.py                     # Existing (used by worker)
```

---

## Part 5: Implementation Checklist

### Phase 1: API Foundation (Days 1-2)
- [ ] Create `api/` directory structure
- [ ] Implement `api/models.py` with Pydantic models
- [ ] Implement `api/database.py` with SQLite utilities
- [ ] Implement `api/job_manager.py` with job CRUD operations
- [ ] Write unit tests for job_manager
- [ ] Test database operations manually

### Phase 2: Worker & Executor (Days 3-4)
- [ ] Implement `api/runtime_manager.py`
- [ ] Implement `api/executor.py` for single model-day execution
- [ ] Implement `api/worker.py` for job orchestration
- [ ] Test worker with mock agent
- [ ] Test runtime config isolation

### Phase 3: FastAPI Endpoints (Days 5-6)
- [ ] Implement `api/main.py` with all endpoints
- [ ] Implement `/simulate/trigger` with background tasks
- [ ] Implement `/simulate/status/{job_id}`
- [ ] Implement `/simulate/current`
- [ ] Implement `/results` with detail levels
- [ ] Implement `/health` with MCP checks
- [ ] Test all endpoints with Postman/curl

### Phase 4: Docker Integration (Day 7)
- [ ] Update `Dockerfile`
- [ ] Create `docker-entrypoint-api.sh`
- [ ] Create `requirements-api.txt`
- [ ] Update `docker-compose.yml`
- [ ] Test Docker build
- [ ] Test container startup and health checks
- [ ] Test end-to-end simulation via API in Docker

### Phase 5: Windmill Integration (Days 8-9)
- [ ] Create Windmill scripts (trigger, poll, store)
- [ ] Test scripts locally against Docker API
- [ ] Deploy scripts to Windmill instance
- [ ] Create Windmill workflow
- [ ] Test workflow end-to-end
- [ ] Create Windmill dashboard
- [ ] Document Windmill setup process

### Phase 6: Testing & Documentation (Day 10)
- [ ] Integration tests for complete workflow
- [ ] Load testing (multiple concurrent requests)
- [ ] Error scenario testing (MCP down, API timeout)
- [ ] Update README.md with API usage
- [ ] Create API documentation (Swagger/OpenAPI)
- [ ] Create deployment guide
- [ ] Create troubleshooting guide

---

## Summary

This comprehensive specification covers:

1. **BaseAgent Refactoring:** Minimal changes needed (existing code compatible)
2. **Docker Configuration:** API service mode with health checks and proper entrypoint
3. **Windmill Integration:** Complete workflow automation with TypeScript/Python scripts
4. **File Structure:** Clear organization of new API components
5. **Implementation Checklist:** Step-by-step plan for 10-day implementation

**Total estimated implementation time:** 10 working days for MVP

**Next Step:** Review all specifications (api-specification.md, job-manager-specification.md, worker-specification.md, and this document) and approve before beginning implementation.
