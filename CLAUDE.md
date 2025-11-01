# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI-Trader-Server is a REST API service for autonomous AI trading competitions where multiple AI models compete in NASDAQ 100 trading with zero human intervention. Each AI starts with $10,000 and uses standardized MCP (Model Context Protocol) tools to make fully autonomous trading decisions.

**Key Innovation:** Historical replay architecture with anti-look-ahead controls ensures AI agents can only access data from the current simulation date and earlier.

## Development Commands

### Environment Setup
```bash
# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# Edit .env and set:
# - OPENAI_API_BASE, OPENAI_API_KEY
# - ALPHAADVANTAGE_API_KEY, JINA_API_KEY
# - AGENT_MAX_STEP (default: 30)
```

### Data Preparation
```bash
# Download/update NASDAQ 100 stock data
cd data
python get_daily_price.py     # Fetch daily prices from Alpha Vantage
python merge_jsonl.py          # Merge into unified format (merged.jsonl)
cd ..
```

### Starting Services
```bash
# Start all MCP services (Math, Search, Trade, LocalPrices)
cd agent_tools
python start_mcp_services.py
cd ..

# MCP services use fixed internal ports (8000-8003)
# These are not exposed to the host and should not be changed
```

### Docker Deployment

```bash
# Build Docker image
docker-compose build

# Run with Docker Compose
docker-compose up

# Run in background
docker-compose up -d

# Run with custom config
docker-compose run ai-trader-server configs/my_config.json

# View logs
docker-compose logs -f

# Stop and remove containers
docker-compose down

# Pull pre-built image
docker pull ghcr.io/xe138/ai-trader-server:latest

# Test local Docker build
docker build -t ai-trader-server-test .
docker run --env-file .env -v $(pwd)/data:/app/data ai-trader-server-test
```

### Releasing Docker Images

```bash
# Create and push release tag
git tag v1.0.0
git push origin v1.0.0

# GitHub Actions automatically:
# 1. Builds Docker image
# 2. Tags with version and latest
# 3. Pushes to ghcr.io/xe138/ai-trader-server

# Verify build in Actions tab
# https://github.com/Xe138/AI-Trader-Server/actions
```

### Running Trading Simulations
```bash
# Run with default config
python main.py

# Run with custom config
python main.py configs/my_config.json

# Environment variables can override config dates:
INIT_DATE=2025-01-01 END_DATE=2025-01-31 python main.py
```

### Complete Workflow
```bash
# All-in-one startup script (data + services + trading + web)
bash main.sh
```

## Architecture

### Core Components

**1. Agent System** (`agent/base_agent/base_agent.py`)
- `BaseAgent`: Base class for all trading agents
- Manages MCP tool connections, AI model initialization, trading execution loops
- Handles position management and logging
- Supports retry logic with exponential backoff (`max_retries`, `base_delay`)

**2. Main Entry Point** (`main.py`)
- Dynamic agent class loading via `AGENT_REGISTRY`
- Multi-model concurrent trading support
- Date range validation and weekday filtering
- Configuration management (JSON + environment variables)

**3. MCP Toolchain** (`agent_tools/`)
- `tool_math.py`: Mathematical calculations (port 8000)
- `tool_jina_search.py`: Market intelligence search (port 8001)
- `tool_trade.py`: Buy/sell execution (port 8002)
- `tool_get_price_local.py`: Price queries (port 8003)
- `start_mcp_services.py`: Service orchestration with health checks

**4. Data Management** (`data/`)
- `daily_prices_*.json`: Individual stock OHLCV data
- `merged.jsonl`: Unified price data format
- `agent_data/[signature]/position/position.jsonl`: Position records
- `agent_data/[signature]/log/[date]/log.jsonl`: Trading logs

**5. Utilities** (`tools/`)
- `general_tools.py`: Config management, message extraction
- `price_tools.py`: Price queries, position updates
- `result_tools.py`: Performance calculations

### Data Flow

1. **Initialization**: Agent loads config, connects to MCP services, initializes AI model
2. **Trading Loop**: For each date:
   - Get system prompt with current positions, yesterday's prices, today's buy prices
   - AI agent analyzes market, calls search/math/price tools
   - Makes buy/sell decisions via trade tool
   - Logs all decisions and updates position.jsonl
3. **Position Tracking**: Each trade appends to `position.jsonl` with date, action, and updated holdings

### Configuration System

**Multi-layered config priority:**
1. Environment variables (highest)
2. Model-specific config (`openai_base_url`, `openai_api_key` in model config)
3. JSON config file
4. Default values (lowest)

**Runtime configuration** (API mode only):
- Dynamically created per model-day execution via `RuntimeConfigManager`
- Isolated config files prevent concurrent execution conflicts
- Contains: `TODAY_DATE`, `SIGNATURE`, `IF_TRADE`, `JOB_ID`
- Written by `write_config_value()`, read by `get_config_value()`

### Agent System

**BaseAgent Key Methods:**
- `initialize()`: Connect to MCP services, create AI model
- `run_trading_session(date)`: Execute single day's trading with retry logic
- `run_date_range(init_date, end_date)`: Process all weekdays in range
- `get_trading_dates()`: Resume from last date in position.jsonl
- `register_agent()`: Create initial position file with $10,000 cash

**Adding Custom Agents:**
1. Create new class inheriting from `BaseAgent`
2. Add to `AGENT_REGISTRY` in `main.py`:
   ```python
   "CustomAgent": {
       "module": "agent.custom.custom_agent",
       "class": "CustomAgent"
   }
   ```
3. Set `"agent_type": "CustomAgent"` in config JSON

### System Prompt Construction

**Dynamic prompt generation** (`prompts/agent_prompt.py`):
- `get_agent_system_prompt()` builds prompt with:
  - Current date
  - Yesterday's closing positions
  - Yesterday's closing prices
  - Today's buy prices
  - Yesterday's profit/loss
- AI agent must output `<FINISH_SIGNAL>` to end trading session

### Anti-Look-Ahead Controls

**Data access restrictions:**
- Price data: Only returns data for `date <= TODAY_DATE`
- Search results: News filtered by publication date
- All tools enforce temporal boundaries via `TODAY_DATE` from `runtime_env.json`

## Configuration File Format

```json
{
  "agent_type": "BaseAgent",
  "date_range": {
    "init_date": "2025-01-01",
    "end_date": "2025-01-31"
  },
  "models": [
    {
      "name": "model-display-name",
      "basemodel": "provider/model-id",
      "signature": "unique-identifier",
      "enabled": true,
      "openai_base_url": "optional-override",
      "openai_api_key": "optional-override"
    }
  ],
  "agent_config": {
    "max_steps": 30,           // Max reasoning iterations per day
    "max_retries": 3,          // Retry attempts on failure
    "base_delay": 1.0,         // Base retry delay (seconds)
    "initial_cash": 10000.0
  },
  "log_config": {
    "log_path": "./data/agent_data"
  }
}
```

## Data Formats

**Position Record** (`position.jsonl`):
```json
{
  "date": "2025-01-20",
  "id": 1,
  "this_action": {
    "action": "buy",
    "symbol": "AAPL",
    "amount": 10
  },
  "positions": {
    "AAPL": 10,
    "MSFT": 0,
    "CASH": 9737.6
  }
}
```

**Price Data** (`merged.jsonl`):
```json
{
  "Meta Data": {
    "2. Symbol": "AAPL",
    "3. Last Refreshed": "2025-01-20"
  },
  "Time Series (Daily)": {
    "2025-01-20": {
      "1. buy price": "255.8850",
      "2. high": "264.3750",
      "3. low": "255.6300",
      "4. sell price": "262.2400",
      "5. volume": "90483029"
    }
  }
}
```

## Important Implementation Details

**Trading Day Logic:**
- Only weekdays (Monday-Friday) are processed
- `get_trading_dates()` automatically resumes from last date in `position.jsonl`
- Skips days already processed (idempotent)

**Error Handling:**
- All async operations use `_ainvoke_with_retry()` with exponential backoff
- MCP service failures raise detailed error messages with troubleshooting hints
- Missing API keys halt startup with clear error messages

**Tool Message Extraction:**
- `extract_conversation(response, "final")`: Get AI's final answer
- `extract_tool_messages(response)`: Get all tool results
- Handles both dict and object-based message formats

**Logging:**
- Each trading day creates `log/[date]/log.jsonl`
- Logs include timestamps, signature, and all message exchanges
- Position updates append to single `position/position.jsonl`

**Development Mode:**

AI-Trader supports a development mode that mocks AI API calls for testing without costs.

**Deployment Modes:**
- `DEPLOYMENT_MODE=PROD`: Real AI calls, production data paths
- `DEPLOYMENT_MODE=DEV`: Mock AI, isolated dev environment

**DEV Mode Characteristics:**
- Uses `MockChatModel` from `agent/mock_provider/`
- Data paths: `data/dev_agent_data/` and `data/trading_dev.db`
- Dev database reset on startup (controlled by `PRESERVE_DEV_DATA`)
- API responses flagged with `deployment_mode` field

**Implementation Details:**
- Deployment config: `tools/deployment_config.py`
- Mock provider: `agent/mock_provider/mock_ai_provider.py`
- LangChain wrapper: `agent/mock_provider/mock_langchain_model.py`
- BaseAgent integration: `agent/base_agent/base_agent.py:146-189`
- Database handling: `api/database.py` (automatic path resolution)

**Testing Dev Mode:**
```bash
DEPLOYMENT_MODE=DEV python main.py configs/default_config.json
```

**Mock AI Behavior:**
- Deterministic stock rotation (AAPL → MSFT → GOOGL → etc.)
- Each response includes price query, buy order, and finish signal
- No actual AI API calls or costs

## Testing Changes

When modifying agent behavior or adding tools:
1. Create test config with short date range (2-3 days)
2. Set `max_steps` low (e.g., 10) to iterate faster
3. Check logs in `data/agent_data/[signature]/log/[date]/`
4. Verify position updates in `position/position.jsonl`
5. Use `main.sh` only for full end-to-end testing

See [docs/developer/testing.md](docs/developer/testing.md) for complete testing guide.

## Documentation Structure

The project uses a well-organized documentation structure:

### Root Level (User-facing)
- **README.md** - Project overview, quick start, API overview
- **QUICK_START.md** - 5-minute getting started guide
- **API_REFERENCE.md** - Complete API endpoint documentation
- **CHANGELOG.md** - Release notes and version history
- **TESTING_GUIDE.md** - Testing and validation procedures

### docs/user-guide/
- `configuration.md` - Environment setup and model configuration
- `using-the-api.md` - Common workflows and best practices
- `integration-examples.md` - Python, TypeScript, automation examples
- `troubleshooting.md` - Common issues and solutions

### docs/developer/
- `CONTRIBUTING.md` - Contribution guidelines
- `development-setup.md` - Local development without Docker
- `testing.md` - Running tests and validation
- `architecture.md` - System design and components
- `database-schema.md` - SQLite table reference
- `adding-models.md` - How to add custom AI models

### docs/deployment/
- `docker-deployment.md` - Production Docker setup
- `production-checklist.md` - Pre-deployment verification
- `monitoring.md` - Health checks, logging, metrics
- `scaling.md` - Multiple instances and load balancing

### docs/reference/
- `environment-variables.md` - Configuration reference
- `mcp-tools.md` - Trading tool documentation
- `data-formats.md` - File formats and schemas

### docs/ (Maintainer docs)
- `DOCKER.md` - Docker deployment details
- `RELEASING.md` - Release process for maintainers

## Common Issues

**MCP Services Not Running:**
- Error: "Failed to initialize MCP client"
- Fix: `cd agent_tools && python start_mcp_services.py`
- Verify ports not already in use: `lsof -i :8000-8003`

**Missing Price Data:**
- Ensure `data/merged.jsonl` exists
- Run `cd data && python get_daily_price.py && python merge_jsonl.py`
- Check Alpha Vantage API key is valid

**Runtime Config Issues:**
- Runtime configs are automatically managed by the API
- Configs are created per model-day execution in `data/` directory
- Ensure `data/` directory is writable

**Agent Doesn't Stop Trading:**
- Agent must output `<FINISH_SIGNAL>` within `max_steps`
- Increase `max_steps` if agent needs more reasoning time
- Check `log.jsonl` for errors preventing completion