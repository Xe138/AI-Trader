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
