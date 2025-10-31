<div align="center">

# 🚀 AI-Trader: Can AI Beat the Market?

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue.svg)](https://docker.com)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.120+-green.svg)](https://fastapi.tiangolo.com)

**REST API service for autonomous AI trading competitions. Run multiple AI models in NASDAQ 100 trading simulations with zero human intervention.**

[🚀 Quick Start](#-quick-start) • [📚 API Documentation](#-api-documentation) • [🐳 Docker Deployment](#-docker-deployment) • [中文文档](README_CN.md)

</div>

---

## ✨ Latest Updates (v0.3.0)

**Major Architecture Upgrade - REST API Service**

- 🌐 **REST API Server** - Complete FastAPI implementation
  - `POST /simulate/trigger` - Start simulation jobs
  - `GET /simulate/status/{job_id}` - Monitor progress
  - `GET /results` - Query results with filtering
  - `GET /health` - Service health checks
- 💾 **SQLite Database** - Persistent storage
  - Job tracking and lifecycle management
  - Position records with P&L tracking
  - AI reasoning logs and tool usage analytics
- 🐳 **Production-Ready Docker** - Single-command deployment
  - Health checks and automatic restarts
  - Volume persistence for data and logs
  - Simplified configuration
- 🧪 **Comprehensive Testing** - 102 tests, 85% coverage
- 📚 **Complete Documentation** - Deployment and validation guides

See [CHANGELOG.md](CHANGELOG.md) for full release notes.

---

## 🌟 What is AI-Trader?

> **AI-Trader enables multiple AI models to compete autonomously in NASDAQ 100 trading, making 100% independent decisions through a standardized tool-based architecture.**

### 🎯 Core Features

- 🤖 **Fully Autonomous Trading** - AI agents analyze, decide, and execute without human intervention
- 🌐 **REST API Architecture** - Trigger simulations and monitor results via HTTP
- 🛠️ **MCP Toolchain** - Standardized tools for market research, price queries, and trade execution
- 🏆 **Multi-Model Competition** - Deploy GPT, Claude, Qwen, DeepSeek, or custom models
- 📊 **Real-Time Analytics** - Track positions, P&L, and AI decision reasoning
- ⏰ **Historical Replay** - Backtest with anti-look-ahead controls
- 💾 **Persistent Storage** - SQLite database for all results and analytics
- 🔌 **External Orchestration** - Integrate with Windmill.dev or any HTTP client

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

### Key Components

- **FastAPI Server** - RESTful interface for job management and results
- **Job Manager** - Coordinates simulation execution, prevents concurrent jobs
- **Simulation Worker** - Orchestrates date-sequential, model-parallel execution
- **Model-Day Executor** - Runs single model for single date with isolated config
- **SQLite Database** - Persistent storage with 6 relational tables
- **MCP Services** - Internal tool ecosystem (math, search, trade, price)

---

## 🚀 Quick Start

### 🐳 Docker Deployment (Recommended)

**1. Prerequisites**
- Docker and Docker Compose installed
- API keys: OpenAI, Alpha Vantage, Jina AI

**2. Setup**
```bash
# Clone repository
git clone https://github.com/Xe138/AI-Trader.git
cd AI-Trader

# Configure environment
cp .env.example .env
# Edit .env and add your API keys:
#   OPENAI_API_KEY=your_key_here
#   ALPHAADVANTAGE_API_KEY=your_key_here
#   JINA_API_KEY=your_key_here
```

**3. Start API Server**
```bash
# Start in background
docker-compose up -d

# View logs
docker logs -f ai-trader

# Verify health
curl http://localhost:8080/health
```

**4. Trigger Simulation**
```bash
curl -X POST http://localhost:8080/simulate/trigger \
  -H "Content-Type: application/json" \
  -d '{
    "config_path": "/app/configs/default_config.json",
    "date_range": ["2025-01-16", "2025-01-17"],
    "models": ["gpt-4"]
  }'
```

**5. Monitor Progress**
```bash
# Get job status (use job_id from trigger response)
curl http://localhost:8080/simulate/status/{job_id}

# View results
curl http://localhost:8080/results?job_id={job_id}
```

---

## 📚 API Documentation

### Endpoints

#### `POST /simulate/trigger`
Start a new simulation job.

**Request:**
```json
{
  "config_path": "/app/configs/default_config.json",
  "date_range": ["2025-01-16", "2025-01-17"],
  "models": ["gpt-4", "claude-3.7-sonnet"]
}
```

**Response:**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "total_model_days": 4,
  "message": "Simulation job created and started"
}
```

#### `GET /simulate/status/{job_id}`
Query job execution status and progress.

**Response:**
```json
{
  "job_id": "550e8400-...",
  "status": "running",
  "progress": {
    "completed": 2,
    "failed": 0,
    "pending": 2,
    "total": 4
  },
  "details": [
    {
      "model_signature": "gpt-4",
      "trading_date": "2025-01-16",
      "status": "completed",
      "start_time": "2025-01-16T10:00:00",
      "end_time": "2025-01-16T10:05:00"
    }
  ]
}
```

#### `GET /results`
Retrieve simulation results with optional filtering.

**Query Parameters:**
- `job_id` - Filter by job UUID
- `date` - Filter by trading date (YYYY-MM-DD)
- `model` - Filter by model signature

**Response:**
```json
{
  "count": 2,
  "results": [
    {
      "job_id": "550e8400-...",
      "model_signature": "gpt-4",
      "trading_date": "2025-01-16",
      "final_cash": 9850.50,
      "total_value": 10250.75,
      "profit_loss": 250.75,
      "positions": {...},
      "holdings": [...]
    }
  ]
}
```

#### `GET /health`
Service health check.

**Response:**
```json
{
  "status": "healthy",
  "database": "connected",
  "timestamp": "2025-01-16T10:00:00Z"
}
```

---

## 🛠️ Configuration

### Environment Variables

```bash
# AI Model API Configuration
OPENAI_API_BASE=              # Optional: custom OpenAI proxy
OPENAI_API_KEY=your_key_here  # Required: OpenAI API key

# Data Source Configuration
ALPHAADVANTAGE_API_KEY=your_key_here  # Required: Alpha Vantage
JINA_API_KEY=your_key_here            # Required: Jina AI search

# API Server Port (host-side mapping)
API_PORT=8080  # Change if port 8080 is occupied

# Agent Configuration
AGENT_MAX_STEP=30  # Maximum reasoning steps per day

# Data Volume Configuration
VOLUME_PATH=.  # Base directory for persistent data
```

### Configuration File

Create custom configs in `configs/` directory:

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

### Manual Testing

```bash
# 1. Start API server
docker-compose up -d

# 2. Health check
curl http://localhost:8080/health

# 3. Trigger small test job
curl -X POST http://localhost:8080/simulate/trigger \
  -H "Content-Type: application/json" \
  -d '{
    "config_path": "/app/configs/default_config.json",
    "date_range": ["2025-01-16"],
    "models": ["gpt-4"]
  }'

# 4. Monitor until complete
curl http://localhost:8080/simulate/status/{job_id}

# 5. View results
curl http://localhost:8080/results?job_id={job_id}
```

See [TESTING_GUIDE.md](TESTING_GUIDE.md) for comprehensive testing procedures and troubleshooting.

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

- 📰 **Research Markets** - Search news, analyst reports, financial data (Jina AI)
- 📊 **Query Prices** - Get real-time and historical OHLCV data
- 💰 **Execute Trades** - Buy/sell stocks, manage positions
- 🧮 **Perform Calculations** - Mathematical analysis and computations
- 📝 **Log Reasoning** - Document decision-making process

**All operations are 100% autonomous - zero human intervention or pre-programmed strategies.**

---

## 📁 Project Structure

```
AI-Trader/
├── api/                          # FastAPI application
│   ├── main.py                   # API server entry point
│   ├── database.py               # SQLite schema and operations
│   ├── job_manager.py            # Job lifecycle management
│   ├── simulation_worker.py      # Job orchestration
│   ├── model_day_executor.py     # Single model-day execution
│   ├── runtime_manager.py        # Isolated runtime configs
│   └── models.py                 # Pydantic request/response models
│
├── agent/                        # AI agent core
│   └── base_agent/
│       └── base_agent.py         # BaseAgent implementation
│
├── agent_tools/                  # MCP service implementations
│   ├── tool_math.py              # Mathematical calculations
│   ├── tool_jina_search.py       # Market intelligence search
│   ├── tool_trade.py             # Trading execution
│   ├── tool_get_price_local.py   # Price queries
│   └── start_mcp_services.py     # Service orchestration
│
├── tests/                        # Test suite (102 tests, 85% coverage)
│   ├── unit/                     # Unit tests
│   └── integration/              # Integration tests
│
├── configs/                      # Configuration files
│   └── default_config.json       # Default simulation config
│
├── scripts/                      # Validation scripts
│   ├── validate_docker_build.sh  # Docker build validation
│   └── test_api_endpoints.sh     # API endpoint testing
│
├── data/                         # Persistent data (volume mount)
│   ├── jobs.db                   # SQLite database
│   └── agent_data/               # Agent execution data
│
├── docker-compose.yml            # Docker orchestration
├── Dockerfile                    # Container image definition
├── entrypoint.sh                 # Container startup script
├── requirements.txt              # Python dependencies
└── README.md                     # This file
```

---

## 🔌 Integration Examples

### Windmill.dev Workflow

```typescript
// Trigger simulation
export async function triggerSimulation(
  api_url: string,
  config_path: string,
  date_range: string[],
  models: string[]
) {
  const response = await fetch(`${api_url}/simulate/trigger`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ config_path, date_range, models })
  });
  return response.json();
}

// Poll for completion
export async function waitForCompletion(api_url: string, job_id: string) {
  while (true) {
    const status = await fetch(`${api_url}/simulate/status/${job_id}`)
      .then(r => r.json());

    if (['completed', 'failed', 'partial'].includes(status.status)) {
      return status;
    }

    await new Promise(resolve => setTimeout(resolve, 10000)); // 10s poll
  }
}

// Get results
export async function getResults(api_url: string, job_id: string) {
  return fetch(`${api_url}/results?job_id=${job_id}`)
    .then(r => r.json());
}
```

### Python Client

```python
import requests
import time

# Trigger simulation
response = requests.post('http://localhost:8080/simulate/trigger', json={
    'config_path': '/app/configs/default_config.json',
    'date_range': ['2025-01-16', '2025-01-17'],
    'models': ['gpt-4', 'claude-3.7-sonnet']
})
job_id = response.json()['job_id']

# Poll for completion
while True:
    status = requests.get(f'http://localhost:8080/simulate/status/{job_id}').json()
    if status['status'] in ['completed', 'failed', 'partial']:
        break
    time.sleep(10)

# Get results
results = requests.get(f'http://localhost:8080/results?job_id={job_id}').json()
print(f"Completed with {results['count']} results")
```

---

## 📊 Database Schema

The SQLite database (`data/jobs.db`) contains:

### Tables

- **jobs** - Job metadata (id, status, created_at, etc.)
- **job_details** - Per model-day execution details
- **positions** - Trading position records with P&L
- **holdings** - Portfolio holdings breakdown
- **reasoning_logs** - AI decision reasoning history
- **tool_usage** - MCP tool usage statistics

### Querying Data

```bash
# Direct database access
docker exec -it ai-trader sqlite3 /app/data/jobs.db

# Example queries
sqlite> SELECT * FROM jobs ORDER BY created_at DESC LIMIT 5;
sqlite> SELECT model_signature, AVG(profit_loss) FROM positions GROUP BY model_signature;
sqlite> SELECT * FROM reasoning_logs WHERE job_id='...';
```

---

## 🛠️ Development

### Running Tests

```bash
# Install dependencies
pip install -r requirements.txt

# Run test suite
pytest tests/ -v --cov=api --cov-report=term-missing

# Run specific test
pytest tests/unit/test_job_manager.py -v
```

### Adding Custom Models

Edit `configs/default_config.json`:

```json
{
  "models": [
    {
      "name": "Custom Model",
      "basemodel": "provider/model-name",
      "signature": "custom-model",
      "enabled": true,
      "openai_base_url": "https://api.custom.com/v1",
      "openai_api_key": "custom_key_here"
    }
  ]
}
```

---

## 📖 Documentation

- [CHANGELOG.md](CHANGELOG.md) - Release notes and version history
- [DOCKER_API.md](DOCKER_API.md) - Detailed API deployment guide
- [TESTING_GUIDE.md](TESTING_GUIDE.md) - Comprehensive testing procedures
- [CLAUDE.md](CLAUDE.md) - Development guide for contributors

---

## 🤝 Contributing

Contributions welcome! Please read [CLAUDE.md](CLAUDE.md) for development guidelines.

---

## 📄 License

MIT License - see [LICENSE](LICENSE) for details

---

## 🔗 Links

- **GitHub**: https://github.com/Xe138/AI-Trader
- **Docker Hub**: `ghcr.io/xe138/ai-trader:latest`
- **Issues**: https://github.com/Xe138/AI-Trader/issues

---

<div align="center">

**Built with FastAPI, SQLite, Docker, and the MCP Protocol**

</div>
