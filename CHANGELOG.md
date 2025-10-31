# Changelog

All notable changes to the AI-Trader project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/Xe138/AI-Trader/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/Xe138/AI-Trader/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Xe138/AI-Trader/releases/tag/v0.1.0
