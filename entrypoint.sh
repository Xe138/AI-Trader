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

# Step 1: Data preparation
echo "📊 Fetching and merging price data..."
# Run scripts from /app/scripts but output to /app/data
cd /app/data
python /app/scripts/get_daily_price.py
python /app/scripts/merge_jsonl.py
cd /app

# Step 2: Start MCP services in background
echo "🔧 Starting MCP services..."
cd /app
python agent_tools/start_mcp_services.py &
MCP_PID=$!

# Step 3: Wait for services to initialize
echo "⏳ Waiting for MCP services to start..."
sleep 5

# Verify MCP services are responsive
echo "🔍 Checking MCP service health..."
MAX_RETRIES=10
RETRY_COUNT=0
SERVICES_READY=false

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    # Check if all ports are listening
    if nc -z localhost 8000 && nc -z localhost 8001 && nc -z localhost 8002 && nc -z localhost 8003; then
        SERVICES_READY=true
        echo "✅ All MCP services are ready"
        break
    fi
    RETRY_COUNT=$((RETRY_COUNT + 1))
    echo "⏳ Waiting for services... (attempt $RETRY_COUNT/$MAX_RETRIES)"
    sleep 1
done

if [ "$SERVICES_READY" = false ]; then
    echo "⚠️  Warning: Some MCP services may not be ready"
    echo "   Check logs in /app/logs/ for details"
fi

# Step 4: Run trading agent with config file
echo "🤖 Starting trading agent..."
CONFIG_FILE="${1:-configs/default_config.json}"
python main.py "$CONFIG_FILE"

# Cleanup on exit
trap "echo '🛑 Stopping MCP services...'; kill $MCP_PID 2>/dev/null; exit 0" EXIT SIGTERM SIGINT
