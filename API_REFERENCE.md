# AI-Trader-Server API Reference

Complete reference for the AI-Trader-Server REST API service.

**Base URL:** `http://localhost:8080` (default)

**API Version:** 1.0.0

---

## Endpoints

### POST /simulate/trigger

Trigger a new simulation job for a specified date range and models.

**Request Body:**

```json
{
  "start_date": "2025-01-16",
  "end_date": "2025-01-17",
  "models": ["gpt-4", "claude-3.7-sonnet"]
}
```

**Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `start_date` | string | Yes | Start date in YYYY-MM-DD format |
| `end_date` | string | No | End date in YYYY-MM-DD format. If omitted, simulates single day (uses `start_date`) |
| `models` | array[string] | No | Model signatures to run. If omitted, uses all enabled models from server config |

**Response (200 OK):**

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "total_model_days": 4,
  "message": "Simulation job created with 2 trading dates"
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `job_id` | string | Unique UUID for this simulation job |
| `status` | string | Job status: `pending`, `running`, `completed`, `partial`, or `failed` |
| `total_model_days` | integer | Total number of model-day combinations to execute |
| `message` | string | Human-readable status message |

**Error Responses:**

**400 Bad Request** - Invalid parameters or validation failure
```json
{
  "detail": "Invalid date format: 2025-1-16. Expected YYYY-MM-DD"
}
```

**400 Bad Request** - Another job is already running
```json
{
  "detail": "Another simulation job is already running or pending. Please wait for it to complete."
}
```

**500 Internal Server Error** - Server configuration issue
```json
{
  "detail": "Server configuration file not found: configs/default_config.json"
}
```

**503 Service Unavailable** - Price data download failed
```json
{
  "detail": "Failed to download any price data. Check ALPHAADVANTAGE_API_KEY."
}
```

**Validation Rules:**

- **Date format:** Must be YYYY-MM-DD
- **Date validity:** Must be valid calendar dates
- **Date order:** `start_date` must be <= `end_date`
- **Future dates:** Cannot simulate future dates (must be <= today)
- **Date range limit:** Maximum 30 days (configurable via `MAX_SIMULATION_DAYS`)
- **Model signatures:** Must match models defined in server configuration
- **Concurrency:** Only one simulation job can run at a time

**Behavior:**

1. Validates date range and parameters
2. Determines which models to run (from request or server config)
3. Checks for missing price data in date range
4. Downloads missing data if `AUTO_DOWNLOAD_PRICE_DATA=true` (default)
5. Identifies trading dates with complete price data (all symbols available)
6. Creates job in database with status `pending`
7. Starts background worker thread
8. Returns immediately with job ID

**Examples:**

Single day, single model:
```bash
curl -X POST http://localhost:8080/simulate/trigger \
  -H "Content-Type: application/json" \
  -d '{
    "start_date": "2025-01-16",
    "models": ["gpt-4"]
  }'
```

Date range, all enabled models:
```bash
curl -X POST http://localhost:8080/simulate/trigger \
  -H "Content-Type: application/json" \
  -d '{
    "start_date": "2025-01-16",
    "end_date": "2025-01-20"
  }'
```

---

### GET /simulate/status/{job_id}

Get status and progress of a simulation job.

**URL Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `job_id` | string | Job UUID from trigger response |

**Response (200 OK):**

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
  "started_at": "2025-01-16T10:00:05Z",
  "completed_at": null,
  "total_duration_seconds": null,
  "error": null,
  "details": [
    {
      "model_signature": "gpt-4",
      "trading_date": "2025-01-16",
      "status": "completed",
      "start_time": "2025-01-16T10:00:05Z",
      "end_time": "2025-01-16T10:05:23Z",
      "duration_seconds": 318.5,
      "error": null
    },
    {
      "model_signature": "claude-3.7-sonnet",
      "trading_date": "2025-01-16",
      "status": "completed",
      "start_time": "2025-01-16T10:05:24Z",
      "end_time": "2025-01-16T10:10:12Z",
      "duration_seconds": 288.0,
      "error": null
    },
    {
      "model_signature": "gpt-4",
      "trading_date": "2025-01-17",
      "status": "running",
      "start_time": "2025-01-16T10:10:13Z",
      "end_time": null,
      "duration_seconds": null,
      "error": null
    },
    {
      "model_signature": "claude-3.7-sonnet",
      "trading_date": "2025-01-17",
      "status": "pending",
      "start_time": null,
      "end_time": null,
      "duration_seconds": null,
      "error": null
    }
  ]
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `job_id` | string | Job UUID |
| `status` | string | Overall job status |
| `progress` | object | Progress summary |
| `progress.total_model_days` | integer | Total model-day combinations |
| `progress.completed` | integer | Successfully completed model-days |
| `progress.failed` | integer | Failed model-days |
| `progress.pending` | integer | Not yet started model-days |
| `date_range` | array[string] | Trading dates in this job |
| `models` | array[string] | Model signatures in this job |
| `created_at` | string | ISO 8601 timestamp when job was created |
| `started_at` | string | ISO 8601 timestamp when execution began |
| `completed_at` | string | ISO 8601 timestamp when job finished |
| `total_duration_seconds` | float | Total execution time in seconds |
| `error` | string | Error message if job failed |
| `details` | array[object] | Per model-day execution details |

**Job Status Values:**

| Status | Description |
|--------|-------------|
| `pending` | Job created, waiting to start |
| `running` | Job currently executing |
| `completed` | All model-days completed successfully |
| `partial` | Some model-days completed, some failed |
| `failed` | All model-days failed |

**Model-Day Status Values:**

| Status | Description |
|--------|-------------|
| `pending` | Not started yet |
| `running` | Currently executing |
| `completed` | Finished successfully |
| `failed` | Execution failed (see `error` field) |

**Error Response:**

**404 Not Found** - Job doesn't exist
```json
{
  "detail": "Job 550e8400-e29b-41d4-a716-446655440000 not found"
}
```

**Example:**

```bash
curl http://localhost:8080/simulate/status/550e8400-e29b-41d4-a716-446655440000
```

**Polling Recommendation:**

Poll every 10-30 seconds until `status` is `completed`, `partial`, or `failed`.

---

### GET /results

Query simulation results with optional filters.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `job_id` | string | No | Filter by job UUID |
| `date` | string | No | Filter by trading date (YYYY-MM-DD) |
| `model` | string | No | Filter by model signature |

**Response (200 OK):**

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
      "created_at": "2025-01-16T10:05:23Z",
      "holdings": [
        {"symbol": "AAPL", "quantity": 10},
        {"symbol": "CASH", "quantity": 7495.00}
      ]
    },
    {
      "id": 2,
      "job_id": "550e8400-e29b-41d4-a716-446655440000",
      "date": "2025-01-16",
      "model": "gpt-4",
      "action_id": 2,
      "action_type": "buy",
      "symbol": "MSFT",
      "amount": 5,
      "price": 380.20,
      "cash": 5594.00,
      "portfolio_value": 10105.00,
      "daily_profit": 105.00,
      "daily_return_pct": 1.05,
      "created_at": "2025-01-16T10:05:23Z",
      "holdings": [
        {"symbol": "AAPL", "quantity": 10},
        {"symbol": "MSFT", "quantity": 5},
        {"symbol": "CASH", "quantity": 5594.00}
      ]
    }
  ],
  "count": 2
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `results` | array[object] | Array of position records |
| `count` | integer | Number of results returned |

**Position Record Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `id` | integer | Unique position record ID |
| `job_id` | string | Job UUID this belongs to |
| `date` | string | Trading date (YYYY-MM-DD) |
| `model` | string | Model signature |
| `action_id` | integer | Action sequence number (1, 2, 3...) for this model-day |
| `action_type` | string | Action taken: `buy`, `sell`, or `hold` |
| `symbol` | string | Stock symbol traded (or null for `hold`) |
| `amount` | integer | Quantity traded (or null for `hold`) |
| `price` | float | Price per share (or null for `hold`) |
| `cash` | float | Cash balance after this action |
| `portfolio_value` | float | Total portfolio value (cash + holdings) |
| `daily_profit` | float | Profit/loss for this trading day |
| `daily_return_pct` | float | Return percentage for this day |
| `created_at` | string | ISO 8601 timestamp when recorded |
| `holdings` | array[object] | Current holdings after this action |

**Holdings Object:**

| Field | Type | Description |
|-------|------|-------------|
| `symbol` | string | Stock symbol or "CASH" |
| `quantity` | float | Shares owned (or cash amount) |

**Examples:**

All results for a specific job:
```bash
curl "http://localhost:8080/results?job_id=550e8400-e29b-41d4-a716-446655440000"
```

Results for a specific date:
```bash
curl "http://localhost:8080/results?date=2025-01-16"
```

Results for a specific model:
```bash
curl "http://localhost:8080/results?model=gpt-4"
```

Combine filters:
```bash
curl "http://localhost:8080/results?job_id=550e8400-e29b-41d4-a716-446655440000&date=2025-01-16&model=gpt-4"
```

---

### GET /health

Health check endpoint for monitoring and orchestration services.

**Response (200 OK):**

```json
{
  "status": "healthy",
  "database": "connected",
  "timestamp": "2025-01-16T10:00:00Z"
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `status` | string | Overall service health: `healthy` or `unhealthy` |
| `database` | string | Database connection status: `connected` or `disconnected` |
| `timestamp` | string | ISO 8601 timestamp of health check |

**Example:**

```bash
curl http://localhost:8080/health
```

**Usage:**

- Docker health checks: `HEALTHCHECK CMD curl -f http://localhost:8080/health`
- Monitoring systems: Poll every 30-60 seconds
- Orchestration services: Verify availability before triggering simulations

---

## Common Workflows

### Trigger and Monitor a Simulation

1. **Trigger simulation:**
```bash
RESPONSE=$(curl -X POST http://localhost:8080/simulate/trigger \
  -H "Content-Type: application/json" \
  -d '{"start_date": "2025-01-16", "end_date": "2025-01-17", "models": ["gpt-4"]}')

JOB_ID=$(echo $RESPONSE | jq -r '.job_id')
echo "Job ID: $JOB_ID"
```

2. **Poll for completion:**
```bash
while true; do
  STATUS=$(curl -s http://localhost:8080/simulate/status/$JOB_ID | jq -r '.status')
  echo "Status: $STATUS"

  if [[ "$STATUS" == "completed" ]] || [[ "$STATUS" == "partial" ]] || [[ "$STATUS" == "failed" ]]; then
    break
  fi

  sleep 10
done
```

3. **Retrieve results:**
```bash
curl "http://localhost:8080/results?job_id=$JOB_ID" | jq '.'
```

### Scheduled Daily Simulations

Use a scheduler (cron, Airflow, etc.) to trigger simulations:

```bash
#!/bin/bash
# daily_simulation.sh

# Calculate yesterday's date
DATE=$(date -d "yesterday" +%Y-%m-%d)

# Trigger simulation
curl -X POST http://localhost:8080/simulate/trigger \
  -H "Content-Type: application/json" \
  -d "{\"start_date\": \"$DATE\", \"models\": [\"gpt-4\"]}"
```

Add to crontab:
```
0 6 * * * /path/to/daily_simulation.sh
```

---

## Error Handling

All endpoints return consistent error responses with HTTP status codes and detail messages.

### Common Error Codes

| Code | Meaning | Common Causes |
|------|---------|---------------|
| 400 | Bad Request | Invalid date format, invalid parameters, concurrent job running |
| 404 | Not Found | Job ID doesn't exist |
| 500 | Internal Server Error | Server misconfiguration, missing config file |
| 503 | Service Unavailable | Price data download failed, database unavailable |

### Error Response Format

```json
{
  "detail": "Human-readable error message"
}
```

### Retry Recommendations

- **400 errors:** Fix request parameters, don't retry
- **404 errors:** Verify job ID, don't retry
- **500 errors:** Check server logs, investigate before retrying
- **503 errors:** Retry with exponential backoff (wait 1s, 2s, 4s, etc.)

---

## Rate Limits and Constraints

### Concurrency

- **Maximum concurrent jobs:** 1 (configurable via `MAX_CONCURRENT_JOBS`)
- **Attempting to start a second job returns:** 400 Bad Request

### Date Range Limits

- **Maximum date range:** 30 days (configurable via `MAX_SIMULATION_DAYS`)
- **Attempting longer range returns:** 400 Bad Request

### Price Data

- **Alpha Vantage API rate limit:** 5 requests/minute (free tier), 75 requests/minute (premium)
- **Automatic download:** Enabled by default (`AUTO_DOWNLOAD_PRICE_DATA=true`)
- **Behavior when rate limited:** Partial data downloaded, simulation continues with available dates

---

## Data Persistence

All simulation data is stored in SQLite database at `data/jobs.db`.

### Database Tables

- **jobs** - Job metadata and status
- **job_details** - Per model-day execution details
- **positions** - Trading position records
- **holdings** - Portfolio holdings breakdown
- **reasoning_logs** - AI decision reasoning (if enabled)
- **tool_usage** - MCP tool usage statistics
- **price_data** - Historical price data cache
- **price_coverage** - Data availability tracking

### Data Retention

- Job data persists indefinitely by default
- Results can be queried at any time after job completion
- Manual cleanup: Delete rows from `jobs` table (cascades to related tables)

---

## Configuration

API behavior is controlled via environment variables and server configuration file.

### Environment Variables

See [docs/reference/environment-variables.md](docs/reference/environment-variables.md) for complete reference.

**Key variables:**

- `API_PORT` - API server port (default: 8080)
- `MAX_CONCURRENT_JOBS` - Maximum concurrent simulations (default: 1)
- `MAX_SIMULATION_DAYS` - Maximum date range (default: 30)
- `AUTO_DOWNLOAD_PRICE_DATA` - Auto-download missing data (default: true)
- `ALPHAADVANTAGE_API_KEY` - Alpha Vantage API key (required)

### Server Configuration File

Server loads model definitions from configuration file (default: `configs/default_config.json`).

**Example config:**
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
      "enabled": true
    }
  ],
  "agent_config": {
    "max_steps": 30,
    "initial_cash": 10000.0
  }
}
```

**Model fields:**

- `signature` - Unique identifier used in API requests
- `enabled` - Whether model runs when no models specified in request
- `basemodel` - Model identifier for AI provider
- `openai_base_url` - Optional custom API endpoint
- `openai_api_key` - Optional model-specific API key

---

## OpenAPI / Swagger Documentation

Interactive API documentation available at:

- Swagger UI: `http://localhost:8080/docs`
- ReDoc: `http://localhost:8080/redoc`
- OpenAPI JSON: `http://localhost:8080/openapi.json`

---

## Client Libraries

### Python

```python
import requests
import time

class AITraderServerClient:
    def __init__(self, base_url="http://localhost:8080"):
        self.base_url = base_url

    def trigger_simulation(self, start_date, end_date=None, models=None):
        """Trigger a simulation job."""
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

    def get_status(self, job_id):
        """Get job status."""
        response = requests.get(f"{self.base_url}/simulate/status/{job_id}")
        response.raise_for_status()
        return response.json()

    def wait_for_completion(self, job_id, poll_interval=10):
        """Poll until job completes."""
        while True:
            status = self.get_status(job_id)
            if status["status"] in ["completed", "partial", "failed"]:
                return status
            time.sleep(poll_interval)

    def get_results(self, job_id=None, date=None, model=None):
        """Query results with optional filters."""
        params = {}
        if job_id:
            params["job_id"] = job_id
        if date:
            params["date"] = date
        if model:
            params["model"] = model

        response = requests.get(f"{self.base_url}/results", params=params)
        response.raise_for_status()
        return response.json()

# Usage
client = AITraderServerClient()
job = client.trigger_simulation("2025-01-16", models=["gpt-4"])
result = client.wait_for_completion(job["job_id"])
results = client.get_results(job_id=job["job_id"])
```

### TypeScript/JavaScript

```typescript
class AITraderServerClient {
  constructor(private baseUrl: string = "http://localhost:8080") {}

  async triggerSimulation(
    startDate: string,
    endDate?: string,
    models?: string[]
  ) {
    const body: any = { start_date: startDate };
    if (endDate) body.end_date = endDate;
    if (models) body.models = models;

    const response = await fetch(`${this.baseUrl}/simulate/trigger`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    });

    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  }

  async getStatus(jobId: string) {
    const response = await fetch(
      `${this.baseUrl}/simulate/status/${jobId}`
    );
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  }

  async waitForCompletion(jobId: string, pollInterval: number = 10000) {
    while (true) {
      const status = await this.getStatus(jobId);
      if (["completed", "partial", "failed"].includes(status.status)) {
        return status;
      }
      await new Promise(resolve => setTimeout(resolve, pollInterval));
    }
  }

  async getResults(filters: {
    jobId?: string;
    date?: string;
    model?: string;
  } = {}) {
    const params = new URLSearchParams();
    if (filters.jobId) params.set("job_id", filters.jobId);
    if (filters.date) params.set("date", filters.date);
    if (filters.model) params.set("model", filters.model);

    const response = await fetch(
      `${this.baseUrl}/results?${params.toString()}`
    );
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  }
}

// Usage
const client = new AITraderServerClient();
const job = await client.triggerSimulation("2025-01-16", null, ["gpt-4"]);
const result = await client.waitForCompletion(job.job_id);
const results = await client.getResults({ jobId: job.job_id });
```
