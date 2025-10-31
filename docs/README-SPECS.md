# AI-Trader API Service - Technical Specifications Summary

## Overview

This directory contains comprehensive technical specifications for transforming the AI-Trader batch simulation system into an API service compatible with Windmill automation.

## Specification Documents

### 1. [API Specification](./api-specification.md)
**Purpose:** Defines all API endpoints, request/response formats, and data models

**Key Contents:**
- **5 REST Endpoints:**
  - `POST /simulate/trigger` - Queue catch-up simulation job
  - `GET /simulate/status/{job_id}` - Poll job progress
  - `GET /simulate/current` - Get latest job
  - `GET /results` - Retrieve simulation results (minimal/full detail)
  - `GET /health` - Service health check
- **Pydantic Models** for type-safe request/response handling
- **Error Handling** strategies and HTTP status codes
- **SQLite Schema** for jobs and job_details tables
- **Configuration Management** via environment variables

**Status Codes:** 200 OK, 202 Accepted, 400 Bad Request, 404 Not Found, 409 Conflict, 503 Service Unavailable

---

### 2. [Job Manager Specification](./job-manager-specification.md)
**Purpose:** Details the job tracking and database layer

**Key Contents:**
- **SQLite Database Schema:**
  - `jobs` table - High-level job metadata
  - `job_details` table - Per model-day execution tracking
- **JobManager Class Interface:**
  - `create_job()` - Create new simulation job
  - `get_job()` - Retrieve job by ID
  - `update_job_status()` - State transitions (pending → running → completed/partial/failed)
  - `get_job_progress()` - Detailed progress metrics
  - `can_start_new_job()` - Concurrency control
- **State Machine:** Job status transitions and business logic
- **Concurrency Control:** Single-job execution enforcement
- **Testing Strategy:** Unit tests with temporary databases

**Key Feature:** Independent model execution - one model's failure doesn't block others (results in "partial" status)

---

### 3. [Background Worker Specification](./worker-specification.md)
**Purpose:** Defines async job execution architecture

**Key Contents:**
- **Execution Pattern:** Date-sequential, Model-parallel
  - All models for Date 1 run in parallel
  - Date 2 starts only after all models finish Date 1
  - Ensures position.jsonl integrity (no concurrent writes)
- **SimulationWorker Class:**
  - Orchestrates job execution
  - Manages date sequencing
  - Handles job-level errors
- **ModelDayExecutor Class:**
  - Executes single model-day simulation
  - Updates job_detail status
  - Isolates runtime configuration
- **RuntimeConfigManager:**
  - Creates temporary runtime_env_{job_id}_{model}_{date}.json files
  - Prevents state collisions between concurrent models
  - Cleans up after execution
- **Error Handling:** Graceful failure (models continue despite peer failures)
- **Logging:** Structured JSON logging with job/model/date context

**Performance:** 3 models × 5 days = ~7-15 minutes (vs. ~22-45 minutes sequential)

---

### 4. [Implementation Specification](./implementation-specifications.md)
**Purpose:** Complete implementation guide covering Agent, Docker, and Windmill

**Key Contents:**

#### Part 1: BaseAgent Refactoring
- **Analysis:** Existing `run_trading_session()` already compatible with API mode
- **Required Changes:** ✅ NONE! Existing code works as-is
- **Worker Integration:** Calls `agent.run_trading_session(date)` directly

#### Part 2: Docker Configuration
- **Modified Dockerfile:** Adds FastAPI dependencies, new entrypoint
- **docker-entrypoint-api.sh:** Starts MCP services → launches uvicorn
- **Health Checks:** Verifies MCP services and database connectivity
- **Volume Mounts:** `./data`, `./configs` for persistence

#### Part 3: Windmill Integration
- **Flow 1: trigger_simulation.ts** - Daily cron triggers API
- **Flow 2: poll_simulation_status.ts** - Polls every 5 min until complete
- **Flow 3: store_simulation_results.py** - Stores results in Windmill DB
- **Dashboard:** Charts and tables showing portfolio performance
- **Workflow Orchestration:** Complete YAML workflow definition

#### Part 4: File Structure
- New `api/` directory with 7 modules
- New `windmill/` directory with scripts and dashboard
- New `docs/` directory (this folder)
- `data/jobs.db` for job tracking

#### Part 5: Implementation Checklist
10-day implementation plan broken into 6 phases

---

## Architecture Highlights

### Request Flow

```
1. Windmill → POST /simulate/trigger
2. API creates job in SQLite (status: pending)
3. API queues BackgroundTask
4. API returns 202 Accepted with job_id
   ↓
5. Worker starts (status: running)
6. For each date sequentially:
     For each model in parallel:
       - Create isolated runtime config
       - Execute agent.run_trading_session(date)
       - Update job_detail status
7. Worker finishes (status: completed/partial/failed)
   ↓
8. Windmill polls GET /simulate/status/{job_id}
9. When complete: Windmill calls GET /results?date=X
10. Windmill stores results in internal DB
11. Windmill dashboard displays performance
```

### Data Flow

```
Input: configs/default_config.json
       ↓
API: Calculates date_range (last position → today)
       ↓
Worker: Executes simulations
       ↓
Output: data/agent_data/{model}/position/position.jsonl
        data/agent_data/{model}/log/{date}/log.jsonl
        data/jobs.db (job tracking)
       ↓
API: Reads position.jsonl + calculates P&L
       ↓
Windmill: Stores in internal DB → Dashboard visualization
```

---

## Key Design Decisions

### 1. Pattern B: Lazy On-Demand Processing
- **Chosen:** Windmill controls simulation timing via API calls
- **Benefit:** Centralized scheduling in Windmill
- **Tradeoff:** First Windmill call of the day triggers long-running job

### 2. SQLite vs. PostgreSQL
- **Chosen:** SQLite for MVP
- **Rationale:** Low concurrency (1 job at a time), simple deployment
- **Future:** PostgreSQL for production with multiple concurrent jobs

### 3. Date-Sequential, Model-Parallel Execution
- **Chosen:** Dates run sequentially, models run in parallel per date
- **Rationale:** Prevents position.jsonl race conditions, faster than fully sequential
- **Performance:** ~50% faster than sequential (3 models in parallel)

### 4. Independent Model Failures
- **Chosen:** One model's failure doesn't block others
- **Benefit:** Partial results better than no results
- **Implementation:** Job status becomes "partial" if any model fails

### 5. Minimal BaseAgent Changes
- **Chosen:** No modifications to agent code
- **Rationale:** Existing `run_trading_session()` is perfect API interface
- **Benefit:** Maintains backward compatibility with batch mode

---

## Implementation Prerequisites

### Required Environment Variables
```bash
OPENAI_API_BASE=...
OPENAI_API_KEY=...
ALPHAADVANTAGE_API_KEY=...
JINA_API_KEY=...
RUNTIME_ENV_PATH=/app/data/runtime_env.json
MATH_HTTP_PORT=8000
SEARCH_HTTP_PORT=8001
TRADE_HTTP_PORT=8002
GETPRICE_HTTP_PORT=8003
API_HOST=0.0.0.0
API_PORT=8080
```

### Required Python Packages (new)
```
fastapi==0.109.0
uvicorn[standard]==0.27.0
pydantic==2.5.3
```

### Docker Requirements
- Docker Engine 20.10+
- Docker Compose 2.0+
- 2GB RAM minimum for container
- 10GB disk space for data

### Windmill Requirements
- Windmill instance (self-hosted or cloud)
- Network access from Windmill to AI-Trader API
- Windmill CLI for deployment (optional)

---

## Testing Strategy

### Unit Tests
- `tests/test_job_manager.py` - Database operations
- `tests/test_worker.py` - Job execution logic
- `tests/test_executor.py` - Model-day execution

### Integration Tests
- `tests/test_api_endpoints.py` - FastAPI endpoint behavior
- `tests/test_end_to_end.py` - Full workflow (trigger → execute → retrieve)

### Manual Testing
- Docker container startup
- Health check endpoint
- Windmill workflow execution
- Dashboard visualization

---

## Performance Expectations

### Single Model-Day Execution
- **Duration:** 30-60 seconds (varies by AI model latency)
- **Bottlenecks:** AI API calls, MCP tool latency

### Multi-Model Job
- **Example:** 3 models × 5 days = 15 model-days
- **Parallel Execution:** ~7-15 minutes
- **Sequential Execution:** ~22-45 minutes
- **Speedup:** ~3x (number of models)

### API Response Times
- `/simulate/trigger`: < 1 second (just queues job)
- `/simulate/status`: < 100ms (SQLite query)
- `/results?detail=minimal`: < 500ms (file read + JSON parsing)
- `/results?detail=full`: < 2 seconds (parse log files)

---

## Security Considerations

### MVP Security
- **Network Isolation:** Docker network (no public exposure)
- **No Authentication:** Assumes Windmill → API is trusted network

### Future Enhancements
- API key authentication (`X-API-Key` header)
- Rate limiting per client
- HTTPS/TLS encryption
- Input sanitization for path traversal prevention

---

## Deployment Steps

### 1. Build Docker Image
```bash
docker-compose build
```

### 2. Start API Service
```bash
docker-compose up -d
```

### 3. Verify Health
```bash
curl http://localhost:8080/health
```

### 4. Test Trigger
```bash
curl -X POST http://localhost:8080/simulate/trigger \
  -H "Content-Type: application/json" \
  -d '{"config_path": "configs/default_config.json"}'
```

### 5. Deploy Windmill Scripts
```bash
wmill script push windmill/trigger_simulation.ts
wmill script push windmill/poll_simulation_status.ts
wmill script push windmill/store_simulation_results.py
```

### 6. Create Windmill Workflow
- Import `windmill/daily_simulation_workflow.yaml`
- Configure resource `ai_trader_api` with API URL
- Set cron schedule (daily 6 AM)

### 7. Create Windmill Dashboard
- Import `windmill/dashboard.json`
- Verify data visualization

---

## Troubleshooting Guide

### Issue: Health check fails
**Symptoms:** `curl http://localhost:8080/health` returns 503

**Possible Causes:**
1. MCP services not running
2. Database file permission error
3. API server not started

**Solutions:**
```bash
# Check MCP services
docker-compose exec ai-trader curl http://localhost:8000/health

# Check API logs
docker-compose logs -f ai-trader

# Restart container
docker-compose restart
```

### Issue: Job stuck in "running" status
**Symptoms:** Job never completes, status remains "running"

**Possible Causes:**
1. Agent execution crashed
2. Model API timeout
3. Worker process died

**Solutions:**
```bash
# Check job details for error messages
curl http://localhost:8080/simulate/status/{job_id}

# Check container logs
docker-compose logs -f ai-trader

# If API restarted, stale jobs are marked as failed on startup
docker-compose restart
```

### Issue: Windmill can't reach API
**Symptoms:** Connection refused from Windmill scripts

**Solutions:**
- Verify Windmill and AI-Trader on same Docker network
- Check firewall rules
- Use container name (ai-trader) instead of localhost in Windmill resource
- Verify API_PORT environment variable

---

## Migration from Batch Mode

### For Users Currently Running Batch Mode

**Option 1: Dual Mode (Recommended)**
- Keep existing `main.py` for manual testing
- Add new API mode for production automation
- Use different config files for each mode

**Option 2: API-Only**
- Replace batch execution entirely
- All simulations via API calls
- More consistent with production workflow

### Migration Checklist
- [ ] Backup existing `data/` directory
- [ ] Update `.env` with API configuration
- [ ] Test API mode in separate environment first
- [ ] Gradually migrate Windmill workflows
- [ ] Monitor logs for errors
- [ ] Validate results match batch mode output

---

## Next Steps

1. **Review Specifications**
   - Read all 4 specification documents
   - Ask clarifying questions
   - Approve design before implementation

2. **Implementation Phase 1** (Days 1-2)
   - Set up `api/` directory structure
   - Implement database and job_manager
   - Write unit tests

3. **Implementation Phase 2** (Days 3-4)
   - Implement worker and executor
   - Test with mock agents

4. **Implementation Phase 3** (Days 5-6)
   - Implement FastAPI endpoints
   - Test with Postman/curl

5. **Implementation Phase 4** (Day 7)
   - Docker integration
   - End-to-end testing

6. **Implementation Phase 5** (Days 8-9)
   - Windmill integration
   - Dashboard creation

7. **Implementation Phase 6** (Day 10)
   - Final testing
   - Documentation

---

## Questions or Feedback?

Please review all specifications and provide feedback on:
1. API endpoint design
2. Database schema
3. Execution pattern (date-sequential, model-parallel)
4. Error handling approach
5. Windmill integration workflow
6. Any concerns or suggested improvements

**Ready to proceed with implementation?** Confirm approval of specifications to begin Phase 1.
