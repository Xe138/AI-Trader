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
sleep 3

# Step 4: Run trading agent with config file
echo "🤖 Starting trading agent..."

# Smart config selection: custom_config.json takes precedence if it exists
if [ -f "configs/custom_config.json" ]; then
    CONFIG_FILE="configs/custom_config.json"
    echo "✅ Using custom configuration: configs/custom_config.json"
elif [ -n "$1" ]; then
    CONFIG_FILE="$1"
    echo "✅ Using specified configuration: $CONFIG_FILE"
else
    CONFIG_FILE="configs/default_config.json"
    echo "✅ Using default configuration: configs/default_config.json"
fi

python main.py "$CONFIG_FILE"

# Cleanup on exit
trap "echo '🛑 Stopping MCP services...'; kill $MCP_PID 2>/dev/null; exit 0" EXIT SIGTERM SIGINT
