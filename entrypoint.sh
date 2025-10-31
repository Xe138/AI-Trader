#!/bin/bash
set -e  # Exit on any error

echo "🚀 Starting AI-Trader..."

# Validate required environment variables
echo "🔍 Validating environment variables..."
MISSING_VARS=()

if [ -z "$OPENAI_API_KEY" ]; then
    MISSING_VARS+=("OPENAI_API_KEY")
fi

if [ -z "$ALPHAADVANTAGE_API_KEY" ]; then
    MISSING_VARS+=("ALPHAADVANTAGE_API_KEY")
fi

if [ -z "$JINA_API_KEY" ]; then
    MISSING_VARS+=("JINA_API_KEY")
fi

if [ ${#MISSING_VARS[@]} -gt 0 ]; then
    echo ""
    echo "❌ ERROR: Missing required environment variables:"
    for var in "${MISSING_VARS[@]}"; do
        echo "   - $var"
    done
    echo ""
    echo "Please set these variables in your .env file:"
    echo "   1. Copy .env.example to .env"
    echo "   2. Edit .env and add your API keys"
    echo "   3. Restart the container"
    echo ""
    echo "See docs/DOCKER.md for more information."
    exit 1
fi

echo "✅ Environment variables validated"

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

# Step 2: Start MCP services in background
echo "🔧 Starting MCP services..."
cd /app
python agent_tools/start_mcp_services.py &
MCP_PID=$!

# Step 3: Wait for services to initialize
echo "⏳ Waiting for MCP services to start..."
sleep 3

# Step 4: Run trading agent with config file
echo "🤖 Starting trading agent..."
CONFIG_FILE="${1:-configs/default_config.json}"
python main.py "$CONFIG_FILE"

# Cleanup on exit
trap "echo '🛑 Stopping MCP services...'; kill $MCP_PID 2>/dev/null; exit 0" EXIT SIGTERM SIGINT
