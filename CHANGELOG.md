# Changelog

All notable changes to the AI-Trader-Server project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Date Range Support in /results Endpoint** - Query multiple dates in single request with period performance metrics
  - `start_date` and `end_date` parameters replace deprecated `date` parameter
  - Returns lightweight format with daily portfolio values and period metrics for date ranges
  - Period metrics: period return %, annualized return %, calendar days, trading days
  - Default to last 30 days when no dates provided (configurable via `DEFAULT_RESULTS_LOOKBACK_DAYS`)
  - Automatic edge trimming when requested range exceeds available data
  - Per-model results grouping
- **Environment Variable:** `DEFAULT_RESULTS_LOOKBACK_DAYS` - Configure default lookback period (default: 30)

### Changed
- **BREAKING:** `/results` endpoint parameter `date` removed - use `start_date`/`end_date` instead
  - Single date: `?start_date=2025-01-16` or `?end_date=2025-01-16`
  - Date range: `?start_date=2025-01-16&end_date=2025-01-20`
  - Old `?date=2025-01-16` now returns 422 error with migration instructions

### Migration Guide

**Before:**
```bash
GET /results?date=2025-01-16&model=gpt-4
```

**After:**
```bash
# Option 1: Use start_date only
GET /results?start_date=2025-01-16&model=gpt-4

# Option 2: Use both (same result for single date)
GET /results?start_date=2025-01-16&end_date=2025-01-16&model=gpt-4

# New: Date range queries
GET /results?start_date=2025-01-16&end_date=2025-01-20&model=gpt-4
```

**Python Client:**
```python
# OLD (will break)
results = client.get_results(date="2025-01-16")

# NEW
results = client.get_results(start_date="2025-01-16")
results = client.get_results(start_date="2025-01-16", end_date="2025-01-20")
```

## [0.4.3] - 2025-11-07

### Fixed
- **Critical:** Fixed cross-job portfolio continuity bug where subsequent jobs reset to initial position
  - Root cause: Two database query functions (`get_previous_trading_day()` and `get_starting_holdings()`) filtered by `job_id`, preventing them from finding previous day's position when queried from a different job
  - Impact: New jobs on consecutive dates would start with $10,000 cash and empty holdings instead of continuing from previous job's ending position (e.g., Job 2 on 2025-10-08 started with $10,000 instead of $329.825 cash and lost all stock holdings from Job 1 on 2025-10-07)
  - Solution: Removed `job_id` filters from SQL queries to enable cross-job position lookups, matching the existing design in `get_current_position_from_db()` which already supported cross-job continuity
  - Fix ensures complete portfolio continuity (both cash and holdings) across jobs for the same model
  - Added comprehensive test coverage with `test_get_previous_trading_day_across_jobs` and `test_get_starting_holdings_across_jobs`
  - Locations: `api/database.py:622-630` (get_previous_trading_day), `api/database.py:674-681` (get_starting_holdings), `tests/unit/test_database_helpers.py:133-169,265-316`

## [0.4.2] - 2025-11-07

### Fixed
- **Critical:** Fixed negative cash position bug where trades calculated from initial capital instead of accumulating
  - Root cause: MCP tools return `CallToolResult` objects with position data in `structuredContent` field, but `ContextInjector` was checking `isinstance(result, dict)` which always failed
  - Impact: Each trade checked cash against initial $10,000 instead of cumulative position, allowing over-spending and resulting in negative cash balances (e.g., -$8,768.68 after 11 trades totaling $18,768.68)
  - Solution: Updated `ContextInjector` to extract position dict from `CallToolResult.structuredContent` before validation
  - Fix ensures proper intra-day position tracking with cumulative cash checks preventing over-trading
  - Updated unit tests to mock `CallToolResult` objects matching production MCP behavior
  - Locations: `agent/context_injector.py:95-109`, `tests/unit/test_context_injector.py:26-53`
- Enabled MCP service logging by redirecting stdout/stderr from `/dev/null` to main process for better debugging
  - Previously, all MCP tool debug output was silently discarded
  - Now visible in docker logs for diagnosing parameter injection and trade execution issues
  - Location: `agent_tools/start_mcp_services.py:81-88`

### Fixed
- **Critical:** Fixed stale jobs blocking new jobs after Docker container restart
  - Root cause: Jobs with status 'pending', 'downloading_data', or 'running' remained in database after container shutdown, preventing new job creation
  - Solution: Added `cleanup_stale_jobs()` method that runs on FastAPI startup to mark interrupted jobs as 'failed' or 'partial' based on completion percentage
  - Intelligent status determination: Uses existing progress tracking (completed/total model-days) to distinguish between failed (0% complete) and partial (>0% complete)
  - Detailed error messages include original status and completion counts (e.g., "Job interrupted by container restart (was running, 3/10 model-days completed)")
  - Incomplete job_details automatically marked as 'failed' with clear error messages
  - Deployment-aware: Skips cleanup in DEV mode when database is reset, always runs in PROD mode
  - Comprehensive test coverage: 6 new unit tests covering all cleanup scenarios
  - Locations: `api/job_manager.py:702-779`, `api/main.py:164-168`, `tests/unit/test_job_manager.py:451-609`
- Fixed Pydantic validation errors when using DeepSeek models via OpenRouter
  - Root cause: LangChain's `parse_tool_call()` has a bug where it sometimes returns `args` as JSON string instead of parsed dict object
  - Solution: Added `ToolCallArgsParsingWrapper` that:
    1. Patches `parse_tool_call()` to detect and fix string args by parsing them to dict
    2. Normalizes non-standard tool_call formats (e.g., `{name, args, id}` → `{function: {name, arguments}, id}`)
  - The wrapper is defensive and only acts when needed, ensuring compatibility with all AI providers
  - Fixes validation error: `tool_calls.0.args: Input should be a valid dictionary [type=dict_type, input_value='...', input_type=str]`

## [0.4.1] - 2025-11-06

### Fixed
- Fixed "No trading" message always displaying despite trading activity by initializing `IF_TRADE` to `True` (trades expected by default)
- Root cause: `IF_TRADE` was initialized to `False` in runtime config but never updated when trades executed

### Note
- ChatDeepSeek integration was reverted as it conflicts with OpenRouter unified gateway architecture
- System uses `OPENAI_API_BASE` (OpenRouter) with single `OPENAI_API_KEY` for all providers
- Sporadic DeepSeek validation errors appear to be transient and do not require code changes

## [0.4.0] - 2025-11-05

### BREAKING CHANGES

#### Schema Migration: Old Tables Removed

The following database tables have been **removed** and replaced with new schema:

**Removed Tables:**
- `trading_sessions` → Replaced by `trading_days`
- `positions` (old action-centric version) → Replaced by `trading_days` + `actions` + `holdings`
- `reasoning_logs` → Replaced by `trading_days.reasoning_full` (JSON column)

**Migration Required:**
- If you have existing data in old tables, export it before upgrading
- New installations automatically use new schema
- Old data cannot be automatically migrated (different data model)

**Database Path:**
- Production: `data/trading.db`
- Development: `data/trading_dev.db`

**To migrate existing production database:**
```bash
# Run migration script to drop old tables
PYTHONPATH=. python api/migrations/002_drop_old_schema.py
```

#### API Endpoint Removed: /reasoning

The `/reasoning` endpoint has been **removed** and replaced by `/results` with reasoning parameter.

**Migration Guide:**

| Old Endpoint | New Endpoint |
|--------------|--------------|
| `GET /reasoning?job_id=X` | `GET /results?job_id=X&reasoning=summary` |
| `GET /reasoning?job_id=X&include_full_conversation=true` | `GET /results?job_id=X&reasoning=full` |

**Benefits of New Endpoint:**
- Day-centric structure (easier to understand portfolio progression)
- Daily P&L metrics included
- AI-generated reasoning summaries (2-3 sentences)
- Unified data model

**Response Structure Changes:**

Old `/reasoning` returned:
```json
{
  "sessions": [
    {
      "session_id": 1,
      "positions": [{"action_id": 0, "cash_after": 10000, ...}],
      "conversation": [...]
    }
  ]
}
```

New `/results?reasoning=full` returns:
```json
{
  "results": [
    {
      "date": "2025-01-15",
      "starting_position": {"holdings": [], "cash": 10000},
      "daily_metrics": {"profit": 0.0, "return_pct": 0.0},
      "trades": [{"action_type": "buy", "symbol": "AAPL", ...}],
      "final_position": {"holdings": [...], "cash": 8500},
      "reasoning": [...]
    }
  ]
}
```

### Removed

- `/reasoning` endpoint (use `/results?reasoning=full` instead)
- Old database tables: `trading_sessions`, `positions`, `reasoning_logs`
- Pydantic models: `ReasoningMessage`, `PositionSummary`, `TradingSessionResponse`, `ReasoningResponse`
- Old-schema tests for deprecated tables

### Added
- **Daily P&L Calculation System** - Accurate profit/loss tracking with normalized database schema
  - New `trading_days` table for day-centric trading results with daily P&L metrics
  - `holdings` table for portfolio snapshots (ending positions only)
  - `actions` table for trade execution ledger
  - `DailyPnLCalculator` calculates P&L by valuing previous holdings at current prices
  - Weekend/holiday gap handling with `days_since_last_trading` tracking
  - First trading day properly handled with zero P&L
  - Auto-initialization of schema on database creation
- **AI Reasoning Summaries** - Automated trading decision documentation
  - `ReasoningSummarizer` generates 2-3 sentence AI-powered summaries of trading sessions
  - Fallback to statistical summary if AI generation fails
  - Summaries generated during simulation and stored in database
  - Full reasoning logs preserved for detailed analysis
- **Day-Centric Results API** - Unified endpoint for trading results
  - New `/results` endpoint with query parameters: `job_id`, `model`, `date`, `reasoning`
  - Three reasoning levels: `none` (default), `summary`, `full`
  - Response structure: `starting_position`, `daily_metrics`, `trades`, `final_position`, `metadata`
  - Holdings chain validation across trading days
  - Replaced old positions-based endpoint
- **BaseAgent P&L Integration** - Complete integration of P&L calculation into trading sessions
  - P&L calculated at start of each trading day after loading current prices
  - Trading day records created with comprehensive metrics
  - Holdings saved to database after each session
  - Reasoning summaries generated and stored automatically
  - Database helper methods for clean data access

### Changed
- Reduced Docker healthcheck frequency from 30s to 1h to minimize log noise while maintaining startup verification
- Database schema migrated from action-centric to day-centric model
- Results API now returns normalized day-centric data structure
- Trade tools (`buy()`, `sell()`) now write to `actions` table instead of old `positions` table
- `model_day_executor` simplified - removed duplicate writes to old schema tables
- `get_current_position_from_db()` queries new schema (trading_days + holdings) instead of positions table

### Improved
- Database helper methods with 7 new functions for `trading_days` schema operations
- Test coverage increased with 36+ new comprehensive tests
- Documentation updated with complete API reference and database schema details

### Fixed
- **Critical:** Intra-day position tracking for sell-then-buy trades (e20dce7)
  - Sell proceeds now immediately available for subsequent buy orders within same trading session
  - ContextInjector maintains in-memory position state during trading sessions
  - Position updates accumulate after each successful trade
  - Enables agents to rebalance portfolios (sell + buy) in single session
  - Added 13 comprehensive tests for position tracking
- **Critical:** Tool message extraction in conversation history (462de3a, abb9cd0)
  - Fixed bug where tool messages (buy/sell trades) were not captured when agent completed in single step
  - Tool extraction now happens BEFORE finish signal check
  - Reasoning summaries now accurately reflect actual trades executed
  - Resolves issue where summarizer saw 0 tools despite multiple trades
- Reasoning summary generation improvements (6d126db)
  - Summaries now explicitly mention specific trades executed (symbols, quantities, actions)
  - Added TRADES EXECUTED section highlighting tool calls
  - Example: 'sold 1 GOOGL and 1 AMZN to reduce exposure' instead of 'maintain core holdings'
- Final holdings calculation accuracy (a8d912b)
  - Final positions now calculated from actions instead of querying incomplete database records
  - Correctly handles first trading day with multiple trades
  - New `_calculate_final_position_from_actions()` method applies all trades to calculate final state
  - Holdings now persist correctly across all trading days
  - Added 3 comprehensive tests for final position calculation
- Holdings persistence between trading days (aa16480)
  - Query now retrieves previous day's ending position as current day's starting position
  - Changed query from `date <=` to `date <` to prevent returning incomplete current-day records
  - Fixes empty starting_position/final_position in API responses despite successful trades
  - Updated tests to verify correct previous-day retrieval
- Context injector trading_day_id synchronization (05620fa)
  - ContextInjector now updated with trading_day_id after record creation
  - Fixes "Trade failed: trading_day_id not found in runtime config" error
  - MCP tools now correctly receive trading_day_id via context injection
- Schema migration compatibility fixes (7c71a04)
  - Updated position queries to use new trading_days schema instead of obsolete positions table
  - Removed obsolete add_no_trade_record_to_db function calls
  - Fixes "no such table: positions" error
  - Simplified _handle_trading_result logic
- Database referential integrity (9da65c2)
  - Corrected Database default path from "data/trading.db" to "data/jobs.db"
  - Ensures all components use same database file
  - Fixes FOREIGN KEY constraint failures when creating trading_day records
- Debug logging cleanup (1e7bdb5)
  - Removed verbose debug logging from ContextInjector for cleaner output

## [0.3.1] - 2025-11-03

### Fixed
- **Critical:** Fixed position tracking bugs causing cash reset and positions lost over weekends
  - Removed redundant `ModelDayExecutor._write_results_to_db()` that created corrupt records with cash=0 and holdings=[]
  - Fixed profit calculation to compare against start-of-day portfolio value instead of previous day's final value
  - Positions now correctly carry over between trading days and across weekends
  - Profit/loss calculations now accurately reflect trading gains/losses without treating trades as losses

### Changed
- Position tracking now exclusively handled by trade tools (`buy()`, `sell()`) and `add_no_trade_record_to_db()`
- Daily profit calculation compares to start-of-day (action_id=0) portfolio value for accurate P&L tracking

### Added
- Standardized testing scripts for different workflows:
  - `scripts/test.sh` - Interactive menu for all testing operations
  - `scripts/quick_test.sh` - Fast unit test feedback (~10-30s)
  - `scripts/run_tests.sh` - Main test runner with full configuration options
  - `scripts/coverage_report.sh` - Coverage analysis with HTML/JSON/terminal reports
  - `scripts/ci_test.sh` - CI/CD optimized testing with JUnit/coverage XML output
- Comprehensive testing documentation in `docs/developer/testing.md`
- Test coverage requirement: 85% minimum (currently at 89.86%)

## [0.3.0] - 2025-11-03

### Added - Development & Testing Features
- **Development Mode** - Mock AI provider for cost-free testing
  - `DEPLOYMENT_MODE=DEV` enables mock AI responses with deterministic stock rotation
  - Isolated dev database (`trading_dev.db`) separate from production data
  - `PRESERVE_DEV_DATA=true` option to prevent dev database reset on startup
  - No AI API costs during development and testing
  - All API responses include `deployment_mode` field
  - Startup warning displayed when running in DEV mode
- **Config Override System** - Docker configuration merging
  - Place custom configs in `user-configs/` directory
  - Startup merges user config with default config
  - Comprehensive validation with clear error messages
  - Volume mount: `./user-configs:/app/user-configs`

### Added - Enhanced API Features
- **Async Price Download** - Non-blocking data preparation
  - `POST /simulate/trigger` no longer blocks on price downloads
  - New job status: `downloading_data` during data preparation
  - Warnings field in status response for download issues
  - Better user experience for large date ranges
- **Resume Mode** - Idempotent simulation execution
  - Jobs automatically skip already-completed model-days
  - Safe to re-run jobs without duplicating work
  - `status="skipped"` for already-completed executions
  - Error-free job completion when partial results exist
- **Reasoning Logs API** - Access AI decision-making history
  - `GET /reasoning` endpoint for querying reasoning logs
  - Filter by job_id, model_name, date, include_full_conversation
  - Includes conversation history and tool usage
  - Database-only storage (no JSONL files)
  - AI-powered summary generation for reasoning sessions
- **Job Skip Status** - Enhanced job status tracking
  - New status: `skipped` for already-completed model-days
  - Better differentiation between pending, running, and skipped
  - Accurate job completion detection

### Added - Price Data Management & On-Demand Downloads
- **SQLite Price Data Storage** - Replaced JSONL files with relational database
  - `price_data` table for OHLCV data (replaces merged.jsonl)
  - `price_data_coverage` table for tracking downloaded date ranges
  - `simulation_runs` table for soft-delete position tracking
  - Comprehensive indexes for query performance
- **On-Demand Price Data Downloads** - Automatic gap filling via Alpha Vantage
  - Priority-based download strategy (maximize date completion)
  - Graceful rate limit handling (no pre-configured limits needed)
  - Smart coverage gap detection
  - Configurable via `AUTO_DOWNLOAD_PRICE_DATA` (default: true)
- **Date Range API** - Simplified date specification
  - Single date: `{"start_date": "2025-01-20"}`
  - Date range: `{"start_date": "2025-01-20", "end_date": "2025-01-24"}`
  - Automatic validation (chronological order, max range, not future)
  - Configurable max days via `MAX_SIMULATION_DAYS` (default: 30)
- **Migration Tooling** - Script to import existing merged.jsonl data
  - `scripts/migrate_price_data.py` for one-time data migration
  - Automatic coverage tracking during migration

### Added - API Service Transformation
- **REST API Service** - Complete FastAPI implementation for external orchestration
  - `POST /simulate/trigger` - Trigger simulation jobs with config, date range, and models
  - `GET /simulate/status/{job_id}` - Query job progress and execution details
  - `GET /results` - Retrieve simulation results with filtering (job_id, date, model)
  - `GET /health` - Service health check with database connectivity verification
- **SQLite Database** - Complete persistence layer replacing JSONL files
  - Jobs table - Job metadata and lifecycle tracking
  - Job details table - Per model-day execution status
  - Positions table - Trading position records with P&L
  - Holdings table - Portfolio holdings breakdown
  - Reasoning logs table - AI decision reasoning history
  - Tool usage table - MCP tool usage statistics
- **Backend Components**
  - JobManager - Job lifecycle management with concurrent job prevention
  - RuntimeConfigManager - Isolated runtime configs for thread-safe execution
  - ModelDayExecutor - Single model-day execution engine
  - SimulationWorker - Job orchestration with date-sequential, model-parallel execution
- **Comprehensive Test Suite**
  - 175 unit and integration tests
  - 19 database tests (98% coverage)
  - 23 job manager tests (98% coverage)
  - 10 model executor tests (84% coverage)
  - 20 API endpoint tests (81% coverage)
  - 20 Pydantic model tests (100% coverage)
  - 10 runtime manager tests (89% coverage)
  - 22 date utilities tests (100% coverage)
  - 33 price data manager tests (85% coverage)
  - 10 on-demand download integration tests
  - 8 existing integration tests
- **Docker Deployment** - Persistent REST API service
  - API-only deployment (batch mode removed for simplicity)
  - Single docker-compose service (ai-trader-server)
  - Health check configuration (30s interval, 3 retries)
  - Volume persistence for SQLite database and logs
  - Configurable API_PORT for flexible deployment
  - System dependencies (curl, procps) for health checks and debugging
- **Validation & Testing Tools**
  - `scripts/validate_docker_build.sh` - Docker build and startup validation with port awareness
  - `scripts/test_api_endpoints.sh` - Complete API endpoint testing suite with port awareness
  - TESTING_GUIDE.md - Comprehensive testing procedures and troubleshooting (including port conflicts)
- **Documentation**
  - DOCKER_API.md - API deployment guide with examples
  - TESTING_GUIDE.md - Validation procedures and troubleshooting
  - API endpoint documentation with request/response examples
  - Windmill integration patterns and examples

### Changed
- **Project Rebrand** - AI-Trader renamed to AI-Trader-Server
  - Updated all documentation for new project name
  - Updated Docker images to ghcr.io/xe138/ai-trader-server
  - Updated GitHub Actions workflows
  - Updated README, CHANGELOG, and all user guides
- **Architecture** - Transformed from batch-only to API-first service with database persistence
- **Data Storage** - Migrated from JSONL files to SQLite relational database
  - Price data now stored in `price_data` table instead of `merged.jsonl`
  - Tools/price_tools.py updated to query database
  - Position data fully migrated to database-only storage (removed JSONL dependencies)
  - Trade tools now read/write from database tables with lazy context injection
- **Deployment** - Simplified to single API-only Docker service (REST API is new in v0.3.0)
- **Logging** - Removed duplicate MCP service log files for cleaner output
- **Configuration** - Simplified environment variable configuration
  - **Added:** `DEPLOYMENT_MODE` (PROD/DEV) for environment control
  - **Added:** `PRESERVE_DEV_DATA` (default: false) to keep dev data between runs
  - **Added:** `AUTO_DOWNLOAD_PRICE_DATA` (default: true) - Enable on-demand downloads
  - **Added:** `MAX_SIMULATION_DAYS` (default: 30) - Maximum date range size
  - **Added:** `API_PORT` for host port mapping (default: 8080, customizable for port conflicts)
  - **Removed:** `RUNTIME_ENV_PATH` (API dynamically manages runtime configs)
  - **Removed:** MCP service ports (MATH_HTTP_PORT, SEARCH_HTTP_PORT, TRADE_HTTP_PORT, GETPRICE_HTTP_PORT)
  - **Removed:** `WEB_HTTP_PORT` (web UI not implemented)
  - MCP services use fixed internal ports (8000-8003) and are no longer exposed to host
  - Container always uses port 8080 internally for API
  - Only API port (8080) is exposed to host
  - Reduces configuration complexity and attack surface
- **Requirements** - Added fastapi>=0.120.0, uvicorn[standard]>=0.27.0, pydantic>=2.0.0
- **Docker Compose** - Single service (ai-trader-server) instead of dual-mode
- **Dockerfile** - Added system dependencies (curl, procps) and port 8080 exposure
- **.env.example** - Simplified configuration with only essential variables
- **Entrypoint** - Unified entrypoint.sh with proper signal handling (exec uvicorn)

### Technical Implementation
- **Test-Driven Development** - All components written with tests first
- **Mock-based Testing** - Avoid heavy dependencies in unit tests
- **Pydantic V2** - Type-safe request/response validation
- **Foreign Key Constraints** - Database referential integrity with cascade deletes
- **Thread-safe Execution** - Isolated runtime configs per model-day
- **Background Job Execution** - ThreadPoolExecutor for parallel model execution
- **Automatic Status Transitions** - Job status updates based on model-day completion

### Performance & Quality
- **Test Suite** - 175 tests, all passing
  - Unit tests: 155 tests
  - Integration tests: 18 tests
  - API tests: 20+ tests
- **Code Coverage** - High coverage for new modules
  - Date utilities: 100%
  - Price data manager: 85%
  - Database layer: 98%
  - Job manager: 98%
  - Pydantic models: 100%
  - Runtime manager: 89%
  - Model executor: 84%
  - FastAPI app: 81%
- **Test Execution** - Fast test suite (~12 seconds for full suite)

### Integration Ready
- **Windmill.dev** - HTTP-based integration with polling support
- **External Orchestration** - RESTful API for workflow automation
- **Monitoring** - Health checks and status tracking
- **Persistence** - SQLite database survives container restarts

### Fixed
- **Context Injection** - Runtime parameters correctly injected into MCP tools
  - ContextInjector always overrides AI-provided parameters (defense-in-depth)
  - Hidden context parameters from AI tool schema to prevent hallucination
  - Resolved database locking issues with concurrent tool calls
  - Proper async handling of tool reloading after context injection
- **Simulation Re-runs** - Prevent duplicate execution of completed model-days
  - Fixed job hanging when re-running partially completed simulations
  - `_execute_date()` now skips already-completed model-days
  - Job completion status correctly reflects skipped items
- **Agent Initialization** - Correct parameter passing in API mode
  - Fixed BaseAgent initialization parameters in ModelDayExecutor
  - Resolved async execution and position storage issues
- **Database Reliability** - Various improvements for concurrent access
  - Fixed column existence checks before creating indexes
  - Proper database path resolution in dev mode (prevents recursive _dev suffix)
  - Module-level database initialization for uvicorn reliability
  - Fixed database locking during concurrent writes
  - Improved error handling in buy/sell functions
- **Configuration** - Improved config handling
  - Use enabled field from config to determine which models run
  - Use config models when empty models list provided
  - Correct handling of merged runtime configs in containers
  - Proper get_db_path() usage to pass base database path
- **Docker** - Various deployment improvements
  - Removed non-existent data scripts from Dockerfile
  - Proper respect for dev mode in entrypoint database initialization
  - Correct closure usage to capture db_path in lifespan context manager

### Breaking Changes
- **Batch Mode Removed** - All simulations now run through REST API
  - v0.2.0 used sequential batch execution via Docker entrypoint
  - v0.3.0 introduces REST API for external orchestration
  - Migration: Use `POST /simulate/trigger` endpoint instead of direct script execution
- **Data Storage Format Changed** - Price data moved from JSONL to SQLite
  - Run `python scripts/migrate_price_data.py` to migrate existing merged.jsonl data
  - `merged.jsonl` no longer used (replaced by `price_data` table)
  - Automatic on-demand downloads eliminate need for manual data fetching
- **Configuration Variables Changed**
  - Added: `DEPLOYMENT_MODE`, `PRESERVE_DEV_DATA`, `AUTO_DOWNLOAD_PRICE_DATA`, `MAX_SIMULATION_DAYS`, `API_PORT`
  - Removed: `RUNTIME_ENV_PATH`, MCP service ports, `WEB_HTTP_PORT`
  - MCP services now use fixed internal ports (not exposed to host)

## [0.2.0] - 2025-10-31

### Added
- Complete Docker deployment support with containerization
- Docker Compose orchestration for easy local deployment
- Multi-stage Dockerfile with Python 3.10-slim base image
- Automated CI/CD pipeline via GitHub Actions for release builds
- Automatic draft release creation with version tagging
- Docker images published to GitHub Container Registry (ghcr.io)
- Comprehensive Docker documentation (docs/DOCKER.md)
- Release process documentation (docs/RELEASING.md)
- Data cache reuse design documentation (docs/DESIGN_DATA_CACHE_REUSE.md)
- CLAUDE.md repository guidance for development
- Docker deployment section in main README
- Environment variable configuration via docker-compose
- Sequential startup script (entrypoint.sh) for data fetch, MCP services, and trading agent
- Volume mounts for data and logs persistence
- Pre-built image support from ghcr.io/xe138/ai-trader-server
- Configurable volume path for persistent data
- Configurable web interface host port
- Automated merged.jsonl creation during price fetching
- API key registration URLs in .env.example

### Changed
- Updated .env.example with Docker-specific configuration, API key URLs, and paths
- Updated .gitignore to exclude git worktrees directory
- Removed deprecated version tag from docker-compose.yml
- Updated repository URLs to Xe138/AI-Trader-Server fork
- Docker Compose now uses pre-built image by default
- Simplified Docker config file selection with convention over configuration
- Fixed internal ports with configurable host ports
- Separated data scripts from volume mount directory
- Reduced log flooding during data fetch
- OPENAI_API_BASE can now be left empty in configuration

### Fixed
- Docker Compose configuration now follows modern best practices (version-less)
- Prevent restart loop on missing API keys with proper validation
- Docker tag generation now converts repository owner to lowercase
- Validate GITHUB_REF is a tag in docker-release workflow
- Correct Dockerfile FROM AS casing
- Module import errors for MCP services resolved with PYTHONPATH
- Prevent price data overwrite on container restart
- Merge script now writes to current directory for volume compatibility

## [0.1.0] - Initial Release

### Added
- AI trading competition platform for NASDAQ 100 stocks
- Support for multiple AI models (GPT, Claude, Qwen, DeepSeek, Gemini)
- MCP (Model Context Protocol) toolchain integration
  - Mathematical calculation tools
  - Market intelligence search via Jina AI
  - Trading execution tools
  - Price query tools
- Historical replay architecture with anti-look-ahead controls
- Alpha Vantage API integration for price data
- Autonomous AI decision-making with zero human intervention
- Real-time performance analytics and leaderboard
- Position tracking and trading logs
- Web-based performance dashboard
- Complete NASDAQ 100 stock universe support
- Initial capital: $10,000 per AI model
- Configurable date range for backtesting
- Multi-model concurrent trading support
- Automatic data fetching and merging
- Comprehensive README with quick start guide

### Technical Details
- Python 3.10+ support
- LangChain framework integration
- FastMCP for MCP service implementation
- JSONL format for position and log storage
- Weekday-only trading simulation
- Configurable agent parameters (max_steps, max_retries, initial_cash)

---

## Release Notes Template

For future releases, use this template:

```markdown
## [X.Y.Z] - YYYY-MM-DD

### Added
- New features

### Changed
- Changes to existing functionality

### Deprecated
- Soon-to-be removed features

### Removed
- Removed features

### Fixed
- Bug fixes

### Security
- Security improvements
```

---

[Unreleased]: https://github.com/Xe138/AI-Trader-Server/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/Xe138/AI-Trader-Server/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/Xe138/AI-Trader-Server/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Xe138/AI-Trader-Server/releases/tag/v0.1.0
