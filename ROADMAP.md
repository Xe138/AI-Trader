# AI-Trader Roadmap

This document outlines planned features and improvements for the AI-Trader project.

## Release Planning

### v0.4.0 - Enhanced Simulation Management (Planned)

**Focus:** Improved simulation control, resume capabilities, and performance analysis

#### Simulation Resume & Continuation
- **Resume from Last Completed Date** - API to continue simulations without re-running completed dates
  - `POST /simulate/resume` - Resume last incomplete job or start from last completed date
  - `POST /simulate/continue` - Extend existing simulation with new date range
  - Query parameters to specify which model(s) to continue
  - Automatic detection of last completed date per model
  - Validation to prevent overlapping simulations
  - Support for extending date ranges forward in time
  - Use cases:
    - Daily simulation updates (add today's date to existing run)
    - Recovering from failed jobs (resume from interruption point)
    - Incremental backtesting (extend historical analysis)

#### Position History & Analysis
- **Position History Tracking** - Track position changes over time
  - Query endpoint: `GET /positions/history?model=<name>&start_date=<date>&end_date=<date>`
  - Timeline view of all trades and position changes
  - Calculate holding periods and turnover rates
  - Support for position snapshots at specific dates

#### Performance Metrics
- **Advanced Performance Analytics** - Calculate standard trading metrics
  - Sharpe ratio, Sortino ratio, maximum drawdown
  - Win rate, average win/loss, profit factor
  - Volatility and beta calculations
  - Risk-adjusted returns
  - Comparison across models

#### Data Management
- **Price Data Management API** - Endpoints for price data operations
  - `GET /data/coverage` - Check date ranges available per symbol
  - `POST /data/download` - Trigger manual price data downloads
  - `GET /data/status` - Check download progress and rate limits
  - `DELETE /data/range` - Remove price data for specific date ranges

#### Web UI
- **Dashboard Interface** - Web-based monitoring and control interface
  - Job management dashboard
    - View active, pending, and completed jobs
    - Start new simulations with form-based configuration
    - Monitor job progress in real-time
    - Cancel running jobs
  - Results visualization
    - Performance charts (P&L over time, cumulative returns)
    - Position history timeline
    - Model comparison views
    - Trade log explorer with filtering
  - Configuration management
    - Model configuration editor
    - Date range selection with calendar picker
    - Price data coverage visualization
  - Technical implementation
    - Modern frontend framework (React, Vue.js, or Svelte)
    - Real-time updates via WebSocket or SSE
    - Responsive design for mobile access
    - Chart library (Plotly.js, Chart.js, or Recharts)
    - Served alongside API (single container deployment)

#### Development Infrastructure
- **Migration to uv Package Manager** - Modern Python package management
  - Replace pip with uv for dependency management
  - Create pyproject.toml with project metadata and dependencies
  - Update Dockerfile to use uv for faster, more reliable builds
  - Update development documentation and workflows
  - Benefits:
    - 10-100x faster dependency resolution and installation
    - Better dependency locking and reproducibility
    - Unified tool for virtual environments and package management
    - Drop-in pip replacement with improved UX

## Contributing

We welcome contributions to any of these planned features! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

To propose a new feature:
1. Open an issue with the `feature-request` label
2. Describe the use case and expected behavior
3. Discuss implementation approach with maintainers
4. Submit a PR with tests and documentation

## Version History

- **v0.1.0** - Initial release with batch execution
- **v0.2.0** - Docker deployment support
- **v0.3.0** - REST API, on-demand downloads, database storage (current)
- **v0.4.0** - Enhanced simulation management (planned)

---

Last updated: 2025-10-31
