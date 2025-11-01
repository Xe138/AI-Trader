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

### v0.5.0 - Advanced Quantitative Modeling (Planned)

**Focus:** Enable AI agents to create, test, and deploy custom quantitative models

#### Model Development Framework
- **Quantitative Model Creation** - AI agents build custom trading models
  - New MCP tool: `tool_model_builder.py` for model development operations
  - Support for common model types:
    - Statistical arbitrage models (mean reversion, cointegration)
    - Machine learning models (regression, classification, ensemble)
    - Technical indicator combinations (momentum, volatility, trend)
    - Factor models (multi-factor risk models, alpha signals)
  - Model specification via structured prompts/JSON
  - Integration with pandas, numpy, scikit-learn, statsmodels
  - Time series cross-validation for backtesting
  - Model versioning and persistence per agent signature

#### Model Testing & Validation
- **Backtesting Engine** - Rigorous model validation before deployment
  - Walk-forward analysis with rolling windows
  - Out-of-sample performance metrics
  - Statistical significance testing (t-tests, Sharpe ratio confidence intervals)
  - Overfitting detection (train/test performance divergence)
  - Transaction cost simulation (slippage, commissions)
  - Risk metrics (VaR, CVaR, maximum drawdown)
  - Anti-look-ahead validation (strict temporal boundaries)

#### Model Deployment & Execution
- **Production Model Integration** - Deploy validated models into trading decisions
  - Model registry per agent (`agent_data/[signature]/models/`)
  - Real-time model inference during trading sessions
  - Feature computation from historical price data
  - Model ensemble capabilities (combine multiple models)
  - Confidence scoring for predictions
  - Model performance monitoring (track live vs. backtest accuracy)
  - Automatic model retraining triggers (performance degradation detection)

#### Data & Features
- **Feature Engineering Toolkit** - Rich data transformations for model inputs
  - Technical indicators library (RSI, MACD, Bollinger Bands, ATR, etc.)
  - Price transformations (returns, log returns, volatility)
  - Market regime detection (trending, ranging, high/low volatility)
  - Cross-sectional features (relative strength, sector momentum)
  - Alternative data integration hooks (sentiment, news signals)
  - Feature caching and incremental computation
  - Feature importance analysis

#### API Endpoints
- **Model Management API** - Control and monitor quantitative models
  - `POST /models/create` - Create new model specification
  - `POST /models/train` - Train model on historical data
  - `POST /models/backtest` - Run backtest with specific parameters
  - `GET /models/{model_id}` - Retrieve model metadata and performance
  - `GET /models/{model_id}/predictions` - Get historical predictions
  - `POST /models/{model_id}/deploy` - Deploy model to production
  - `DELETE /models/{model_id}` - Archive or delete model

#### Benefits
- **Enhanced Trading Strategies** - Move beyond simple heuristics to data-driven decisions
- **Reproducibility** - Systematic model development and validation process
- **Risk Management** - Quantify model uncertainty and risk exposure
- **Learning System** - Agents improve trading performance through model iteration
- **Research Platform** - Compare effectiveness of different quantitative approaches

#### Technical Considerations
- Anti-look-ahead enforcement in model training (only use data before training date)
- Computational resource limits per model (prevent excessive training time)
- Model explainability requirements (agents must justify model choices)
- Integration with existing MCP architecture (models as tools)
- Storage considerations for model artifacts and training data

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
- **v0.5.0** - Advanced quantitative modeling (planned)

---

Last updated: 2025-11-01
