# Data Cache Reuse Design

**Date:** 2025-10-30
**Status:** Approved

## Problem Statement

Docker containers currently fetch all 103 NASDAQ 100 tickers from Alpha Vantage on every startup, even when price data is volume-mounted and already cached in `./data`. This causes:
- Slow startup times (103 API calls)
- Unnecessary API quota consumption
- Rate limit risks during frequent development iterations

## Solution Overview

Implement staleness-based data refresh with configurable age threshold. Container checks all `daily_prices_*.json` files and only refetches if any file is missing or older than `MAX_DATA_AGE_DAYS`.

## Design Decisions

### Architecture Choice
**Selected:** Check all `daily_prices_*.json` files individually
**Rationale:** Ensures data integrity by detecting partial/missing files, not just stale merged data

### Implementation Location
**Selected:** Bash wrapper logic in `entrypoint.sh`
**Rationale:** Keeps data fetching scripts unchanged, adds orchestration at container startup layer

### Staleness Threshold
**Selected:** Configurable via `MAX_DATA_AGE_DAYS` environment variable (default: 7 days)
**Rationale:** Balances freshness with API usage; flexible for different use cases (development vs production)

## Technical Design

### Components

#### 1. Staleness Check Function
Location: `entrypoint.sh` (after environment validation, before data fetch)

```bash
should_refresh_data() {
    MAX_AGE=${MAX_DATA_AGE_DAYS:-7}

    # Check if at least one price file exists
    if ! ls /app/data/daily_prices_*.json >/dev/null 2>&1; then
        echo "📭 No price data found"
        return 0  # Need refresh
    fi

    # Find any files older than MAX_AGE days
    STALE_COUNT=$(find /app/data -name "daily_prices_*.json" -mtime +$MAX_AGE | wc -l)
    TOTAL_COUNT=$(ls /app/data/daily_prices_*.json 2>/dev/null | wc -l)

    if [ $STALE_COUNT -gt 0 ]; then
        echo "📅 Found $STALE_COUNT stale files (>$MAX_AGE days old)"
        return 0  # Need refresh
    fi

    echo "✅ All $TOTAL_COUNT price files are fresh (<$MAX_AGE days old)"
    return 1  # Skip refresh
}
```

**Logic:**
- Uses `find -mtime +N` to detect files modified more than N days ago
- Returns shell exit codes: 0 (refresh needed), 1 (skip refresh)
- Logs informative messages for debugging

#### 2. Conditional Data Fetch
Location: `entrypoint.sh` lines 40-46 (replace existing unconditional fetch)

```bash
# Step 1: Data preparation (conditional)
echo "📊 Checking price data freshness..."

if should_refresh_data; then
    echo "🔄 Fetching and merging price data..."
    cd /app/data
    python /app/scripts/get_daily_price.py
    python /app/scripts/merge_jsonl.py
    cd /app
else
    echo "⏭️  Skipping data fetch (using cached data)"
fi
```

#### 3. Environment Configuration
**docker-compose.yml:**
```yaml
environment:
  - MAX_DATA_AGE_DAYS=${MAX_DATA_AGE_DAYS:-7}
```

**.env.example:**
```bash
# Data Refresh Configuration
MAX_DATA_AGE_DAYS=7  # Refresh price data older than N days (0=always refresh)
```

### Data Flow

1. **Container Startup** → entrypoint.sh begins execution
2. **Environment Validation** → Check required API keys (existing logic)
3. **Staleness Check** → `should_refresh_data()` scans `/app/data/daily_prices_*.json`
   - No files found → Return 0 (refresh)
   - Any file older than `MAX_DATA_AGE_DAYS` → Return 0 (refresh)
   - All files fresh → Return 1 (skip)
4. **Conditional Fetch** → Run get_daily_price.py only if refresh needed
5. **Merge Data** → Always run merge_jsonl.py (handles missing merged.jsonl)
6. **MCP Services** → Start services (existing logic)
7. **Trading Agent** → Begin trading (existing logic)

### Edge Cases

| Scenario | Behavior |
|----------|----------|
| **First run (no data)** | Detects no files → triggers full fetch |
| **Restart within 7 days** | All files fresh → skips fetch (fast startup) |
| **Restart after 7 days** | Files stale → refreshes all data |
| **Partial data (some files missing)** | Missing files treated as infinitely old → triggers refresh |
| **Corrupt merged.jsonl but fresh price files** | Skips fetch, re-runs merge to rebuild merged.jsonl |
| **MAX_DATA_AGE_DAYS=0** | Always refresh (useful for testing/production) |
| **MAX_DATA_AGE_DAYS unset** | Defaults to 7 days |
| **Alpha Vantage rate limit** | get_daily_price.py handles with warning (existing behavior) |

## Configuration Options

| Variable | Default | Purpose |
|----------|---------|---------|
| `MAX_DATA_AGE_DAYS` | 7 | Days before price data considered stale |

**Special Values:**
- `0` → Always refresh (force fresh data)
- `999` → Never refresh (use cached data indefinitely)

## User Experience

### Scenario 1: Fresh Container
```
🚀 Starting AI-Trader...
🔍 Validating environment variables...
✅ Environment variables validated
📊 Checking price data freshness...
📭 No price data found
🔄 Fetching and merging price data...
✓ Fetched NVDA
✓ Fetched MSFT
...
```

### Scenario 2: Restart Within 7 Days
```
🚀 Starting AI-Trader...
🔍 Validating environment variables...
✅ Environment variables validated
📊 Checking price data freshness...
✅ All 103 price files are fresh (<7 days old)
⏭️  Skipping data fetch (using cached data)
🔧 Starting MCP services...
```

### Scenario 3: Restart After 7 Days
```
🚀 Starting AI-Trader...
🔍 Validating environment variables...
✅ Environment variables validated
📊 Checking price data freshness...
📅 Found 103 stale files (>7 days old)
🔄 Fetching and merging price data...
✓ Fetched NVDA
✓ Fetched MSFT
...
```

## Testing Plan

1. **Test fresh container:** Delete `./data/daily_prices_*.json`, start container → should fetch all
2. **Test cached data:** Restart immediately → should skip fetch
3. **Test staleness:** `touch -d "8 days ago" ./data/daily_prices_AAPL.json`, restart → should refresh
4. **Test partial data:** Delete 10 random price files → should refresh all
5. **Test MAX_DATA_AGE_DAYS=0:** Restart with env var set → should always fetch
6. **Test MAX_DATA_AGE_DAYS=30:** Restart with 8-day-old data → should skip

## Documentation Updates

Files requiring updates:
- `entrypoint.sh` → Add function and conditional logic
- `docker-compose.yml` → Add MAX_DATA_AGE_DAYS environment variable
- `.env.example` → Document MAX_DATA_AGE_DAYS with default value
- `CLAUDE.md` → Update "Docker Deployment" section with new env var
- `docs/DOCKER.md` (if exists) → Explain data caching behavior

## Benefits

- **Development:** Instant container restarts during iteration
- **API Quota:** ~103 fewer API calls per restart
- **Reliability:** No rate limit risks during frequent testing
- **Flexibility:** Configurable threshold for different use cases
- **Consistency:** Checks all files to ensure complete data
