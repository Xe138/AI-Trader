# Data Cache Reuse Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Avoid re-fetching all 103 NASDAQ tickers on Docker container restart by checking file staleness and reusing cached data.

**Architecture:** Add bash staleness check function to entrypoint.sh that scans all `daily_prices_*.json` files. Only trigger full data fetch if any file is missing or older than configurable `MAX_DATA_AGE_DAYS` threshold.

**Tech Stack:** Bash scripting, Docker environment variables, find command for file age detection

---

## Task 1: Add Staleness Check Function to entrypoint.sh

**Files:**
- Modify: `entrypoint.sh:38-39` (after environment validation, before data preparation)

**Step 1: Add should_refresh_data() function**

Insert after line 38 (after "echo '✅ Environment variables validated'"):

```bash
# Function to check if price data needs refresh
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

**Step 2: Verify bash syntax**

Run: `bash -n entrypoint.sh`
Expected: No output (syntax valid)

**Step 3: Commit function addition**

```bash
git add entrypoint.sh
git commit -m "feat: add staleness check function for price data"
```

---

## Task 2: Replace Unconditional Data Fetch with Conditional Logic

**Files:**
- Modify: `entrypoint.sh:40-46` (Step 1: Data preparation section)

**Step 1: Replace unconditional fetch with conditional**

Replace lines 40-46:
```bash
# Step 1: Data preparation
echo "📊 Fetching and merging price data..."
# Run scripts from /app/scripts but output to /app/data
cd /app/data
python /app/scripts/get_daily_price.py
python /app/scripts/merge_jsonl.py
cd /app
```

With:
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

**Step 2: Verify bash syntax**

Run: `bash -n entrypoint.sh`
Expected: No output (syntax valid)

**Step 3: Commit conditional logic**

```bash
git add entrypoint.sh
git commit -m "feat: conditionally fetch price data based on staleness"
```

---

## Task 3: Add MAX_DATA_AGE_DAYS to docker-compose.yml

**Files:**
- Modify: `docker-compose.yml:29` (after AGENT_MAX_STEP, before ports section)

**Step 1: Add environment variable**

Insert after line 29:
```yaml
      # Data Refresh Configuration
      - MAX_DATA_AGE_DAYS=${MAX_DATA_AGE_DAYS:-7}
```

**Step 2: Verify YAML syntax**

Run: `yamllint docker-compose.yml`
Expected: No errors (or only warnings about line length/comments)

Alternative if yamllint not available:
Run: `docker-compose config > /dev/null`
Expected: No errors

**Step 3: Commit docker-compose.yml change**

```bash
git add docker-compose.yml
git commit -m "feat: add MAX_DATA_AGE_DAYS environment variable"
```

---

## Task 4: Document MAX_DATA_AGE_DAYS in .env.example

**Files:**
- Modify: `.env.example:19-20` (after JINA_API_KEY section)

**Step 1: Add configuration section**

Insert after line 19 (after JINA_API_KEY):
```bash

# Data Refresh Configuration
MAX_DATA_AGE_DAYS=7  # Refresh price data older than N days (0=always refresh)
```

**Step 2: Verify file is valid**

Run: `cat .env.example | grep MAX_DATA_AGE_DAYS`
Expected: Shows the new configuration line

**Step 3: Commit .env.example update**

```bash
git add .env.example
git commit -m "docs: document MAX_DATA_AGE_DAYS in .env.example"
```

---

## Task 5: Update CLAUDE.md Documentation

**Files:**
- Modify: `CLAUDE.md` (Docker Deployment section and Environment Setup section)

**Step 1: Add to Environment Setup section**

Find the section starting with "### Environment Setup" (around line 13). After the list of environment variables to set, add:

```markdown
# - MAX_DATA_AGE_DAYS (optional, default: 7)
```

**Step 2: Add to Docker Deployment section explanation**

Find the section "### Docker Deployment" (around line 31). After the existing docker-compose commands, add a new subsection:

```markdown

#### Data Caching Behavior

The container automatically caches price data between restarts:
- On first run: Fetches all 103 NASDAQ tickers
- On restart: Checks if data files are older than `MAX_DATA_AGE_DAYS` (default: 7 days)
  - If fresh: Skips fetch, uses cached data (fast startup)
  - If stale: Refreshes all data

Configure staleness threshold:
```bash
# In .env
MAX_DATA_AGE_DAYS=7   # Refresh after 7 days
MAX_DATA_AGE_DAYS=0   # Always refresh (testing)
MAX_DATA_AGE_DAYS=30  # Monthly refresh (historical backtesting)
```
```

**Step 3: Verify markdown formatting**

Run: `head -50 CLAUDE.md | grep -A 5 "MAX_DATA_AGE_DAYS"`
Expected: Shows the new documentation

**Step 4: Commit CLAUDE.md update**

```bash
git add CLAUDE.md
git commit -m "docs: document data caching behavior in CLAUDE.md"
```

---

## Task 6: Verify Implementation with Test Scenarios

**Files:**
- No code changes, verification only

**Step 1: Test scenario 1 - Fresh container (no data)**

Simulate by checking function behavior with no files:
```bash
# Test the logic manually
cd /app/data
rm -f daily_prices_*.json  # CAUTION: Only in test environment
cd /app
source <(grep -A 20 "should_refresh_data()" entrypoint.sh)
should_refresh_data && echo "✅ Would refresh (expected)" || echo "❌ Would skip (unexpected)"
```
Expected: "✅ Would refresh (expected)"

**Step 2: Test scenario 2 - Fresh data (recent files)**

Simulate by checking function with fresh files:
```bash
# Create test files
touch /app/data/daily_prices_TEST1.json /app/data/daily_prices_TEST2.json
should_refresh_data && echo "❌ Would refresh (unexpected)" || echo "✅ Would skip (expected)"
rm /app/data/daily_prices_TEST*.json
```
Expected: "✅ Would skip (expected)"

**Step 3: Test scenario 3 - Stale data (old files)**

Simulate by checking function with old files:
```bash
# Create old test files
touch -d "10 days ago" /app/data/daily_prices_STALE.json
should_refresh_data && echo "✅ Would refresh (expected)" || echo "❌ Would skip (unexpected)"
rm /app/data/daily_prices_STALE.json
```
Expected: "✅ Would refresh (expected)"

**Step 4: Verify docker-compose.yml is valid**

Run: `docker-compose config > /dev/null 2>&1 && echo "✅ docker-compose.yml valid" || echo "❌ Invalid YAML"`
Expected: "✅ docker-compose.yml valid"

**Step 5: Document verification complete**

No commit needed - this is verification only.

---

## Task 7: Final Integration Test (Optional - Requires Docker)

**Files:**
- No code changes, full system test

**Step 1: Build Docker image**

Run: `docker-compose build`
Expected: Build completes successfully

**Step 2: Test fresh container startup**

Run: `docker-compose up`
Expected: Logs show "📭 No price data found" and "🔄 Fetching and merging price data..."

**Step 3: Test cached data startup**

Stop container (Ctrl+C), then restart:
Run: `docker-compose up`
Expected: Logs show "✅ All 103 price files are fresh (<7 days old)" and "⏭️ Skipping data fetch"

**Step 4: Test MAX_DATA_AGE_DAYS=0**

Add to .env: `MAX_DATA_AGE_DAYS=0`, then restart:
Run: `docker-compose up`
Expected: Logs show "📅 Found 103 stale files" and always refreshes

**Step 5: Clean up test environment**

Run: `docker-compose down`

Note: This task is optional and should only be run if Docker is available. The implementation is complete without this integration test.

---

## Success Criteria

- ✅ `should_refresh_data()` function checks all `daily_prices_*.json` files
- ✅ Conditional logic in entrypoint.sh only fetches when needed
- ✅ `MAX_DATA_AGE_DAYS` configurable via environment variable (default: 7)
- ✅ Documentation updated in .env.example and CLAUDE.md
- ✅ All bash syntax is valid
- ✅ Function correctly identifies: no data, fresh data, stale data scenarios

## Principles Applied

- **DRY:** Single function encapsulates staleness logic
- **YAGNI:** No complex caching mechanisms, just file timestamps
- **Frequent commits:** 5 commits for 5 logical changes
- **Clear messages:** Emoji indicators for easy log scanning
- **Safe defaults:** 7 days balances freshness and API usage
