# AI-Trader-Server API Reference

Complete reference for the AI-Trader-Server REST API service.

**Base URL:** `http://localhost:8080` (default)

**API Version:** 1.0.0

---

## Endpoints

### POST /simulate/trigger

Trigger a new simulation job for a specified date range and models.

**Supports three operational modes:**
1. **Explicit date range**: Provide both `start_date` and `end_date`
2. **Single date**: Set `start_date` = `end_date`
3. **Resume mode**: Set `start_date` to `null` to continue from each model's last completed date

**Request Body:**

```json
{
  "start_date": "2025-01-16",
  "end_date": "2025-01-17",
  "models": ["gpt-4", "claude-3.7-sonnet"],
  "replace_existing": false
}
```

**Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `start_date` | string \| null | No | Start date in YYYY-MM-DD format. If `null`, enables resume mode (each model continues from its last completed date). Defaults to `null`. |
| `end_date` | string | **Yes** | End date in YYYY-MM-DD format. **Required** - cannot be null or empty. |
| `models` | array[string] | No | Model signatures to run. If omitted or empty array, uses all enabled models from server config. |
| `replace_existing` | boolean | No | If `false` (default), skips already-completed model-days (idempotent). If `true`, re-runs all dates even if previously completed. |

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
- **Date order:** `start_date` must be <= `end_date` (when `start_date` is not null)
- **end_date required:** Cannot be null or empty string
- **Future dates:** Cannot simulate future dates (must be <= today)
- **Date range limit:** Maximum 30 days (configurable via `MAX_SIMULATION_DAYS`)
- **Model signatures:** Must match models defined in server configuration
- **Concurrency:** Only one simulation job can run at a time

**Behavior:**

1. Validates date range and parameters
2. Determines which models to run (from request or server config)
3. **Resume mode** (if `start_date` is null):
   - For each model, queries last completed simulation date
   - If no previous data exists (cold start), uses `end_date` as single-day simulation
   - Otherwise, resumes from day after last completed date
   - Each model can have different resume start dates
4. **Idempotent mode** (if `replace_existing=false`, default):
   - Queries database for already-completed model-day combinations in date range
   - Skips completed model-days, only creates tasks for gaps
   - Returns error if all requested dates are already completed
5. Checks for missing price data in date range
6. Downloads missing data if `AUTO_DOWNLOAD_PRICE_DATA=true` (default)
7. Identifies trading dates with complete price data (all symbols available)
8. Creates job in database with status `pending` (only for model-days that will actually run)
9. Starts background worker thread
10. Returns immediately with job ID

**Examples:**

Single day, single model:
```bash
curl -X POST http://localhost:8080/simulate/trigger \
  -H "Content-Type: application/json" \
  -d '{
    "start_date": "2025-01-16",
    "end_date": "2025-01-16",
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

Resume from last completed date:
```bash
curl -X POST http://localhost:8080/simulate/trigger \
  -H "Content-Type: application/json" \
  -d '{
    "start_date": null,
    "end_date": "2025-01-31",
    "models": ["gpt-4"]
  }'
```

Idempotent simulation (skip already-completed dates):
```bash
curl -X POST http://localhost:8080/simulate/trigger \
  -H "Content-Type: application/json" \
  -d '{
    "start_date": "2025-01-16",
    "end_date": "2025-01-20",
    "models": ["gpt-4"],
    "replace_existing": false
  }'
```

Re-run existing dates (force replace):
```bash
curl -X POST http://localhost:8080/simulate/trigger \
  -H "Content-Type: application/json" \
  -d '{
    "start_date": "2025-01-16",
    "end_date": "2025-01-20",
    "models": ["gpt-4"],
    "replace_existing": true
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
| `warnings` | array[string] | Optional array of non-fatal warning messages |

**Job Status Values:**

| Status | Description |
|--------|-------------|
| `pending` | Job created, waiting to start |
| `downloading_data` | Preparing price data (downloading if needed) |
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

**Warnings Field:**

The optional `warnings` array contains non-fatal warning messages about the job execution:

- **Rate limit warnings**: Price data download hit API rate limits
- **Skipped dates**: Some dates couldn't be processed due to incomplete price data
- **Other issues**: Non-fatal problems that don't prevent job completion

**Example response with warnings:**

```json
{
  "job_id": "019a426b-1234-5678-90ab-cdef12345678",
  "status": "completed",
  "progress": {
    "total_model_days": 10,
    "completed": 8,
    "failed": 0,
    "pending": 0
  },
  "warnings": [
    "Rate limit reached - downloaded 12/15 symbols",
    "Skipped 2 dates due to incomplete price data: ['2025-10-02', '2025-10-05']"
  ]
}
```

If no warnings occurred, the field will be `null` or omitted.

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

Get trading results grouped by day with daily P&L metrics and AI reasoning.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `job_id` | string | No | Filter by job UUID |
| `date` | string | No | Filter by trading date (YYYY-MM-DD) |
| `model` | string | No | Filter by model signature |
| `reasoning` | string | No | Include AI reasoning: `none` (default), `summary`, or `full` |

**Response (200 OK) - Default (no reasoning):**

```json
{
  "count": 2,
  "results": [
    {
      "date": "2025-01-15",
      "model": "gpt-4",
      "job_id": "550e8400-e29b-41d4-a716-446655440000",
      "starting_position": {
        "holdings": [],
        "cash": 10000.0,
        "portfolio_value": 10000.0
      },
      "daily_metrics": {
        "profit": 0.0,
        "return_pct": 0.0,
        "days_since_last_trading": 0
      },
      "trades": [
        {
          "action_type": "buy",
          "symbol": "AAPL",
          "quantity": 10,
          "price": 150.0,
          "created_at": "2025-01-15T14:30:00Z"
        }
      ],
      "final_position": {
        "holdings": [
          {"symbol": "AAPL", "quantity": 10}
        ],
        "cash": 8500.0,
        "portfolio_value": 10000.0
      },
      "metadata": {
        "total_actions": 1,
        "session_duration_seconds": 45.2,
        "completed_at": "2025-01-15T14:31:00Z"
      },
      "reasoning": null
    },
    {
      "date": "2025-01-16",
      "model": "gpt-4",
      "job_id": "550e8400-e29b-41d4-a716-446655440000",
      "starting_position": {
        "holdings": [
          {"symbol": "AAPL", "quantity": 10}
        ],
        "cash": 8500.0,
        "portfolio_value": 10100.0
      },
      "daily_metrics": {
        "profit": 100.0,
        "return_pct": 1.0,
        "days_since_last_trading": 1
      },
      "trades": [
        {
          "action_type": "buy",
          "symbol": "MSFT",
          "quantity": 5,
          "price": 200.0,
          "created_at": "2025-01-16T14:30:00Z"
        }
      ],
      "final_position": {
        "holdings": [
          {"symbol": "AAPL", "quantity": 10},
          {"symbol": "MSFT", "quantity": 5}
        ],
        "cash": 7500.0,
        "portfolio_value": 10100.0
      },
      "metadata": {
        "total_actions": 1,
        "session_duration_seconds": 52.1,
        "completed_at": "2025-01-16T14:31:00Z"
      },
      "reasoning": null
    }
  ]
}
```

**Response (200 OK) - With Summary Reasoning:**

```json
{
  "count": 1,
  "results": [
    {
      "date": "2025-01-15",
      "model": "gpt-4",
      "job_id": "550e8400-e29b-41d4-a716-446655440000",
      "starting_position": {
        "holdings": [],
        "cash": 10000.0,
        "portfolio_value": 10000.0
      },
      "daily_metrics": {
        "profit": 0.0,
        "return_pct": 0.0,
        "days_since_last_trading": 0
      },
      "trades": [
        {
          "action_type": "buy",
          "symbol": "AAPL",
          "quantity": 10,
          "price": 150.0,
          "created_at": "2025-01-15T14:30:00Z"
        }
      ],
      "final_position": {
        "holdings": [
          {"symbol": "AAPL", "quantity": 10}
        ],
        "cash": 8500.0,
        "portfolio_value": 10000.0
      },
      "metadata": {
        "total_actions": 1,
        "session_duration_seconds": 45.2,
        "completed_at": "2025-01-15T14:31:00Z"
      },
      "reasoning": "Analyzed AAPL earnings report showing strong Q4 results. Bought 10 shares at $150 based on positive revenue guidance and expanding margins."
    }
  ]
}
```

**Response (200 OK) - With Full Reasoning:**

```json
{
  "count": 1,
  "results": [
    {
      "date": "2025-01-15",
      "model": "gpt-4",
      "job_id": "550e8400-e29b-41d4-a716-446655440000",
      "starting_position": {
        "holdings": [],
        "cash": 10000.0,
        "portfolio_value": 10000.0
      },
      "daily_metrics": {
        "profit": 0.0,
        "return_pct": 0.0,
        "days_since_last_trading": 0
      },
      "trades": [
        {
          "action_type": "buy",
          "symbol": "AAPL",
          "quantity": 10,
          "price": 150.0,
          "created_at": "2025-01-15T14:30:00Z"
        }
      ],
      "final_position": {
        "holdings": [
          {"symbol": "AAPL", "quantity": 10}
        ],
        "cash": 8500.0,
        "portfolio_value": 10000.0
      },
      "metadata": {
        "total_actions": 1,
        "session_duration_seconds": 45.2,
        "completed_at": "2025-01-15T14:31:00Z"
      },
      "reasoning": [
        {
          "role": "user",
          "content": "You are a trading agent. Current date: 2025-01-15..."
        },
        {
          "role": "assistant",
          "content": "I'll analyze market conditions for AAPL..."
        },
        {
          "role": "tool",
          "name": "search",
          "content": "AAPL Q4 earnings beat expectations..."
        },
        {
          "role": "assistant",
          "content": "Based on positive earnings, I'll buy AAPL..."
        }
      ]
    }
  ]
}
```

**Response Fields:**

**Top-level:**
| Field | Type | Description |
|-------|------|-------------|
| `count` | integer | Number of trading days returned |
| `results` | array[object] | Array of day-level trading results |

**Day-level fields:**
| Field | Type | Description |
|-------|------|-------------|
| `date` | string | Trading date (YYYY-MM-DD) |
| `model` | string | Model signature |
| `job_id` | string | Simulation job UUID |
| `starting_position` | object | Portfolio state at start of day |
| `daily_metrics` | object | Daily performance metrics |
| `trades` | array[object] | All trades executed during the day |
| `final_position` | object | Portfolio state at end of day |
| `metadata` | object | Session metadata |
| `reasoning` | null\|string\|array | AI reasoning (based on `reasoning` parameter) |

**starting_position fields:**
| Field | Type | Description |
|-------|------|-------------|
| `holdings` | array[object] | Stock positions at start of day (from previous day's ending) |
| `cash` | float | Cash balance at start of day |
| `portfolio_value` | float | Total portfolio value at start (cash + holdings valued at current prices) |

**daily_metrics fields:**
| Field | Type | Description |
|-------|------|-------------|
| `profit` | float | Dollar amount gained/lost from previous close (portfolio appreciation/depreciation) |
| `return_pct` | float | Percentage return from previous close |
| `days_since_last_trading` | integer | Number of calendar days since last trading day (1=normal, 3=weekend, 0=first day) |

**trades fields:**
| Field | Type | Description |
|-------|------|-------------|
| `action_type` | string | Trade type: `buy`, `sell`, or `no_trade` |
| `symbol` | string\|null | Stock symbol (null for `no_trade`) |
| `quantity` | integer\|null | Number of shares (null for `no_trade`) |
| `price` | float\|null | Execution price per share (null for `no_trade`) |
| `created_at` | string | ISO 8601 timestamp of trade execution |

**final_position fields:**
| Field | Type | Description |
|-------|------|-------------|
| `holdings` | array[object] | Stock positions at end of day |
| `cash` | float | Cash balance at end of day |
| `portfolio_value` | float | Total portfolio value at end (cash + holdings valued at closing prices) |

**metadata fields:**
| Field | Type | Description |
|-------|------|-------------|
| `total_actions` | integer | Number of trades executed during the day |
| `session_duration_seconds` | float\|null | AI session duration in seconds |
| `completed_at` | string\|null | ISO 8601 timestamp of session completion |

**holdings object:**
| Field | Type | Description |
|-------|------|-------------|
| `symbol` | string | Stock symbol |
| `quantity` | integer | Number of shares held |

**reasoning field:**
- `null` when `reasoning=none` (default) - no reasoning included
- `string` when `reasoning=summary` - AI-generated 2-3 sentence summary of trading strategy
- `array` when `reasoning=full` - Complete conversation log with all messages, tool calls, and responses

**Daily P&L Calculation:**

Daily profit/loss is calculated by valuing the previous day's ending holdings at current day's opening prices:

1. **First trading day**: `daily_profit = 0`, `daily_return_pct = 0` (no previous holdings to appreciate/depreciate)
2. **Subsequent days**:
   - Value yesterday's ending holdings at today's opening prices
   - `daily_profit = today_portfolio_value - yesterday_portfolio_value`
   - `daily_return_pct = (daily_profit / yesterday_portfolio_value) * 100`

This accurately captures portfolio appreciation from price movements, not just trading decisions.

**Weekend Gap Handling:**

The system correctly handles multi-day gaps (weekends, holidays):
- `days_since_last_trading` shows actual calendar days elapsed (e.g., 3 for Monday following Friday)
- Daily P&L reflects cumulative price changes over the gap period
- Holdings chain remains consistent (Monday starts with Friday's ending positions)

**Examples:**

All results for a specific job (no reasoning):
```bash
curl "http://localhost:8080/results?job_id=550e8400-e29b-41d4-a716-446655440000"
```

Results for a specific date with summary reasoning:
```bash
curl "http://localhost:8080/results?date=2025-01-16&reasoning=summary"
```

Results for a specific model with full reasoning:
```bash
curl "http://localhost:8080/results?model=gpt-4&reasoning=full"
```

Combine filters:
```bash
curl "http://localhost:8080/results?job_id=550e8400-e29b-41d4-a716-446655440000&date=2025-01-16&model=gpt-4&reasoning=summary"
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

## Deployment Mode

All API responses include a `deployment_mode` field indicating whether the service is running in production or development mode.

### Response Format

```json
{
  "job_id": "abc123",
  "status": "completed",
  "deployment_mode": "DEV",
  "is_dev_mode": true,
  "preserve_dev_data": false
}
```

**Fields:**
- `deployment_mode`: "PROD" or "DEV"
- `is_dev_mode`: Boolean flag
- `preserve_dev_data`: Null in PROD, boolean in DEV

### DEV Mode Behavior

When `DEPLOYMENT_MODE=DEV` is set:
- No AI API calls (mock responses)
- Separate dev database (`jobs_dev.db`)
- Separate data directory (`dev_agent_data/`)
- Database reset on startup (unless PRESERVE_DEV_DATA=true)

**Health Check Example:**

```bash
curl http://localhost:8080/health
```

Response in DEV mode:
```json
{
  "status": "healthy",
  "database": "connected",
  "timestamp": "2025-01-16T10:00:00Z",
  "deployment_mode": "DEV",
  "is_dev_mode": true,
  "preserve_dev_data": false
}
```

### Use Cases

- **Testing:** Validate orchestration without AI API costs
- **CI/CD:** Automated testing in pipelines
- **Development:** Rapid iteration on system logic
- **Configuration validation:** Test settings before production

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

Or use resume mode:
```bash
RESPONSE=$(curl -X POST http://localhost:8080/simulate/trigger \
  -H "Content-Type: application/json" \
  -d '{"start_date": null, "end_date": "2025-01-31", "models": ["gpt-4"]}')

JOB_ID=$(echo $RESPONSE | jq -r '.job_id')
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

**Option 1: Resume mode (recommended)**
```bash
#!/bin/bash
# daily_simulation.sh - Resume from last completed date

# Calculate today's date
TODAY=$(date +%Y-%m-%d)

# Trigger simulation in resume mode
curl -X POST http://localhost:8080/simulate/trigger \
  -H "Content-Type: application/json" \
  -d "{\"start_date\": null, \"end_date\": \"$TODAY\", \"models\": [\"gpt-4\"]}"
```

**Option 2: Explicit yesterday's date**
```bash
#!/bin/bash
# daily_simulation.sh - Run specific date

# Calculate yesterday's date
DATE=$(date -d "yesterday" +%Y-%m-%d)

# Trigger simulation
curl -X POST http://localhost:8080/simulate/trigger \
  -H "Content-Type: application/json" \
  -d "{\"start_date\": \"$DATE\", \"end_date\": \"$DATE\", \"models\": [\"gpt-4\"]}"
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

### Configuration Override System

**Default config:** `/app/configs/default_config.json` (baked into image)

**Custom config:** `/app/user-configs/config.json` (optional, via volume mount)

**Merge behavior:**
- Custom config sections completely replace default sections (root-level merge)
- If no custom config exists, defaults are used
- Validation occurs at container startup (before API starts)
- Invalid config causes immediate exit with detailed error message

**Example custom config** (overrides models only):
```json
{
  "models": [
    {"name": "gpt-5", "basemodel": "openai/gpt-5", "signature": "gpt-5", "enabled": true}
  ]
}
```

All other sections (`agent_config`, `log_config`, etc.) inherited from default.

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

    def trigger_simulation(self, end_date, start_date=None, models=None, replace_existing=False):
        """
        Trigger a simulation job.

        Args:
            end_date: End date (YYYY-MM-DD), required
            start_date: Start date (YYYY-MM-DD) or None for resume mode
            models: List of model signatures or None for all enabled models
            replace_existing: If False, skip already-completed dates (idempotent)
        """
        payload = {"end_date": end_date, "replace_existing": replace_existing}
        if start_date is not None:
            payload["start_date"] = start_date
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

    def get_reasoning(self, job_id=None, date=None, model=None, include_full_conversation=False):
        """Query reasoning logs with optional filters."""
        params = {}
        if job_id:
            params["job_id"] = job_id
        if date:
            params["date"] = date
        if model:
            params["model"] = model
        if include_full_conversation:
            params["include_full_conversation"] = "true"

        response = requests.get(f"{self.base_url}/reasoning", params=params)
        response.raise_for_status()
        return response.json()

# Usage examples
client = AITraderServerClient()

# Single day simulation
job = client.trigger_simulation(end_date="2025-01-16", start_date="2025-01-16", models=["gpt-4"])

# Date range simulation
job = client.trigger_simulation(end_date="2025-01-20", start_date="2025-01-16")

# Resume mode (continue from last completed)
job = client.trigger_simulation(end_date="2025-01-31", models=["gpt-4"])

# Wait for completion and get results
result = client.wait_for_completion(job["job_id"])
results = client.get_results(job_id=job["job_id"])

# Get reasoning logs (summaries only)
reasoning = client.get_reasoning(job_id=job["job_id"])

# Get reasoning logs with full conversation
full_reasoning = client.get_reasoning(
    job_id=job["job_id"],
    date="2025-01-16",
    include_full_conversation=True
)
```

### TypeScript/JavaScript

```typescript
class AITraderServerClient {
  constructor(private baseUrl: string = "http://localhost:8080") {}

  async triggerSimulation(
    endDate: string,
    options: {
      startDate?: string | null;
      models?: string[];
      replaceExisting?: boolean;
    } = {}
  ) {
    const body: any = {
      end_date: endDate,
      replace_existing: options.replaceExisting ?? false
    };
    if (options.startDate !== undefined) {
      body.start_date = options.startDate;
    }
    if (options.models) {
      body.models = options.models;
    }

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

  async getReasoning(filters: {
    jobId?: string;
    date?: string;
    model?: string;
    includeFullConversation?: boolean;
  } = {}) {
    const params = new URLSearchParams();
    if (filters.jobId) params.set("job_id", filters.jobId);
    if (filters.date) params.set("date", filters.date);
    if (filters.model) params.set("model", filters.model);
    if (filters.includeFullConversation) params.set("include_full_conversation", "true");

    const response = await fetch(
      `${this.baseUrl}/reasoning?${params.toString()}`
    );
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  }
}

// Usage examples
const client = new AITraderServerClient();

// Single day simulation
const job1 = await client.triggerSimulation("2025-01-16", {
  startDate: "2025-01-16",
  models: ["gpt-4"]
});

// Date range simulation
const job2 = await client.triggerSimulation("2025-01-20", {
  startDate: "2025-01-16"
});

// Resume mode (continue from last completed)
const job3 = await client.triggerSimulation("2025-01-31", {
  startDate: null,
  models: ["gpt-4"]
});

// Wait for completion and get results
const result = await client.waitForCompletion(job1.job_id);
const results = await client.getResults({ jobId: job1.job_id });

// Get reasoning logs (summaries only)
const reasoning = await client.getReasoning({ jobId: job1.job_id });

// Get reasoning logs with full conversation
const fullReasoning = await client.getReasoning({
  jobId: job1.job_id,
  date: "2025-01-16",
  includeFullConversation: true
});
```
