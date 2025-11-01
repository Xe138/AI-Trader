# AI-Trader Roadmap

This document outlines planned features and improvements for the AI-Trader project.

## Release Planning

### v0.4.0 - Simplified Simulation Control (Planned)

**Focus:** Streamlined date-based simulation API with automatic resume from last completed date

#### Core Simulation API
- **Smart Date-Based Simulation** - Simple API for running simulations to a target date
  - `POST /simulate/to-date` - Run simulation up to specified date
    - Request: `{"target_date": "2025-01-31", "models": ["model1", "model2"]}`
    - Automatically starts from last completed date in position.jsonl
    - Skips already-simulated dates by default (idempotent)
    - Optional `force_resimulate: true` flag to re-run completed dates
    - Returns: job_id, date range to be simulated, models included
  - `GET /simulate/status/{model_name}` - Get last completed date and available date ranges
    - Returns: last_simulated_date, next_available_date, data_coverage
  - Behavior:
    - If no position.jsonl exists: starts from initial_date in config or first available data
    - If position.jsonl exists: continues from last completed date + 1 day
    - Validates target_date has available price data
    - Skips weekends automatically
    - Prevents accidental re-simulation without explicit flag

#### Benefits
- **Simplicity** - Single endpoint for "simulate to this date"
- **Idempotent** - Safe to call repeatedly, won't duplicate work
- **Incremental Updates** - Easy daily simulation updates: `POST /simulate/to-date {"target_date": "today"}`
- **Explicit Re-simulation** - Require `force_resimulate` flag to prevent accidental data overwrites
- **Automatic Resume** - Handles crash recovery transparently

#### Example Usage
```bash
# Initial backtest (Jan 1 - Jan 31)
curl -X POST http://localhost:5000/simulate/to-date \
  -d '{"target_date": "2025-01-31", "models": ["gpt-4"]}'

# Daily update (simulate new trading day)
curl -X POST http://localhost:5000/simulate/to-date \
  -d '{"target_date": "2025-02-01", "models": ["gpt-4"]}'

# Check status
curl http://localhost:5000/simulate/status/gpt-4

# Force re-simulation (e.g., after config change)
curl -X POST http://localhost:5000/simulate/to-date \
  -d '{"target_date": "2025-01-31", "models": ["gpt-4"], "force_resimulate": true}'
```

#### Technical Implementation
- Modify `main.py` and `api/app.py` to support target date parameter
- Update `BaseAgent.get_trading_dates()` to detect last completed date from position.jsonl
- Add validation: target_date must have price data available
- Add `force_resimulate` flag handling: clear position.jsonl range if enabled
- Preserve existing `/simulate` endpoint for backward compatibility

### v1.0.0 - Production Stability & Validation (Planned)

**Focus:** Comprehensive testing, documentation, and production readiness

#### Testing & Validation
- **Comprehensive Test Suite** - Full coverage of core functionality
  - Unit tests for all agent components
    - BaseAgent methods (initialize, run_trading_session, get_trading_dates)
    - Position management and tracking
    - Date range handling and validation
    - MCP tool integration
  - Integration tests for API endpoints
    - All /simulate endpoints with various configurations
    - /jobs endpoints (status, cancel, results)
    - /models endpoint for listing available models
    - Error handling and validation
  - End-to-end simulation tests
    - Multi-day trading simulations with mock data
    - Multiple concurrent model execution
    - Resume functionality after interruption
    - Force re-simulation scenarios
  - Anti-look-ahead validation tests
    - Verify price data temporal boundaries
    - Verify search results date filtering
    - Confirm no future data leakage in system prompts
  - Test coverage target: >80% code coverage
  - Continuous Integration: GitHub Actions workflow for automated testing

#### Stability & Error Handling
- **Robust Error Recovery** - Handle failures gracefully
  - Retry logic for transient API failures (already implemented, validate)
  - Graceful degradation when MCP services are unavailable
  - Database connection pooling and error handling
  - File system error handling (disk full, permission errors)
  - Comprehensive error messages with troubleshooting guidance
  - Logging improvements:
    - Structured logging with consistent format
    - Log rotation and size management
    - Error classification (user error vs. system error)
    - Debug mode for detailed diagnostics

#### Performance & Scalability
- **Performance Optimization** - Ensure efficient resource usage
  - Database query optimization and indexing
  - Price data caching and efficient lookups
  - Concurrent simulation handling validation
  - Memory usage profiling and optimization
  - Long-running simulation stability testing (30+ day ranges)
  - Load testing: multiple concurrent API requests
  - Resource limits and rate limiting considerations

#### Documentation & Examples
- **Production-Ready Documentation** - Complete user and developer guides
  - API documentation improvements:
    - OpenAPI/Swagger specification
    - Interactive API documentation (Swagger UI)
    - Example requests/responses for all endpoints
    - Error response documentation
  - User guides:
    - Quickstart guide refinement
    - Common workflows and recipes
    - Troubleshooting guide expansion
    - Best practices for model configuration
  - Developer documentation:
    - Architecture deep-dive
    - Contributing guidelines
    - Custom agent development guide
    - MCP tool development guide
  - Example configurations:
    - Various model providers (OpenAI, Anthropic, local models)
    - Different trading strategies
    - Development vs. production setups

#### Security & Best Practices
- **Security Hardening** - Production security review
  - **⚠️ SECURITY WARNING:** v1.0.0 does not include API authentication. The server should only be deployed in trusted environments (local development, private networks). Documentation must clearly warn users that the API is insecure and accessible to anyone with network access. API authentication is planned for v1.1.0.
  - API key management best practices documentation
  - Input validation and sanitization review
  - SQL injection prevention validation
  - Rate limiting for public deployments
  - Security considerations documentation
  - Dependency vulnerability scanning
  - Docker image security scanning

#### Release Readiness
- **Production Deployment Support** - Everything needed for production use
  - Production deployment checklist
  - Health check endpoints improvements
  - Monitoring and observability guidance
    - Key metrics to track (job success rate, execution time, error rates)
    - Integration with monitoring systems (Prometheus, Grafana)
    - Alerting recommendations
  - Backup and disaster recovery guidance
  - Database migration strategy
  - Upgrade path documentation (v0.x to v1.0)
  - Version compatibility guarantees going forward

#### Quality Gates for v1.0.0 Release
All of the following must be met before v1.0.0 release:
- [ ] Test suite passes with >80% code coverage
- [ ] All critical and high-priority bugs resolved
- [ ] API documentation complete (OpenAPI spec)
- [ ] Production deployment guide complete
- [ ] Security review completed
- [ ] Performance benchmarks established
- [ ] Docker image published and tested
- [ ] Migration guide from v0.3.0 available
- [ ] At least 2 weeks of community testing (beta period)
- [ ] Zero known data integrity issues

### v1.1.0 - API Authentication & Security (Planned)

**Focus:** Secure the API with authentication and authorization

#### Authentication System
- **API Key Authentication** - Token-based access control
  - API key generation and management:
    - `POST /auth/keys` - Generate new API key (admin only)
    - `GET /auth/keys` - List API keys with metadata (admin only)
    - `DELETE /auth/keys/{key_id}` - Revoke API key (admin only)
  - Key features:
    - Cryptographically secure random key generation
    - Hashed storage (never store plaintext keys)
    - Key expiration dates (optional)
    - Key scoping (read-only vs. full access)
    - Usage tracking per key
  - Authentication header: `Authorization: Bearer <api_key>`
  - Backward compatibility: Optional authentication mode for migration

#### Authorization & Permissions
- **Role-Based Access Control** - Different permission levels
  - Permission levels:
    - **Admin** - Full access (create/delete keys, all operations)
    - **Read-Write** - Start simulations, modify data
    - **Read-Only** - View results and status only
  - Per-endpoint authorization checks
  - API key metadata includes role/permissions
  - Admin bootstrap process (initial setup)

#### Security Features
- **Enhanced Security Measures** - Defense in depth
  - Rate limiting per API key:
    - Configurable requests per minute/hour
    - Different limits per permission level
    - 429 Too Many Requests responses
  - Request logging and audit trail:
    - Log all API requests with key ID
    - Track failed authentication attempts
    - Alert on suspicious patterns
  - CORS configuration:
    - Configurable allowed origins
    - Secure defaults for production
  - HTTPS enforcement options:
    - Redirect HTTP to HTTPS
    - HSTS headers
  - API key rotation:
    - Support for multiple active keys
    - Graceful key migration

#### Configuration
- **Security Settings** - Environment-based configuration
  - Environment variables:
    - `AUTH_ENABLED` - Enable/disable authentication (default: false for v1.0.0 compatibility)
    - `ADMIN_API_KEY` - Bootstrap admin key (first-time setup)
    - `KEY_EXPIRATION_DAYS` - Default key expiration
    - `RATE_LIMIT_PER_MINUTE` - Default rate limit
    - `REQUIRE_HTTPS` - Force HTTPS in production
  - Migration path:
    - v1.0 users can upgrade with `AUTH_ENABLED=false`
    - Enable authentication when ready
    - Clear migration documentation

#### Documentation Updates
- **Security Documentation** - Comprehensive security guidance
  - Authentication setup guide:
    - Initial admin key setup
    - Creating API keys for clients
    - Key rotation procedures
  - Security best practices:
    - Network security considerations
    - HTTPS deployment requirements
    - Firewall rules recommendations
  - API documentation updates:
    - Authentication examples for all endpoints
    - Error responses (401, 403, 429)
    - Rate limit headers documentation

#### Benefits
- **Secure Public Deployment** - Safe to expose over internet
- **Multi-User Support** - Different users/applications with separate keys
- **Usage Tracking** - Monitor API usage per key
- **Compliance** - Meet security requirements for production deployments
- **Accountability** - Audit trail of who did what

#### Technical Implementation
- Authentication middleware for Flask
- Database schema for API keys:
  - `api_keys` table (id, key_hash, name, role, created_at, expires_at, last_used)
  - `api_requests` table (id, key_id, endpoint, timestamp, status_code)
- Secure key generation using `secrets` module
- Password hashing with bcrypt/argon2
- JWT tokens as alternative to static API keys (future consideration)

### v1.2.0 - Position History & Analytics (Planned)

**Focus:** Track and analyze trading behavior over time

#### Position History API
- **Position Tracking Endpoints** - Query historical position changes
  - `GET /positions/history` - Get position timeline for model(s)
    - Query parameters: `model`, `start_date`, `end_date`, `symbol`
    - Returns: chronological list of all position changes
    - Pagination support for long histories
  - `GET /positions/snapshot` - Get positions at specific date
    - Query parameters: `model`, `date`
    - Returns: portfolio state at end of trading day
  - `GET /positions/summary` - Get position statistics
    - Holdings duration (average, min, max)
    - Turnover rate (daily, weekly, monthly)
    - Most/least traded symbols
    - Trading frequency patterns

#### Trade Analysis
- **Trade-Level Insights** - Analyze individual trades
  - `GET /trades` - List all trades with filtering
    - Filter by: model, date range, symbol, action (buy/sell)
    - Sort by: date, profit/loss, volume
  - `GET /trades/{trade_id}` - Get trade details
    - Entry/exit prices and dates
    - Holding period
    - Realized profit/loss
    - Context (what else was traded that day)
  - Trade classification:
    - Round trips (buy + sell of same stock)
    - Partial positions (multiple entries/exits)
    - Long-term holds vs. day trades

#### Benefits
- Understand agent trading patterns and behavior
- Identify strategy characteristics (momentum, mean reversion, etc.)
- Debug unexpected trading decisions
- Compare trading styles across models

### v1.3.0 - Performance Metrics & Analytics (Planned)

**Focus:** Calculate standard financial performance metrics

#### Risk-Adjusted Performance
- **Performance Metrics API** - Calculate trading performance statistics
  - `GET /metrics/performance` - Overall performance metrics
    - Query parameters: `model`, `start_date`, `end_date`
    - Returns:
      - Total return, annualized return
      - Sharpe ratio (risk-adjusted return)
      - Sortino ratio (downside risk-adjusted)
      - Calmar ratio (return/max drawdown)
      - Information ratio
      - Alpha and beta (vs. NASDAQ 100 benchmark)
  - `GET /metrics/risk` - Risk metrics
    - Maximum drawdown (peak-to-trough decline)
    - Value at Risk (VaR) at 95% and 99% confidence
    - Conditional VaR (CVaR/Expected Shortfall)
    - Volatility (daily, annualized)
    - Downside deviation

#### Win/Loss Analysis
- **Trade Quality Metrics** - Analyze trade outcomes
  - `GET /metrics/trades` - Trade statistics
    - Win rate (% profitable trades)
    - Average win vs. average loss
    - Profit factor (gross profit / gross loss)
    - Largest win/loss
    - Win/loss streaks
    - Expectancy (average $ per trade)

#### Comparison & Benchmarking
- **Model Comparison** - Compare multiple models
  - `GET /metrics/compare` - Side-by-side comparison
    - Query parameters: `models[]`, `start_date`, `end_date`
    - Returns: all metrics for specified models
    - Ranking by various metrics
  - `GET /metrics/benchmark` - Compare to NASDAQ 100
    - Outperformance/underperformance
    - Correlation with market
    - Beta calculation

#### Time Series Metrics
- **Rolling Performance** - Metrics over time
  - `GET /metrics/timeseries` - Performance evolution
    - Query parameters: `model`, `metric`, `window` (days)
    - Returns: daily/weekly/monthly metric values
    - Examples: rolling Sharpe ratio, rolling volatility
    - Useful for detecting strategy degradation

#### Benefits
- Quantify agent performance objectively
- Identify risk characteristics
- Compare effectiveness of different AI models
- Detect performance changes over time

### v1.4.0 - Data Management API (Planned)

**Focus:** Price data operations and coverage management

#### Data Coverage Endpoints
- **Price Data Management** - Control and monitor price data
  - `GET /data/coverage` - Check available data
    - Query parameters: `symbol`, `start_date`, `end_date`
    - Returns: date ranges with data per symbol
    - Identify gaps in historical data
    - Show last refresh date per symbol
  - `GET /data/symbols` - List all available symbols
    - NASDAQ 100 constituents
    - Data availability per symbol
    - Metadata (company name, sector)

#### Data Operations
- **Download & Refresh** - Manage price data updates
  - `POST /data/download` - Trigger data download
    - Query parameters: `symbol`, `start_date`, `end_date`
    - Async operation (returns job_id)
    - Respects Alpha Vantage rate limits
    - Updates existing data or fills gaps
  - `GET /data/download/status` - Check download progress
    - Query parameters: `job_id`
    - Returns: progress, completed symbols, errors
  - `POST /data/refresh` - Update to latest available
    - Automatically downloads new data for all symbols
    - Scheduled refresh capability

#### Data Cleanup
- **Data Management Operations** - Clean and maintain data
  - `DELETE /data/range` - Remove data for date range
    - Query parameters: `symbol`, `start_date`, `end_date`
    - Use case: remove corrupted data before re-download
    - Validation: prevent deletion of in-use data
  - `POST /data/validate` - Check data integrity
    - Verify no missing dates (weekday gaps)
    - Check for outliers/anomalies
    - Returns: validation report with issues

#### Rate Limit Management
- **API Quota Tracking** - Monitor external API usage
  - `GET /data/quota` - Check Alpha Vantage quota
    - Calls remaining today
    - Reset time
    - Historical usage pattern

#### Benefits
- Visibility into data coverage
- Control over data refresh timing
- Ability to fill gaps in historical data
- Prevent simulations with incomplete data

### v1.5.0 - Web Dashboard UI (Planned)

**Focus:** Browser-based interface for monitoring and control

#### Core Dashboard
- **Web UI Foundation** - Modern web interface
  - Technology stack:
    - Frontend: React or Svelte (lightweight, modern)
    - Charts: Recharts or Chart.js
    - Real-time: Server-Sent Events (SSE) for updates
    - Styling: Tailwind CSS for responsive design
  - Deployment: Served alongside API (single container)
  - URL structure: `/` (UI), `/api/` (API endpoints)

#### Job Management View
- **Simulation Control** - Monitor and start simulations
  - Dashboard home page:
    - Active jobs with real-time progress
    - Recent completed jobs
    - Failed jobs with error messages
  - Start simulation form:
    - Model selection (checkboxes)
    - Date picker for target_date
    - Force re-simulate toggle
    - Submit button → launches job
  - Job detail view:
    - Live log streaming (SSE)
    - Per-model progress
    - Cancel job button
    - Download logs

#### Results Visualization
- **Performance Charts** - Visual analysis of results
  - Portfolio value over time (line chart)
    - Multiple models on same chart
    - Zoom/pan interactions
    - Hover tooltips with daily values
  - Cumulative returns comparison (line chart)
    - Percentage-based for fair comparison
    - Benchmark overlay (NASDAQ 100)
  - Position timeline (stacked area chart)
    - Show holdings composition over time
    - Click to filter by symbol
  - Trade log table:
    - Sortable columns (date, symbol, action, amount)
    - Filters (model, date range, symbol)
    - Pagination for large histories

#### Configuration Management
- **Settings & Config** - Manage simulation settings
  - Model configuration editor:
    - Add/remove models
    - Edit base URLs and API keys (masked)
    - Enable/disable models
    - Save to config file
  - Data coverage visualization:
    - Calendar heatmap showing data availability
    - Identify gaps in price data
    - Quick link to download missing dates

#### Real-Time Updates
- **Live Monitoring** - SSE-based updates
  - Job status changes
  - Progress percentage updates
  - New trade notifications
  - Error alerts

#### Benefits
- User-friendly interface (no curl commands needed)
- Visual feedback for long-running simulations
- Easy model comparison through charts
- Quick access to results without API queries

### v1.6.0 - Advanced Configuration & Customization (Planned)

**Focus:** Enhanced configuration options and extensibility

#### Agent Configuration
- **Advanced Agent Settings** - Fine-tune agent behavior
  - Per-model configuration overrides:
    - Custom system prompts
    - Different max_steps per model
    - Model-specific retry policies
    - Temperature/top_p settings
  - Trading constraints:
    - Maximum position sizes per stock
    - Sector exposure limits
    - Cash reserve requirements
    - Maximum trades per day
  - Risk management rules:
    - Stop-loss thresholds
    - Take-profit targets
    - Maximum portfolio concentration

#### Custom Trading Rules
- **Rule Engine** - Enforce trading constraints
  - Pre-trade validation hooks:
    - Check if trade violates constraints
    - Reject or adjust trades automatically
  - Post-trade validation:
    - Ensure position limits respected
    - Verify portfolio balance
  - Configurable via JSON rules file
  - API to query active rules

#### Multi-Strategy Support
- **Strategy Variants** - Run same model with different strategies
  - Strategy configurations:
    - Different initial cash amounts
    - Different universes (e.g., tech stocks only)
    - Different time periods for same model
  - Compare strategy effectiveness
  - A/B testing framework

#### Benefits
- Greater control over agent behavior
- Risk management beyond AI decision-making
- Strategy experimentation and optimization
- Support for diverse use cases

### v2.0.0 - Advanced Quantitative Modeling (Planned)

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
- **v0.4.0** - Simplified simulation control (planned)
- **v1.0.0** - Production stability & validation (planned)
- **v1.1.0** - API authentication & security (planned)
- **v1.2.0** - Position history & analytics (planned)
- **v1.3.0** - Performance metrics & analytics (planned)
- **v1.4.0** - Data management API (planned)
- **v1.5.0** - Web dashboard UI (planned)
- **v1.6.0** - Advanced configuration & customization (planned)
- **v2.0.0** - Advanced quantitative modeling (planned)

---

Last updated: 2025-11-01
