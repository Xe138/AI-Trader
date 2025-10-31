# Docker API Server Deployment

This guide explains how to run AI-Trader as a persistent REST API server using Docker for Windmill.dev integration.

## Quick Start

### 1. Environment Setup

```bash
# Copy environment template
cp .env.example .env

# Edit .env and add your API keys:
# - OPENAI_API_KEY
# - ALPHAADVANTAGE_API_KEY
# - JINA_API_KEY
```

### 2. Start API Server

```bash
# Start in API mode (default)
docker-compose up -d ai-trader-api

# View logs
docker-compose logs -f ai-trader-api

# Check health
curl http://localhost:8080/health
```

### 3. Test API Endpoints

```bash
# Health check
curl http://localhost:8080/health

# Trigger simulation
curl -X POST http://localhost:8080/simulate/trigger \
  -H "Content-Type: application/json" \
  -d '{
    "config_path": "/app/configs/default_config.json",
    "date_range": ["2025-01-16", "2025-01-17"],
    "models": ["gpt-4"]
  }'

# Check job status (replace JOB_ID)
curl http://localhost:8080/simulate/status/JOB_ID

# Query results
curl http://localhost:8080/results?date=2025-01-16
```

## Architecture

### Two Deployment Modes

**API Server Mode** (Windmill integration):
- REST API on port 8080
- Background job execution
- Persistent SQLite database
- Continuous uptime with health checks
- Start with: `docker-compose up -d ai-trader-api`

**Batch Mode** (one-time simulation):
- Command-line execution
- Runs to completion then exits
- Config file driven
- Start with: `docker-compose --profile batch up ai-trader-batch`

### Port Configuration

| Service | Internal Port | Default Host Port | Environment Variable |
|---------|--------------|-------------------|---------------------|
| API Server | 8080 | 8080 | `API_PORT` |
| Math MCP | 8000 | 8000 | `MATH_HTTP_PORT` |
| Search MCP | 8001 | 8001 | `SEARCH_HTTP_PORT` |
| Trade MCP | 8002 | 8002 | `TRADE_HTTP_PORT` |
| Price MCP | 8003 | 8003 | `GETPRICE_HTTP_PORT` |
| Web Dashboard | 8888 | 8888 | `WEB_HTTP_PORT` |

## API Endpoints

### POST /simulate/trigger
Trigger a new simulation job.

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

### GET /simulate/status/{job_id}
Get job progress and status.

**Response:**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "running",
  "progress": {
    "total_model_days": 4,
    "completed": 2,
    "failed": 0,
    "pending": 2
  },
  "date_range": ["2025-01-16", "2025-01-17"],
  "models": ["gpt-4", "claude-3.7-sonnet"],
  "created_at": "2025-01-16T10:00:00Z",
  "details": [
    {
      "date": "2025-01-16",
      "model": "gpt-4",
      "status": "completed",
      "started_at": "2025-01-16T10:00:05Z",
      "completed_at": "2025-01-16T10:05:23Z",
      "duration_seconds": 318.5
    }
  ]
}
```

### GET /results
Query simulation results with optional filters.

**Parameters:**
- `job_id` (optional): Filter by job UUID
- `date` (optional): Filter by trading date (YYYY-MM-DD)
- `model` (optional): Filter by model signature

**Response:**
```json
{
  "results": [
    {
      "id": 1,
      "job_id": "550e8400-e29b-41d4-a716-446655440000",
      "date": "2025-01-16",
      "model": "gpt-4",
      "action_id": 1,
      "action_type": "buy",
      "symbol": "AAPL",
      "amount": 10,
      "price": 250.50,
      "cash": 7495.00,
      "portfolio_value": 10000.00,
      "daily_profit": 0.00,
      "daily_return_pct": 0.00,
      "holdings": [
        {"symbol": "AAPL", "quantity": 10},
        {"symbol": "CASH", "quantity": 7495.00}
      ]
    }
  ],
  "count": 1
}
```

### GET /health
Service health check.

**Response:**
```json
{
  "status": "healthy",
  "database": "connected",
  "timestamp": "2025-01-16T10:00:00Z"
}
```

## Volume Mounts

Data persists across container restarts via volume mounts:

```yaml
volumes:
  - ./data:/app/data          # SQLite database, price data
  - ./logs:/app/logs          # Application logs
  - ./configs:/app/configs    # Configuration files
```

**Key files:**
- `/app/data/jobs.db` - SQLite database with job history and results
- `/app/data/merged.jsonl` - Cached price data (fetched on first run)
- `/app/logs/` - Application and MCP service logs

## Configuration

### Custom Config File

Place config files in `./configs/` directory:

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
      "basemodel": "gpt-4",
      "signature": "gpt-4",
      "enabled": true
    }
  ],
  "agent_config": {
    "max_steps": 30,
    "initial_cash": 10000.0
  }
}
```

Reference in API calls: `/app/configs/your_config.json`

## Troubleshooting

### Check Container Status
```bash
docker-compose ps
docker-compose logs ai-trader-api
```

### Health Check Failing
```bash
# Check if services started
docker exec ai-trader-api ps aux

# Test internal health
docker exec ai-trader-api curl http://localhost:8080/health

# Check MCP services
docker exec ai-trader-api curl http://localhost:8000/health
```

### Database Issues
```bash
# View database
docker exec ai-trader-api sqlite3 data/jobs.db ".tables"

# Reset database (WARNING: deletes all data)
rm ./data/jobs.db
docker-compose restart ai-trader-api
```

### Port Conflicts
If ports are already in use, edit `.env`:
```bash
API_PORT=9080  # Change to available port
```

## Windmill Integration

Example Windmill workflow step:

```python
import httpx

def trigger_simulation(
    api_url: str,
    config_path: str,
    start_date: str,
    end_date: str,
    models: list[str]
):
    """Trigger AI trading simulation via API."""

    response = httpx.post(
        f"{api_url}/simulate/trigger",
        json={
            "config_path": config_path,
            "date_range": [start_date, end_date],
            "models": models
        },
        timeout=30.0
    )

    response.raise_for_status()
    return response.json()

def check_status(api_url: str, job_id: str):
    """Check simulation job status."""

    response = httpx.get(
        f"{api_url}/simulate/status/{job_id}",
        timeout=10.0
    )

    response.raise_for_status()
    return response.json()
```

## Production Deployment

### Use Docker Hub Image
```yaml
# docker-compose.yml
services:
  ai-trader-api:
    image: ghcr.io/xe138/ai-trader:latest
    # ... rest of config
```

### Build Locally
```yaml
# docker-compose.yml
services:
  ai-trader-api:
    build: .
    # ... rest of config
```

### Environment Security
- Never commit `.env` to version control
- Use secrets management in production (Docker secrets, Kubernetes secrets, etc.)
- Rotate API keys regularly

## Monitoring

### Prometheus Metrics (Future)
Metrics endpoint planned: `GET /metrics`

### Log Aggregation
- Container logs: `docker-compose logs -f`
- Application logs: `./logs/api.log`
- MCP service logs: `./logs/mcp_*.log`

## Scaling Considerations

- Single-job concurrency enforced by database lock
- For parallel simulations, deploy multiple instances with separate databases
- Consider load balancer for high-availability setup
- Database size grows with number of simulations (plan for cleanup/archival)
