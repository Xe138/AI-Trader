<div align="center">

# 🚀 AI-Trader: Can AI Beat the Market?

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue.svg)](https://docker.com)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.120+-green.svg)](https://fastapi.tiangolo.com)

**REST API service for autonomous AI trading competitions. Run multiple AI models in NASDAQ 100 trading simulations with zero human intervention.**

[🚀 Quick Start](QUICK_START.md) • [📚 API Reference](API_REFERENCE.md) • [📖 Documentation](#documentation)

</div>

---

## 🌟 What is AI-Trader?

> **AI-Trader enables multiple AI models to compete autonomously in NASDAQ 100 trading, making 100% independent decisions through a standardized tool-based architecture.**

### Key Features

- 🤖 **Fully Autonomous Trading** - AI agents analyze, decide, and execute without human intervention
- 🌐 **REST API Architecture** - Trigger simulations and monitor results via HTTP
- 🛠️ **MCP Toolchain** - Standardized tools for market research, price queries, and trade execution
- 🏆 **Multi-Model Competition** - Deploy GPT, Claude, Qwen, DeepSeek, or custom models
- 📊 **Real-Time Analytics** - Track positions, P&L, and AI decision reasoning
- ⏰ **Historical Replay** - Backtest with anti-look-ahead controls
- 💾 **Persistent Storage** - SQLite database for all results and analytics
- 🔌 **External Orchestration** - Integrate with any HTTP client or workflow automation service

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     REST API (Port 8080)                    │
│  POST /simulate/trigger  │  GET /status  │  GET /results   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   Simulation Worker                         │
│  • Job Manager (concurrent job prevention)                  │
│  • Date-sequential, model-parallel execution                │
│  • Isolated runtime configs per model-day                   │
└─────────────────────────────────────────────────────────────┘
                              │
                ┌─────────────┴─────────────┐
                ▼                           ▼
┌───────────────────────────┐   ┌──────────────────────────┐
│   AI Agent (Model-Day)    │   │   SQLite Database        │
│  • GPT-4, Claude, etc.    │   │  • Jobs & Details        │
│  • MCP Tool Access        │   │  • Positions & Holdings  │
│  • Decision Logging       │   │  • Reasoning Logs        │
└───────────────────────────┘   └──────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────────┐
│                  MCP Services (Internal)                    │
│  • Math (8000)  • Search (8001)  • Trade (8002)            │
│  • Price (8003) - All localhost-only                        │
└─────────────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### Docker Deployment (5 minutes)

**1. Prerequisites**
- Docker and Docker Compose installed
- API keys: OpenAI, Alpha Vantage, Jina AI

**2. Setup**
```bash
git clone https://github.com/Xe138/AI-Trader.git
cd AI-Trader

# Configure environment
cp .env.example .env
# Edit .env and add your API keys
```

**3. Start Service**
```bash
docker-compose up -d

# Verify health
curl http://localhost:8080/health
```

**4. Run Simulation**
```bash
curl -X POST http://localhost:8080/simulate/trigger \
  -H "Content-Type: application/json" \
  -d '{
    "start_date": "2025-01-16",
    "models": ["gpt-4"]
  }'
```

**5. Monitor Progress**
```bash
# Use job_id from trigger response
curl http://localhost:8080/simulate/status/{job_id}
```

**6. View Results**
```bash
curl "http://localhost:8080/results?job_id={job_id}"
```

📖 **Detailed guide:** [QUICK_START.md](QUICK_START.md)

---

## 📚 API Overview

### Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/simulate/trigger` | POST | Start simulation job |
| `/simulate/status/{job_id}` | GET | Check job progress |
| `/results` | GET | Query trading results |
| `/health` | GET | Service health check |

### Example: Trigger Simulation

**Request:**
```bash
curl -X POST http://localhost:8080/simulate/trigger \
  -H "Content-Type: application/json" \
  -d '{
    "start_date": "2025-01-16",
    "end_date": "2025-01-17",
    "models": ["gpt-4", "claude-3.7-sonnet"]
  }'
```

**Response:**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "total_model_days": 4,
  "message": "Simulation job created with 2 trading dates"
}
```

**Parameters:**
- `start_date` (required) - Start date in YYYY-MM-DD format
- `end_date` (optional) - End date, defaults to `start_date` for single-day simulation
- `models` (optional) - Model signatures to run, defaults to all enabled models in config

📖 **Complete reference:** [API_REFERENCE.md](API_REFERENCE.md)

---

## 🎯 Trading Environment

- 💰 **Initial Capital**: $10,000 per AI model
- 📈 **Trading Universe**: NASDAQ 100 stocks
- ⏰ **Trading Schedule**: Weekdays only (historical simulation)
- 📊 **Data Sources**: Alpha Vantage (prices) + Jina AI (market intelligence)
- 🔄 **Anti-Look-Ahead**: Data access limited to current date and earlier

---

## 🧠 AI Agent Capabilities

Through the MCP (Model Context Protocol) toolchain, AI agents can:

- 📰 **Research Markets** - Search news, analyst reports, financial data
- 📊 **Query Prices** - Get real-time and historical OHLCV data
- 💰 **Execute Trades** - Buy/sell stocks, manage positions
- 🧮 **Perform Calculations** - Mathematical analysis and computations
- 📝 **Log Reasoning** - Document decision-making process

**All operations are 100% autonomous - zero human intervention or pre-programmed strategies.**

---

## 🔌 Integration Examples

### Python Client

```python
import requests
import time

class AITraderClient:
    def __init__(self, base_url="http://localhost:8080"):
        self.base_url = base_url

    def trigger_simulation(self, start_date, end_date=None, models=None):
        payload = {"start_date": start_date}
        if end_date:
            payload["end_date"] = end_date
        if models:
            payload["models"] = models

        response = requests.post(
            f"{self.base_url}/simulate/trigger",
            json=payload
        )
        response.raise_for_status()
        return response.json()

    def wait_for_completion(self, job_id, poll_interval=10):
        while True:
            response = requests.get(
                f"{self.base_url}/simulate/status/{job_id}"
            )
            status = response.json()

            if status["status"] in ["completed", "partial", "failed"]:
                return status

            time.sleep(poll_interval)

# Usage
client = AITraderClient()
job = client.trigger_simulation("2025-01-16", models=["gpt-4"])
result = client.wait_for_completion(job["job_id"])
```

### TypeScript/JavaScript

```typescript
async function runSimulation() {
  // Trigger simulation
  const response = await fetch("http://localhost:8080/simulate/trigger", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      start_date: "2025-01-16",
      models: ["gpt-4"]
    })
  });

  const job = await response.json();

  // Poll for completion
  while (true) {
    const statusResponse = await fetch(
      `http://localhost:8080/simulate/status/${job.job_id}`
    );
    const status = await statusResponse.json();

    if (["completed", "partial", "failed"].includes(status.status)) {
      return status;
    }

    await new Promise(resolve => setTimeout(resolve, 10000));
  }
}
```

### Scheduled Automation

Use any scheduler (cron, Airflow, etc.):

```bash
#!/bin/bash
# daily_simulation.sh

DATE=$(date -d "yesterday" +%Y-%m-%d)

curl -X POST http://localhost:8080/simulate/trigger \
  -H "Content-Type: application/json" \
  -d "{\"start_date\": \"$DATE\", \"models\": [\"gpt-4\"]}"
```

Add to crontab:
```
0 6 * * * /path/to/daily_simulation.sh
```

📖 **More examples:** [docs/user-guide/integration-examples.md](docs/user-guide/integration-examples.md)

---

## 📖 Documentation

### User Guides
- [Quick Start](QUICK_START.md) - Get running in 5 minutes
- [Configuration Guide](docs/user-guide/configuration.md) - Environment setup and model configuration
- [Using the API](docs/user-guide/using-the-api.md) - Common workflows and best practices
- [Integration Examples](docs/user-guide/integration-examples.md) - Python, TypeScript, automation
- [Troubleshooting](docs/user-guide/troubleshooting.md) - Common issues and solutions

### Developer Documentation
- [Development Setup](docs/developer/development-setup.md) - Local development without Docker
- [Testing Guide](docs/developer/testing.md) - Running tests and validation
- [Architecture](docs/developer/architecture.md) - System design and components
- [Database Schema](docs/developer/database-schema.md) - SQLite table reference
- [Adding Models](docs/developer/adding-models.md) - How to add custom AI models

### Deployment
- [Docker Deployment](docs/deployment/docker-deployment.md) - Production Docker setup
- [Production Checklist](docs/deployment/production-checklist.md) - Pre-deployment verification
- [Monitoring](docs/deployment/monitoring.md) - Health checks, logging, metrics
- [Scaling](docs/deployment/scaling.md) - Multiple instances and load balancing

### Reference
- [API Reference](API_REFERENCE.md) - Complete endpoint documentation
- [Environment Variables](docs/reference/environment-variables.md) - Configuration reference
- [MCP Tools](docs/reference/mcp-tools.md) - Trading tool documentation
- [Data Formats](docs/reference/data-formats.md) - File formats and schemas

---

## 🛠️ Configuration

### Environment Variables

```bash
# Required API Keys
OPENAI_API_KEY=sk-your-key-here
ALPHAADVANTAGE_API_KEY=your-key-here
JINA_API_KEY=your-key-here

# Optional Configuration
API_PORT=8080                      # API server port
MAX_CONCURRENT_JOBS=1              # Max simultaneous simulations
MAX_SIMULATION_DAYS=30             # Max date range per job
AUTO_DOWNLOAD_PRICE_DATA=true     # Auto-fetch missing data
```

### Model Configuration

Edit `configs/default_config.json`:

```json
{
  "models": [
    {
      "name": "GPT-4",
      "basemodel": "openai/gpt-4",
      "signature": "gpt-4",
      "enabled": true
    },
    {
      "name": "Claude 3.7 Sonnet",
      "basemodel": "anthropic/claude-3.7-sonnet",
      "signature": "claude-3.7-sonnet",
      "enabled": true,
      "openai_base_url": "https://api.anthropic.com/v1",
      "openai_api_key": "your-anthropic-key"
    }
  ],
  "agent_config": {
    "max_steps": 30,
    "initial_cash": 10000.0
  }
}
```

📖 **Full guide:** [docs/user-guide/configuration.md](docs/user-guide/configuration.md)

---

## 📊 Database Schema

SQLite database at `data/jobs.db` contains:

- **jobs** - Job metadata and status
- **job_details** - Per model-day execution details
- **positions** - Trading position records with P&L
- **holdings** - Portfolio holdings breakdown
- **reasoning_logs** - AI decision reasoning history
- **tool_usage** - MCP tool usage statistics
- **price_data** - Historical price data cache
- **price_coverage** - Data availability tracking

Query directly:
```bash
docker exec -it ai-trader sqlite3 /app/data/jobs.db
sqlite> SELECT * FROM jobs ORDER BY created_at DESC LIMIT 5;
```

📖 **Schema reference:** [docs/developer/database-schema.md](docs/developer/database-schema.md)

---

## 🧪 Testing & Validation

### Automated Validation

```bash
# Make scripts executable
chmod +x scripts/*.sh

# Validate Docker build and startup
bash scripts/validate_docker_build.sh

# Test all API endpoints
bash scripts/test_api_endpoints.sh
```

### Unit Tests

```bash
# Install dependencies
pip install -r requirements.txt

# Run test suite
pytest tests/ -v --cov=api --cov-report=term-missing
```

📖 **Testing guide:** [docs/developer/testing.md](docs/developer/testing.md)

---

## 📈 Latest Updates

### v0.3.0 (Current)

**Major Architecture Upgrade - REST API Service**

- 🌐 **REST API Server** - Complete FastAPI implementation
  - `POST /simulate/trigger` - Start simulation jobs with date ranges
  - `GET /simulate/status/{job_id}` - Monitor progress in real-time
  - `GET /results` - Query results with filtering
  - `GET /health` - Service health checks
- 💾 **SQLite Database** - Complete persistence layer
- 📊 **On-Demand Price Data** - Automatic gap filling with priority-based downloads
- 🐳 **Production-Ready Docker** - Single-command deployment
- 🧪 **Comprehensive Testing** - 175 tests with high coverage
- 📚 **Complete Documentation** - API guides and validation procedures

See [CHANGELOG.md](CHANGELOG.md) for full release notes and [ROADMAP.md](ROADMAP.md) for planned features.

---

## 🤝 Contributing

Contributions welcome! Please read [docs/developer/CONTRIBUTING.md](docs/developer/CONTRIBUTING.md) for development guidelines.

---

## 📄 License

MIT License - see [LICENSE](LICENSE) for details

---

## 🔗 Links

- **GitHub**: https://github.com/Xe138/AI-Trader
- **Docker Hub**: `ghcr.io/xe138/ai-trader:latest`
- **Issues**: https://github.com/Xe138/AI-Trader/issues
- **API Docs**: http://localhost:8080/docs (when running)

---

<div align="center">

**Built with FastAPI, SQLite, Docker, and the MCP Protocol**

[⬆ Back to top](#-ai-trader-can-ai-beat-the-market)

</div>
