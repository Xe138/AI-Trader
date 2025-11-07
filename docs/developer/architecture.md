# Architecture

System design and component overview.

---

## Component Diagram

See README.md for architecture diagram.

---

## Key Components

### FastAPI Server (`api/main.py`)
- REST API endpoints
- Request validation
- Response formatting

### Job Manager (`api/job_manager.py`)
- Job lifecycle management
- SQLite operations
- Concurrency control

### Simulation Worker (`api/simulation_worker.py`)
- Background job execution
- Date-sequential, model-parallel orchestration
- Error handling

### Model-Day Executor (`api/model_day_executor.py`)
- Single model-day execution
- Runtime config isolation
- Agent invocation

### Base Agent (`agent/base_agent/base_agent.py`)
- Trading session execution
- MCP tool integration
- Position management

### MCP Services (`agent_tools/`)
- Math, Search, Trade, Price tools
- Internal HTTP servers
- Localhost-only access

---

## Data Flow

1. API receives trigger request
2. Job Manager validates and creates job
3. Worker starts background execution
4. For each date (sequential):
   - For each model (parallel):
     - Executor creates isolated runtime config
     - Agent executes trading session
     - Results stored in database
5. Job status updated
6. Results available via API

---

## Anti-Look-Ahead Controls

- `TODAY_DATE` in runtime config limits data access
- Price queries filter by date
- Search results filtered by publication date

See [CLAUDE.md](../../CLAUDE.md) for implementation details.

---

## Position Tracking Across Jobs

**Design:** Portfolio state is tracked per-model across all jobs, not per-job.

**Query Logic:**
```python
# Get starting position for current trading day
SELECT id, ending_cash FROM trading_days
WHERE model = ? AND date < ?  # No job_id filter
ORDER BY date DESC
LIMIT 1
```

**Benefits:**
- Portfolio continuity when creating new jobs with overlapping dates
- Prevents accidental portfolio resets
- Enables flexible job scheduling (resume, rerun, backfill)

**Example:**
- Job 1: Runs 2025-10-13 to 2025-10-15 for model-a
- Job 2: Runs 2025-10-16 to 2025-10-20 for model-a
- Job 2 starts with Job 1's ending position from 2025-10-15
