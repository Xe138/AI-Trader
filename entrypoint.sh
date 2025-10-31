#!/bin/bash
set -e  # Exit on any error

echo "🚀 Starting AI-Trader API Server..."

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
    exit 1
fi

echo "✅ Environment variables validated"

# Step 1: Initialize database
echo "📊 Initializing database..."
python -c "from api.database import initialize_database; initialize_database('data/jobs.db')"
echo "✅ Database initialized"

# Step 2: Start MCP services in background
echo "🔧 Starting MCP services..."
cd /app
python agent_tools/start_mcp_services.py &
MCP_PID=$!

# Setup cleanup trap before starting uvicorn
trap "echo '🛑 Stopping services...'; kill $MCP_PID 2>/dev/null; exit 0" EXIT SIGTERM SIGINT

# Step 3: Wait for services to initialize
echo "⏳ Waiting for MCP services to start..."
sleep 3

# Step 4: Start FastAPI server with uvicorn (this blocks)
# Note: Container always uses port 8080 internally
# The API_PORT env var only affects the host port mapping in docker-compose.yml
echo "🌐 Starting FastAPI server on port 8080..."
exec uvicorn api.main:app \
    --host 0.0.0.0 \
    --port 8080 \
    --log-level info \
    --access-log
