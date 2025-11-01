# Quick Start Guide

Get AI-Trader running in under 5 minutes using Docker.

---

## Prerequisites

- **Docker** and **Docker Compose** installed
  - [Install Docker Desktop](https://www.docker.com/products/docker-desktop/) (includes both)
- **API Keys:**
  - OpenAI API key ([get one here](https://platform.openai.com/api-keys))
  - Alpha Vantage API key ([free tier](https://www.alphavantage.co/support/#api-key))
  - Jina AI API key ([free tier](https://jina.ai/))
- **System Requirements:**
  - 2GB free disk space
  - Internet connection

---

## Step 1: Clone Repository

```bash
git clone https://github.com/Xe138/AI-Trader.git
cd AI-Trader
```

---

## Step 2: Configure Environment

Create `.env` file with your API keys:

```bash
cp .env.example .env
```

Edit `.env` and add your keys:

```bash
# Required API Keys
OPENAI_API_KEY=sk-your-openai-key-here
ALPHAADVANTAGE_API_KEY=your-alpha-vantage-key-here
JINA_API_KEY=your-jina-key-here

# Optional: Custom OpenAI endpoint
# OPENAI_API_BASE=https://api.openai.com/v1

# Optional: API server port (default: 8080)
# API_PORT=8080
```

**Save the file.**

---

## Step 3: Start the API Server

```bash
docker-compose up -d
```

This will:
- Build the Docker image (~5-10 minutes first time)
- Start the AI-Trader API service
- Start internal MCP services (math, search, trade, price)
- Initialize the SQLite database

**Wait for startup:**

```bash
# View logs
docker logs -f ai-trader

# Wait for this message:
# "Application startup complete"
# Press Ctrl+C to stop viewing logs
```

---

## Step 4: Verify Service is Running

```bash
curl http://localhost:8080/health
```

**Expected response:**

```json
{
  "status": "healthy",
  "database": "connected",
  "timestamp": "2025-01-16T10:00:00Z"
}
```

If you see `"status": "healthy"`, you're ready!

---

## Step 5: Run Your First Simulation

Trigger a simulation for a single day with GPT-4:

```bash
curl -X POST http://localhost:8080/simulate/trigger \
  -H "Content-Type: application/json" \
  -d '{
    "start_date": "2025-01-16",
    "models": ["gpt-4"]
  }'
```

**Response:**

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "total_model_days": 1,
  "message": "Simulation job created with 1 trading dates"
}
```

**Save the `job_id`** - you'll need it to check status.

---

## Step 6: Monitor Progress

```bash
# Replace with your job_id from Step 5
JOB_ID="550e8400-e29b-41d4-a716-446655440000"

curl http://localhost:8080/simulate/status/$JOB_ID
```

**While running:**

```json
{
  "job_id": "550e8400-...",
  "status": "running",
  "progress": {
    "total_model_days": 1,
    "completed": 0,
    "failed": 0,
    "pending": 1
  },
  ...
}
```

**When complete:**

```json
{
  "job_id": "550e8400-...",
  "status": "completed",
  "progress": {
    "total_model_days": 1,
    "completed": 1,
    "failed": 0,
    "pending": 0
  },
  ...
}
```

**Typical execution time:** 2-5 minutes for a single model-day.

---

## Step 7: View Results

```bash
curl "http://localhost:8080/results?job_id=$JOB_ID" | jq '.'
```

**Example output:**

```json
{
  "results": [
    {
      "id": 1,
      "job_id": "550e8400-...",
      "date": "2025-01-16",
      "model": "gpt-4",
      "action_type": "buy",
      "symbol": "AAPL",
      "amount": 10,
      "price": 250.50,
      "cash": 7495.00,
      "portfolio_value": 10000.00,
      "daily_profit": 0.00,
      "holdings": [
        {"symbol": "AAPL", "quantity": 10},
        {"symbol": "CASH", "quantity": 7495.00}
      ]
    }
  ],
  "count": 1
}
```

You can see:
- What the AI decided to buy/sell
- Portfolio value and cash balance
- All current holdings

---

## Success! What's Next?

### Run Multiple Days

```bash
curl -X POST http://localhost:8080/simulate/trigger \
  -H "Content-Type: application/json" \
  -d '{
    "start_date": "2025-01-16",
    "end_date": "2025-01-20"
  }'
```

This simulates 5 trading days (weekdays only).

### Run Multiple Models

```bash
curl -X POST http://localhost:8080/simulate/trigger \
  -H "Content-Type: application/json" \
  -d '{
    "start_date": "2025-01-16",
    "models": ["gpt-4", "claude-3.7-sonnet"]
  }'
```

**Note:** Models must be defined and enabled in `configs/default_config.json`.

### Query Specific Results

```bash
# All results for a specific date
curl "http://localhost:8080/results?date=2025-01-16"

# All results for a specific model
curl "http://localhost:8080/results?model=gpt-4"

# Combine filters
curl "http://localhost:8080/results?date=2025-01-16&model=gpt-4"
```

---

## Troubleshooting

### Service won't start

```bash
# Check logs
docker logs ai-trader

# Common issues:
# - Missing API keys in .env
# - Port 8080 already in use
# - Docker not running
```

**Fix port conflicts:**

Edit `.env` and change `API_PORT`:

```bash
API_PORT=8889
```

Then restart:

```bash
docker-compose down
docker-compose up -d
```

### Health check returns error

```bash
# Check if container is running
docker ps | grep ai-trader

# Restart service
docker-compose restart

# Check for errors in logs
docker logs ai-trader | grep -i error
```

### Job stays "pending"

The simulation might still be downloading price data on first run.

```bash
# Watch logs in real-time
docker logs -f ai-trader

# Look for messages like:
# "Downloading missing price data..."
# "Starting simulation for model-day..."
```

First run can take 10-15 minutes while downloading historical price data.

### "No trading dates with complete price data"

This means price data is missing for the requested date range.

**Solution 1:** Try a different date range (recent dates work best)

**Solution 2:** Manually download price data:

```bash
docker exec -it ai-trader bash
cd data
python get_daily_price.py
python merge_jsonl.py
exit
```

---

## Common Commands

```bash
# View logs
docker logs -f ai-trader

# Stop service
docker-compose down

# Start service
docker-compose up -d

# Restart service
docker-compose restart

# Check health
curl http://localhost:8080/health

# Access container shell
docker exec -it ai-trader bash

# View database
docker exec -it ai-trader sqlite3 /app/data/jobs.db
```

---

## Next Steps

- **Full API Reference:** [API_REFERENCE.md](API_REFERENCE.md)
- **Configuration Guide:** [docs/user-guide/configuration.md](docs/user-guide/configuration.md)
- **Integration Examples:** [docs/user-guide/integration-examples.md](docs/user-guide/integration-examples.md)
- **Troubleshooting:** [docs/user-guide/troubleshooting.md](docs/user-guide/troubleshooting.md)

---

## Need Help?

- Check [docs/user-guide/troubleshooting.md](docs/user-guide/troubleshooting.md)
- Review logs: `docker logs ai-trader`
- Open an issue: [GitHub Issues](https://github.com/Xe138/AI-Trader/issues)
