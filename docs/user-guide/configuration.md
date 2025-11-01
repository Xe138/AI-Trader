# Configuration Guide

Complete guide to configuring AI-Trader.

---

## Environment Variables

Set in `.env` file in project root.

### Required Variables

```bash
# OpenAI API (or compatible endpoint)
OPENAI_API_KEY=sk-your-key-here

# Alpha Vantage (price data)
ALPHAADVANTAGE_API_KEY=your-key-here

# Jina AI (market intelligence search)
JINA_API_KEY=your-key-here
```

### Optional Variables

```bash
# API Server Configuration
API_PORT=8080                       # Host port mapping (default: 8080)
API_HOST=0.0.0.0                   # Bind address (default: 0.0.0.0)

# OpenAI Configuration
OPENAI_API_BASE=https://api.openai.com/v1  # Custom endpoint

# Simulation Limits
MAX_CONCURRENT_JOBS=1               # Max simultaneous jobs (default: 1)
MAX_SIMULATION_DAYS=30              # Max date range per job (default: 30)

# Price Data Management
AUTO_DOWNLOAD_PRICE_DATA=true       # Auto-fetch missing data (default: true)

# Agent Configuration
AGENT_MAX_STEP=30                   # Max reasoning steps per day (default: 30)

# Volume Paths
VOLUME_PATH=.                       # Base directory for data (default: .)

# MCP Service Ports (usually don't need to change)
MATH_HTTP_PORT=8000
SEARCH_HTTP_PORT=8001
TRADE_HTTP_PORT=8002
GETPRICE_HTTP_PORT=8003
```

---

## Model Configuration

Edit `configs/default_config.json` to define available AI models.

### Configuration Structure

```json
{
  "agent_type": "BaseAgent",
  "date_range": {
    "init_date": "2025-01-01",
    "end_date": "2025-01-31"
  },
  "models": [
    {
      "name": "GPT-4",
      "basemodel": "openai/gpt-4",
      "signature": "gpt-4",
      "enabled": true
    }
  ],
  "agent_config": {
    "max_steps": 30,
    "max_retries": 3,
    "initial_cash": 10000.0
  },
  "log_config": {
    "log_path": "./data/agent_data"
  }
}
```

### Model Configuration Fields

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Display name for the model |
| `basemodel` | Yes | Model identifier (e.g., `openai/gpt-4`, `anthropic/claude-3.7-sonnet`) |
| `signature` | Yes | Unique identifier used in API requests and database |
| `enabled` | Yes | Whether this model runs when no models specified in API request |
| `openai_base_url` | No | Custom API endpoint for this model |
| `openai_api_key` | No | Model-specific API key (overrides `OPENAI_API_KEY` env var) |

### Adding Custom Models

**Example: Add Claude 3.7 Sonnet**

```json
{
  "models": [
    {
      "name": "Claude 3.7 Sonnet",
      "basemodel": "anthropic/claude-3.7-sonnet",
      "signature": "claude-3.7-sonnet",
      "enabled": true,
      "openai_base_url": "https://api.anthropic.com/v1",
      "openai_api_key": "your-anthropic-key"
    }
  ]
}
```

**Example: Add DeepSeek via OpenRouter**

```json
{
  "models": [
    {
      "name": "DeepSeek",
      "basemodel": "deepseek/deepseek-chat",
      "signature": "deepseek",
      "enabled": true,
      "openai_base_url": "https://openrouter.ai/api/v1",
      "openai_api_key": "your-openrouter-key"
    }
  ]
}
```

### Agent Configuration

| Field | Description | Default |
|-------|-------------|---------|
| `max_steps` | Maximum reasoning iterations per trading day | 30 |
| `max_retries` | Retry attempts on API failures | 3 |
| `initial_cash` | Starting capital per model | 10000.0 |

---

## Port Configuration

### Default Ports

| Service | Internal Port | Host Port (configurable) |
|---------|---------------|--------------------------|
| API Server | 8080 | `API_PORT` (default: 8080) |
| MCP Math | 8000 | Not exposed to host |
| MCP Search | 8001 | Not exposed to host |
| MCP Trade | 8002 | Not exposed to host |
| MCP Price | 8003 | Not exposed to host |

### Changing API Port

If port 8080 is already in use:

```bash
# Add to .env
echo "API_PORT=8889" >> .env

# Restart
docker-compose down
docker-compose up -d

# Access on new port
curl http://localhost:8889/health
```

---

## Volume Configuration

Docker volumes persist data across container restarts:

```yaml
volumes:
  - ./data:/app/data          # Database, price data, agent data
  - ./configs:/app/configs    # Configuration files
  - ./logs:/app/logs          # Application logs
```

### Data Directory Structure

```
data/
├── jobs.db                      # SQLite database
├── merged.jsonl                 # Cached price data
├── daily_prices_*.json          # Individual stock data
├── price_coverage.json          # Data availability tracking
└── agent_data/                  # Agent execution data
    └── {signature}/
        ├── position/
        │   └── position.jsonl   # Trading positions
        └── log/
            └── {date}/
                └── log.jsonl    # Trading logs
```

---

## API Key Setup

### OpenAI API Key

1. Visit [platform.openai.com/api-keys](https://platform.openai.com/api-keys)
2. Create new key
3. Add to `.env`:
   ```bash
   OPENAI_API_KEY=sk-...
   ```

### Alpha Vantage API Key

1. Visit [alphavantage.co/support/#api-key](https://www.alphavantage.co/support/#api-key)
2. Get free key (5 req/min) or premium (75 req/min)
3. Add to `.env`:
   ```bash
   ALPHAADVANTAGE_API_KEY=...
   ```

### Jina AI API Key

1. Visit [jina.ai](https://jina.ai/)
2. Sign up for free tier
3. Add to `.env`:
   ```bash
   JINA_API_KEY=...
   ```

---

## Configuration Examples

### Development Setup

```bash
# .env
API_PORT=8080
MAX_CONCURRENT_JOBS=1
MAX_SIMULATION_DAYS=5           # Limit for faster testing
AUTO_DOWNLOAD_PRICE_DATA=true
AGENT_MAX_STEP=10               # Fewer steps for faster iteration
```

### Production Setup

```bash
# .env
API_PORT=8080
MAX_CONCURRENT_JOBS=1
MAX_SIMULATION_DAYS=30
AUTO_DOWNLOAD_PRICE_DATA=true
AGENT_MAX_STEP=30
```

### Multi-Model Competition

```json
// configs/default_config.json
{
  "models": [
    {
      "name": "GPT-4",
      "basemodel": "openai/gpt-4",
      "signature": "gpt-4",
      "enabled": true
    },
    {
      "name": "Claude 3.7",
      "basemodel": "anthropic/claude-3.7-sonnet",
      "signature": "claude-3.7",
      "enabled": true,
      "openai_base_url": "https://api.anthropic.com/v1",
      "openai_api_key": "anthropic-key"
    },
    {
      "name": "GPT-3.5 Turbo",
      "basemodel": "openai/gpt-3.5-turbo",
      "signature": "gpt-3.5-turbo",
      "enabled": false  // Not run by default
    }
  ]
}
```

---

## Environment Variable Priority

When the same configuration exists in multiple places:

1. **API request parameters** (highest priority)
2. **Model-specific config** (`openai_base_url`, `openai_api_key` in model config)
3. **Environment variables** (`.env` file)
4. **Default values** (lowest priority)

Example:
```json
// If model config has:
{
  "openai_api_key": "model-specific-key"
}

// This overrides OPENAI_API_KEY from .env
```

---

## Validation

After configuration changes:

```bash
# Restart service
docker-compose down
docker-compose up -d

# Verify health
curl http://localhost:8080/health

# Check logs for errors
docker logs ai-trader | grep -i error
```
