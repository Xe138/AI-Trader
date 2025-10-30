#!/bin/bash
set -e  # Exit on any error

echo "🚀 Starting AI-Trader..."

# Step 1: Data preparation
echo "📊 Fetching and merging price data..."
cd /app/data
python get_daily_price.py
python merge_jsonl.py
cd /app

# Step 2: Start MCP services in background
echo "🔧 Starting MCP services..."
cd /app/agent_tools
python start_mcp_services.py &
MCP_PID=$!
cd /app

# Step 3: Wait for services to initialize
echo "⏳ Waiting for MCP services to start..."
sleep 3

# Step 4: Run trading agent with config file
echo "🤖 Starting trading agent..."
CONFIG_FILE="${1:-configs/default_config.json}"
python main.py "$CONFIG_FILE"

# Cleanup on exit
trap "echo '🛑 Stopping MCP services...'; kill $MCP_PID 2>/dev/null; exit 0" EXIT SIGTERM SIGINT
