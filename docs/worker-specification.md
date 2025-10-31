# Background Worker Architecture Specification

## 1. Overview

The Background Worker executes simulation jobs asynchronously, allowing the API to return immediately (202 Accepted) while simulations run in the background.

**Key Responsibilities:**
1. Execute simulation jobs queued by `/simulate/trigger` endpoint
2. Manage per-model-day execution with status updates
3. Handle errors gracefully (model failures don't block other models)
4. Coordinate runtime configuration for concurrent model execution
5. Update job status in database throughout execution

---

## 2. Worker Architecture

### 2.1 Execution Model

**Pattern:** Date-sequential, Model-parallel execution

```
Job: Simulate 2025-01-16 to 2025-01-18 for models [gpt-5, claude-3.7-sonnet]

Execution flow:
┌─────────────────────────────────────────────────────────────┐
│ Date: 2025-01-16                                            │
│   ├─ gpt-5 (running)              ┐                         │
│   └─ claude-3.7-sonnet (running)  ┘ Parallel               │
└─────────────────────────────────────────────────────────────┘
                    │
                    ▼ (both complete)
┌─────────────────────────────────────────────────────────────┐
│ Date: 2025-01-17                                            │
│   ├─ gpt-5 (running)              ┐                         │
│   └─ claude-3.7-sonnet (running)  ┘ Parallel               │
└─────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────┐
│ Date: 2025-01-18                                            │
│   ├─ gpt-5 (running)              ┐                         │
│   └─ claude-3.7-sonnet (running)  ┘ Parallel               │
└─────────────────────────────────────────────────────────────┘
```

**Rationale:**
- **Models run in parallel** → Faster total execution (30-60s per model-day, 3 models = ~30-60s per date instead of ~90-180s)
- **Dates run sequentially** → Ensures position.jsonl integrity (no concurrent writes to same file)
- **Independent failure handling** → One model's failure doesn't block other models

---

### 2.2 File Structure

```
api/
├── worker.py           # SimulationWorker class
├── executor.py         # Single model-day execution logic
└── runtime_manager.py  # Runtime config isolation
```

---

## 3. Worker Implementation

### 3.1 SimulationWorker Class

```python
# api/worker.py

import asyncio
from typing import List, Dict
from datetime import datetime
import logging
from api.job_manager import JobManager
from api.executor import ModelDayExecutor
from main import load_config, get_agent_class

logger = logging.getLogger(__name__)

class SimulationWorker:
    """
    Executes simulation jobs in the background.

    Manages:
    - Date-sequential, model-parallel execution
    - Job status updates throughout execution
    - Error handling and recovery
    """

    def __init__(self, job_manager: JobManager):
        self.job_manager = job_manager
        self.executor = ModelDayExecutor(job_manager)

    async def run_job(self, job_id: str) -> None:
        """
        Execute a simulation job.

        Args:
            job_id: UUID of job to execute

        Flow:
            1. Load job from database
            2. Load configuration file
            3. Initialize agents for each model
            4. For each date sequentially:
                - Run all models in parallel
                - Update status after each model-day
            5. Mark job as completed/partial/failed
        """
        logger.info(f"Starting simulation job {job_id}")

        try:
            # 1. Load job metadata
            job = self.job_manager.get_job(job_id)
            if not job:
                logger.error(f"Job {job_id} not found")
                return

            # 2. Update job status to 'running'
            self.job_manager.update_job_status(job_id, "running")

            # 3. Load configuration
            config = load_config(job["config_path"])

            # 4. Get enabled models from config
            enabled_models = [
                m for m in config["models"]
                if m.get("signature") in job["models"] and m.get("enabled", True)
            ]

            if not enabled_models:
                raise ValueError("No enabled models found in configuration")

            # 5. Get agent class
            agent_type = config.get("agent_type", "BaseAgent")
            AgentClass = get_agent_class(agent_type)

            # 6. Execute each date sequentially
            for date in job["date_range"]:
                logger.info(f"[Job {job_id}] Processing date: {date}")

                # Run all models for this date in parallel
                tasks = []
                for model_config in enabled_models:
                    task = self.executor.run_model_day(
                        job_id=job_id,
                        date=date,
                        model_config=model_config,
                        agent_class=AgentClass,
                        config=config
                    )
                    tasks.append(task)

                # Wait for all models to complete this date
                results = await asyncio.gather(*tasks, return_exceptions=True)

                # Log any exceptions (already handled by executor, just for visibility)
                for i, result in enumerate(results):
                    if isinstance(result, Exception):
                        model_sig = enabled_models[i]["signature"]
                        logger.error(f"[Job {job_id}] Model {model_sig} failed on {date}: {result}")

                logger.info(f"[Job {job_id}] Date {date} completed")

            # 7. Job execution finished - final status will be set by job_manager
            # based on job_details statuses
            logger.info(f"[Job {job_id}] All dates processed")

        except Exception as e:
            logger.error(f"[Job {job_id}] Fatal error: {e}", exc_info=True)
            self.job_manager.update_job_status(job_id, "failed", error=str(e))
```

---

### 3.2 ModelDayExecutor

```python
# api/executor.py

import asyncio
import os
import logging
from typing import Dict, Any
from datetime import datetime
from pathlib import Path
from api.job_manager import JobManager
from api.runtime_manager import RuntimeConfigManager
from tools.general_tools import write_config_value

logger = logging.getLogger(__name__)

class ModelDayExecutor:
    """
    Executes a single model-day simulation.

    Responsibilities:
    - Initialize agent for specific model
    - Set up isolated runtime configuration
    - Execute trading session
    - Update job_detail status
    - Handle errors without blocking other models
    """

    def __init__(self, job_manager: JobManager):
        self.job_manager = job_manager
        self.runtime_manager = RuntimeConfigManager()

    async def run_model_day(
        self,
        job_id: str,
        date: str,
        model_config: Dict[str, Any],
        agent_class: type,
        config: Dict[str, Any]
    ) -> None:
        """
        Execute simulation for one model on one date.

        Args:
            job_id: Job UUID
            date: Trading date (YYYY-MM-DD)
            model_config: Model configuration dict from config file
            agent_class: Agent class (e.g., BaseAgent)
            config: Full configuration dict

        Updates:
            - job_details status: pending → running → completed/failed
            - Writes to position.jsonl and log.jsonl
        """
        model_sig = model_config["signature"]
        logger.info(f"[Job {job_id}] Starting {model_sig} on {date}")

        # Update status to 'running'
        self.job_manager.update_job_detail_status(
            job_id, date, model_sig, "running"
        )

        # Create isolated runtime config for this execution
        runtime_config_path = self.runtime_manager.create_runtime_config(
            job_id=job_id,
            model_sig=model_sig,
            date=date
        )

        try:
            # 1. Extract model parameters
            basemodel = model_config.get("basemodel")
            openai_base_url = model_config.get("openai_base_url")
            openai_api_key = model_config.get("openai_api_key")

            if not basemodel:
                raise ValueError(f"Model {model_sig} missing basemodel field")

            # 2. Get agent configuration
            agent_config = config.get("agent_config", {})
            log_config = config.get("log_config", {})

            max_steps = agent_config.get("max_steps", 10)
            max_retries = agent_config.get("max_retries", 3)
            base_delay = agent_config.get("base_delay", 0.5)
            initial_cash = agent_config.get("initial_cash", 10000.0)
            log_path = log_config.get("log_path", "./data/agent_data")

            # 3. Get stock symbols from prompts
            from prompts.agent_prompt import all_nasdaq_100_symbols

            # 4. Create agent instance
            agent = agent_class(
                signature=model_sig,
                basemodel=basemodel,
                stock_symbols=all_nasdaq_100_symbols,
                log_path=log_path,
                openai_base_url=openai_base_url,
                openai_api_key=openai_api_key,
                max_steps=max_steps,
                max_retries=max_retries,
                base_delay=base_delay,
                initial_cash=initial_cash,
                init_date=date  # Note: This is used for initial registration
            )

            # 5. Initialize MCP connection and AI model
            # (Only do this once per job, not per date - optimization for future)
            await agent.initialize()

            # 6. Set runtime configuration for this execution
            # Override RUNTIME_ENV_PATH to use isolated config
            original_runtime_path = os.environ.get("RUNTIME_ENV_PATH")
            os.environ["RUNTIME_ENV_PATH"] = runtime_config_path

            try:
                # Write runtime config values
                write_config_value("TODAY_DATE", date)
                write_config_value("SIGNATURE", model_sig)
                write_config_value("IF_TRADE", False)

                # 7. Execute trading session
                await agent.run_trading_session(date)

                # 8. Mark as completed
                self.job_manager.update_job_detail_status(
                    job_id, date, model_sig, "completed"
                )

                logger.info(f"[Job {job_id}] Completed {model_sig} on {date}")

            finally:
                # Restore original runtime path
                if original_runtime_path:
                    os.environ["RUNTIME_ENV_PATH"] = original_runtime_path
                else:
                    os.environ.pop("RUNTIME_ENV_PATH", None)

        except Exception as e:
            # Log error and update status to 'failed'
            error_msg = f"{type(e).__name__}: {str(e)}"
            logger.error(
                f"[Job {job_id}] Failed {model_sig} on {date}: {error_msg}",
                exc_info=True
            )

            self.job_manager.update_job_detail_status(
                job_id, date, model_sig, "failed", error=error_msg
            )

        finally:
            # Cleanup runtime config file
            self.runtime_manager.cleanup_runtime_config(runtime_config_path)
```

---

### 3.3 RuntimeConfigManager

```python
# api/runtime_manager.py

import os
import json
import tempfile
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class RuntimeConfigManager:
    """
    Manages isolated runtime configuration files for concurrent model execution.

    Problem:
        Multiple models running concurrently need separate runtime_env.json files
        to avoid race conditions on TODAY_DATE, SIGNATURE, IF_TRADE values.

    Solution:
        Create temporary runtime config file per model-day execution:
        - /app/data/runtime_env_{job_id}_{model}_{date}.json

    Lifecycle:
        1. create_runtime_config() → Creates temp file
        2. Executor sets RUNTIME_ENV_PATH env var
        3. Agent uses isolated config via get_config_value/write_config_value
        4. cleanup_runtime_config() → Deletes temp file
    """

    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def create_runtime_config(
        self,
        job_id: str,
        model_sig: str,
        date: str
    ) -> str:
        """
        Create isolated runtime config file for this execution.

        Args:
            job_id: Job UUID
            model_sig: Model signature
            date: Trading date

        Returns:
            Path to created runtime config file
        """
        # Generate unique filename
        filename = f"runtime_env_{job_id[:8]}_{model_sig}_{date}.json"
        config_path = self.data_dir / filename

        # Initialize with default values
        initial_config = {
            "TODAY_DATE": date,
            "SIGNATURE": model_sig,
            "IF_TRADE": False,
            "JOB_ID": job_id
        }

        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(initial_config, f, indent=4)

        logger.debug(f"Created runtime config: {config_path}")
        return str(config_path)

    def cleanup_runtime_config(self, config_path: str) -> None:
        """
        Delete runtime config file after execution.

        Args:
            config_path: Path to runtime config file
        """
        try:
            if os.path.exists(config_path):
                os.unlink(config_path)
                logger.debug(f"Cleaned up runtime config: {config_path}")
        except Exception as e:
            logger.warning(f"Failed to cleanup runtime config {config_path}: {e}")

    def cleanup_all_runtime_configs(self) -> int:
        """
        Cleanup all runtime config files (for maintenance/startup).

        Returns:
            Number of files deleted
        """
        count = 0
        for config_file in self.data_dir.glob("runtime_env_*.json"):
            try:
                config_file.unlink()
                count += 1
            except Exception as e:
                logger.warning(f"Failed to delete {config_file}: {e}")

        if count > 0:
            logger.info(f"Cleaned up {count} stale runtime config files")

        return count
```

---

## 4. Integration with FastAPI

### 4.1 Background Task Pattern

```python
# api/main.py

from fastapi import FastAPI, BackgroundTasks, HTTPException
from api.job_manager import JobManager
from api.worker import SimulationWorker
from api.models import TriggerSimulationRequest, TriggerSimulationResponse

app = FastAPI(title="AI-Trader API")

# Global instances
job_manager = JobManager()
worker = SimulationWorker(job_manager)

@app.post("/simulate/trigger", response_model=TriggerSimulationResponse)
async def trigger_simulation(
    request: TriggerSimulationRequest,
    background_tasks: BackgroundTasks
):
    """
    Trigger a catch-up simulation job.

    Returns:
        202 Accepted with job details if new job queued
        200 OK with existing job details if already running
    """
    # 1. Load configuration
    config = load_config(request.config_path)

    # 2. Determine date range (last position date → most recent trading day)
    date_range = calculate_date_range(config)

    if not date_range:
        return {
            "status": "current",
            "message": "Simulation already up-to-date",
            "last_simulation_date": get_last_simulation_date(config),
            "next_trading_day": get_next_trading_day()
        }

    # 3. Get enabled models
    models = [m["signature"] for m in config["models"] if m.get("enabled", True)]

    # 4. Check for existing job with same date range
    existing_job = job_manager.find_job_by_date_range(date_range)
    if existing_job:
        # Return existing job status
        progress = job_manager.get_job_progress(existing_job["job_id"])
        return {
            "job_id": existing_job["job_id"],
            "status": existing_job["status"],
            "date_range": date_range,
            "models": models,
            "created_at": existing_job["created_at"],
            "message": "Simulation already in progress",
            "progress": progress
        }

    # 5. Create new job
    try:
        job_id = job_manager.create_job(
            config_path=request.config_path,
            date_range=date_range,
            models=models
        )
    except ValueError as e:
        # Another job is running (different date range)
        raise HTTPException(status_code=409, detail=str(e))

    # 6. Queue background task
    background_tasks.add_task(worker.run_job, job_id)

    # 7. Return immediately with job details
    return {
        "job_id": job_id,
        "status": "accepted",
        "date_range": date_range,
        "models": models,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "message": "Simulation job queued successfully"
    }
```

---

## 5. Agent Initialization Optimization

### 5.1 Current Issue

**Problem:** Each model-day calls `agent.initialize()`, which:
1. Creates new MCP client connections
2. Creates new AI model instance

For a 5-day simulation with 3 models = 15 `initialize()` calls → Slow

### 5.2 Optimization Strategy (Future Enhancement)

**Option A: Persistent Agent Instances**

Create agent once per model, reuse for all dates:

```python
class SimulationWorker:
    async def run_job(self, job_id: str) -> None:
        # ... load config ...

        # Initialize all agents once
        agents = {}
        for model_config in enabled_models:
            agent = await self._create_and_initialize_agent(
                model_config, AgentClass, config
            )
            agents[model_config["signature"]] = agent

        # Execute dates
        for date in job["date_range"]:
            tasks = []
            for model_sig, agent in agents.items():
                task = self.executor.run_model_day_with_agent(
                    job_id, date, agent
                )
                tasks.append(task)

            await asyncio.gather(*tasks, return_exceptions=True)
```

**Benefit:** ~10-15s saved per job (avoid repeated MCP handshakes)

**Tradeoff:** More memory usage (agents kept in memory), more complex error handling

**Recommendation:** Implement in v2 after MVP validation

---

## 6. Error Handling & Recovery

### 6.1 Model-Day Failure Scenarios

**Scenario 1: AI Model API Timeout**

```python
# In executor.run_model_day()
try:
    await agent.run_trading_session(date)
except asyncio.TimeoutError:
    error_msg = "AI model API timeout after 30s"
    self.job_manager.update_job_detail_status(
        job_id, date, model_sig, "failed", error=error_msg
    )
    # Do NOT raise - let other models continue
```

**Scenario 2: MCP Service Down**

```python
# In agent.initialize()
except RuntimeError as e:
    if "Failed to initialize MCP client" in str(e):
        error_msg = "MCP services unavailable - check agent_tools/start_mcp_services.py"
        self.job_manager.update_job_detail_status(
            job_id, date, model_sig, "failed", error=error_msg
        )
        # This likely affects all models - but still don't raise, let job_manager determine final status
```

**Scenario 3: Out of Cash**

```python
# In trade tool
if position["CASH"] < total_cost:
    # Trade tool returns error message
    # Agent receives error, continues reasoning (might sell other stocks)
    # Not a fatal error - trading session completes normally
```

### 6.2 Job-Level Failure

**When does entire job fail?**

Only if:
1. Configuration file is invalid/missing
2. Agent class import fails
3. Database errors during status updates

In these cases, `worker.run_job()` catches exception and marks job as `failed`.

All other errors (model-day failures) result in `partial` status.

---

## 7. Logging Strategy

### 7.1 Log Levels by Component

**Worker (api/worker.py):**
- `INFO`: Job start/end, date transitions
- `ERROR`: Fatal job errors

**Executor (api/executor.py):**
- `INFO`: Model-day start/completion
- `ERROR`: Model-day failures (with exc_info=True)

**Agent (base_agent.py):**
- Existing logging (step-by-step execution)

### 7.2 Structured Logging Format

```python
import logging
import json

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add extra fields if present
        if hasattr(record, "job_id"):
            log_record["job_id"] = record.job_id
        if hasattr(record, "model"):
            log_record["model"] = record.model
        if hasattr(record, "date"):
            log_record["date"] = record.date

        return json.dumps(log_record)

# Configure logger
handler = logging.StreamHandler()
handler.setFormatter(JSONFormatter())
logger = logging.getLogger("api")
logger.addHandler(handler)
logger.setLevel(logging.INFO)
```

### 7.3 Log Output Example

```json
{"timestamp": "2025-01-20T14:30:00Z", "level": "INFO", "logger": "api.worker", "message": "Starting simulation job 550e8400-...", "job_id": "550e8400-..."}
{"timestamp": "2025-01-20T14:30:01Z", "level": "INFO", "logger": "api.executor", "message": "Starting gpt-5 on 2025-01-16", "job_id": "550e8400-...", "model": "gpt-5", "date": "2025-01-16"}
{"timestamp": "2025-01-20T14:30:45Z", "level": "INFO", "logger": "api.executor", "message": "Completed gpt-5 on 2025-01-16", "job_id": "550e8400-...", "model": "gpt-5", "date": "2025-01-16"}
```

---

## 8. Testing Strategy

### 8.1 Unit Tests

```python
# tests/test_worker.py

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from api.worker import SimulationWorker
from api.job_manager import JobManager

@pytest.fixture
def mock_job_manager():
    jm = MagicMock(spec=JobManager)
    jm.get_job.return_value = {
        "job_id": "test-job-123",
        "config_path": "configs/test.json",
        "date_range": ["2025-01-16", "2025-01-17"],
        "models": ["gpt-5"]
    }
    return jm

@pytest.fixture
def worker(mock_job_manager):
    return SimulationWorker(mock_job_manager)

@pytest.mark.asyncio
async def test_run_job_success(worker, mock_job_manager):
    # Mock executor
    worker.executor.run_model_day = AsyncMock(return_value=None)

    await worker.run_job("test-job-123")

    # Verify job status updated to running
    mock_job_manager.update_job_status.assert_any_call("test-job-123", "running")

    # Verify executor called for each model-day
    assert worker.executor.run_model_day.call_count == 2  # 2 dates × 1 model

@pytest.mark.asyncio
async def test_run_job_partial_failure(worker, mock_job_manager):
    # Mock executor - first call succeeds, second fails
    worker.executor.run_model_day = AsyncMock(
        side_effect=[None, Exception("API timeout")]
    )

    await worker.run_job("test-job-123")

    # Job should continue despite one failure
    assert worker.executor.run_model_day.call_count == 2

    # Job status determined by job_manager based on job_details
    # (tested in test_job_manager.py)
```

### 8.2 Integration Tests

```python
# tests/test_integration.py

import pytest
from api.main import app
from fastapi.testclient import TestClient

client = TestClient(app)

def test_trigger_and_poll_simulation():
    # 1. Trigger simulation
    response = client.post("/simulate/trigger", json={
        "config_path": "configs/test.json"
    })
    assert response.status_code == 202
    job_id = response.json()["job_id"]

    # 2. Poll status (may need to wait for background task)
    import time
    time.sleep(2)  # Wait for execution to start

    response = client.get(f"/simulate/status/{job_id}")
    assert response.status_code == 200
    assert response.json()["status"] in ("running", "completed")

    # 3. Wait for completion (with timeout)
    max_wait = 60  # seconds
    start_time = time.time()
    while time.time() - start_time < max_wait:
        response = client.get(f"/simulate/status/{job_id}")
        status = response.json()["status"]
        if status in ("completed", "partial", "failed"):
            break
        time.sleep(5)

    assert status in ("completed", "partial")
```

---

## 9. Performance Monitoring

### 9.1 Metrics to Track

**Job-level metrics:**
- Total duration (from trigger to completion)
- Model-day failure rate
- Average model-day duration

**System-level metrics:**
- Concurrent job count (should be ≤ 1)
- Database query latency
- MCP service response times

### 9.2 Instrumentation (Future)

```python
# api/metrics.py

from prometheus_client import Counter, Histogram, Gauge

# Job metrics
job_counter = Counter('simulation_jobs_total', 'Total simulation jobs', ['status'])
job_duration = Histogram('simulation_job_duration_seconds', 'Job execution time')

# Model-day metrics
model_day_counter = Counter('model_days_total', 'Total model-days', ['model', 'status'])
model_day_duration = Histogram('model_day_duration_seconds', 'Model-day execution time', ['model'])

# System metrics
concurrent_jobs = Gauge('concurrent_jobs', 'Number of running jobs')
```

**Usage:**
```python
# In worker.run_job()
with job_duration.time():
    await self._execute_job_logic(job_id)
job_counter.labels(status=final_status).inc()
```

---

## 10. Concurrency Safety

### 10.1 Thread Safety

**FastAPI Background Tasks:**
- Run in threadpool (default) or asyncio tasks
- For MVP, using asyncio tasks (async functions)

**SQLite Thread Safety:**
- `check_same_thread=False` allows multi-thread access
- Each operation opens new connection → Safe for low concurrency

**File I/O:**
- `position.jsonl` writes are sequential per model → Safe
- Different models write to different files → Safe

### 10.2 Race Condition Scenarios

**Scenario: Two trigger requests at exact same time**

```
Thread A: Check can_start_new_job() → True
Thread B: Check can_start_new_job() → True
Thread A: Create job → Success
Thread B: Create job → Success (PROBLEM: 2 jobs running)
```

**Mitigation: Database-level locking**

```python
def can_start_new_job(self) -> bool:
    conn = get_db_connection(self.db_path)
    cursor = conn.cursor()

    # Use SELECT ... FOR UPDATE to lock rows (not supported in SQLite)
    # Instead, use UNIQUE constraint on (status, created_at) for pending/running jobs

    cursor.execute("""
        SELECT COUNT(*) FROM jobs
        WHERE status IN ('pending', 'running')
    """)

    count = cursor.fetchone()[0]
    conn.close()

    return count == 0
```

**For MVP:** Accept risk of rare double-job scenario (extremely unlikely with Windmill polling)

**For Production:** Use PostgreSQL with row-level locking or distributed lock (Redis)

---

## Summary

The Background Worker provides:
1. **Async job execution** with FastAPI BackgroundTasks
2. **Parallel model execution** for faster completion
3. **Isolated runtime configs** to prevent state collisions
4. **Graceful error handling** where model failures don't block others
5. **Comprehensive logging** for debugging and monitoring

**Next specification:** BaseAgent Refactoring for Single-Day Execution
