# Changelog

All notable changes to the AI-Trader project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- **Simplified Deployment** - Removed batch mode, now API-only
  - Single docker-compose service (ai-trader) instead of dual mode
  - Removed scripts/test_batch_mode.sh
  - Streamlined entrypoint (entrypoint.sh now runs API server)
  - Simplified docker-compose.yml configuration

### Removed
- **Batch Mode** - Eliminated one-time batch simulation mode
  - All simulations now run through REST API
  - Removes complexity of dual-mode deployment
  - Focus on API-first architecture for Windmill integration

## [0.3.0] - 2025-10-31

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
- **Docker Dual-Mode Deployment**
  - API server mode - Persistent REST API service with health checks
  - Batch mode - One-time simulation execution (backwards compatible)
  - Separate entrypoints for each mode
  - Health check configuration (30s interval, 3 retries)
  - Volume persistence for SQLite database and logs
- **Validation & Testing Tools**
  - `scripts/validate_docker_build.sh` - Docker build and startup validation
  - `scripts/test_api_endpoints.sh` - Complete API endpoint testing suite
  - `scripts/test_batch_mode.sh` - Batch mode execution validation
  - TESTING_GUIDE.md - Comprehensive testing procedures and troubleshooting
- **Documentation**
  - DOCKER_API.md - API deployment guide with examples
  - TESTING_GUIDE.md - Validation procedures and troubleshooting
  - API endpoint documentation with request/response examples
  - Windmill integration patterns and examples

### Changed
- **Architecture** - Transformed from batch-only to API service with database persistence
- **Data Storage** - Migrated from JSONL files to SQLite relational database
- **Deployment** - Added dual-mode Docker deployment (API server + batch)
- **Configuration** - Added API_PORT environment variable (default: 8080)
- **Requirements** - Added fastapi>=0.120.0, uvicorn[standard]>=0.27.0, pydantic>=2.0.0
- **Docker Compose** - Split into two services (ai-trader-api and ai-trader-batch)
- **Dockerfile** - Added port 8080 exposure for API server
- **.env.example** - Added API server configuration

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

### Backwards Compatibility
- **Batch Mode** - Original batch functionality preserved via Docker profile
- **Configuration** - Existing config files still work
- **Data Migration** - No automatic migration (fresh start recommended)

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
