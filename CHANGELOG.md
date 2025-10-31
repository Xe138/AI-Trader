# Changelog

All notable changes to the AI-Trader project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0] - 2025-10-31

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
  - 102 unit and integration tests (85% coverage)
  - 19 database tests (98% coverage)
  - 23 job manager tests (98% coverage)
  - 10 model executor tests (84% coverage)
  - 20 API endpoint tests (81% coverage)
  - 20 Pydantic model tests (100% coverage)
  - 10 runtime manager tests (89% coverage)
- **Docker Deployment** - Persistent REST API service
  - API-only deployment (batch mode removed for simplicity)
  - Single docker-compose service (ai-trader)
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
- **Architecture** - Transformed from batch-only to API-first service with database persistence
- **Data Storage** - Migrated from JSONL files to SQLite relational database
  - Price data now stored in `price_data` table instead of `merged.jsonl`
  - Tools/price_tools.py updated to query database
  - Position data remains in database (already migrated in earlier versions)
- **Deployment** - Simplified to single API-only Docker service
- **API Request Format** - Date range specification changed
  - Old: `{"date_range": ["2025-01-20", "2025-01-21", ...]}`
  - New: `{"start_date": "2025-01-20", "end_date": "2025-01-24"}`
  - `end_date` is optional (defaults to `start_date` for single day simulation)
  - Server automatically expands range and validates trading days
- **Configuration** - Simplified environment variable configuration
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
- **Model Selection** - `enabled` field in config now controls which models run
  - API `models` parameter is now optional
  - If not provided, uses models where `enabled: true` in config
  - If provided, explicitly overrides config (for manual testing)
  - Prevents accidental execution of all models
- **API Interface** - Config path is now server-side detail
  - Removed `config_path` parameter from POST /simulate/trigger
  - Server uses internal default config (configs/default_config.json)
  - Simplifies API calls
- **Requirements** - Added fastapi>=0.120.0, uvicorn[standard]>=0.27.0, pydantic>=2.0.0
- **Docker Compose** - Single service (ai-trader) instead of dual-mode
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
- **Code Coverage** - 85% overall (84.63% measured)
  - Database layer: 98%
  - Job manager: 98%
  - Pydantic models: 100%
  - Runtime manager: 89%
  - Model executor: 84%
  - FastAPI app: 81%
- **Test Execution** - 102 tests in ~2.5 seconds
- **Zero Test Failures** - All tests passing (threading tests excluded)

### Integration Ready
- **Windmill.dev** - HTTP-based integration with polling support
- **External Orchestration** - RESTful API for workflow automation
- **Monitoring** - Health checks and status tracking
- **Persistence** - SQLite database survives container restarts

### Breaking Changes
- **Batch Mode Removed** - All simulations now run through REST API
  - Simplifies deployment and eliminates dual-mode complexity
  - Focus on API-first architecture for external orchestration
  - Migration: Use POST /simulate/trigger endpoint instead of batch execution
- **API Request Format Changed** - Date specification now uses start_date/end_date
  - Old format: `{"date_range": ["2025-01-20", "2025-01-21"], "models": [...]}`
  - New format: `{"start_date": "2025-01-20", "end_date": "2025-01-21"}`
  - Models parameter is optional (uses enabled models from config)
  - Config_path parameter removed (server-side detail)
- **Data Storage Format Changed** - Price data moved from JSONL to SQLite
  - Run `python scripts/migrate_price_data.py` to migrate existing data
  - `merged.jsonl` no longer used (replaced by `price_data` table)
  - Automatic on-demand downloads eliminate need for manual data fetching
- **Configuration Variables Changed**
  - Added: `AUTO_DOWNLOAD_PRICE_DATA`, `MAX_SIMULATION_DAYS`
  - Removed: `RUNTIME_ENV_PATH`, MCP port configs, `WEB_HTTP_PORT`

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
- Pre-built image support from ghcr.io/xe138/ai-trader
- Configurable volume path for persistent data
- Configurable web interface host port
- Automated merged.jsonl creation during price fetching
- API key registration URLs in .env.example

### Changed
- Updated .env.example with Docker-specific configuration, API key URLs, and paths
- Updated .gitignore to exclude git worktrees directory
- Removed deprecated version tag from docker-compose.yml
- Updated repository URLs to Xe138/AI-Trader fork
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

[Unreleased]: https://github.com/Xe138/AI-Trader/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/Xe138/AI-Trader/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/Xe138/AI-Trader/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Xe138/AI-Trader/releases/tag/v0.1.0
