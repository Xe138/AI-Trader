# Environment Variables Reference

Complete list of configuration variables.

---

See [docs/user-guide/configuration.md](../user-guide/configuration.md#environment-variables) for detailed descriptions.

---

## Required

- `OPENAI_API_KEY`
- `ALPHAADVANTAGE_API_KEY`
- `JINA_API_KEY`

---

## Optional

- `API_PORT` (default: 8080)
- `API_HOST` (default: 0.0.0.0)
- `OPENAI_API_BASE`
- `MAX_CONCURRENT_JOBS` (default: 1)
- `MAX_SIMULATION_DAYS` (default: 30)
- `AUTO_DOWNLOAD_PRICE_DATA` (default: true)
- `AGENT_MAX_STEP` (default: 30)
- `VOLUME_PATH` (default: .)
- `MATH_HTTP_PORT` (default: 8000)
- `SEARCH_HTTP_PORT` (default: 8001)
- `TRADE_HTTP_PORT` (default: 8002)
- `GETPRICE_HTTP_PORT` (default: 8003)

### DEFAULT_RESULTS_LOOKBACK_DAYS

**Type:** Integer
**Default:** 30
**Required:** No

Number of calendar days to look back when querying `/results` endpoint without date filters.

**Example:**
```bash
# Default to last 60 days
DEFAULT_RESULTS_LOOKBACK_DAYS=60
```

**Usage:**
When no `start_date` or `end_date` parameters are provided to `/results`, the endpoint returns data from the last N days (ending today).
