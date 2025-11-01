#!/bin/bash

# AI-Trader-Server 主启动脚本
# 用于启动完整的交易环境

set -e  # 遇到错误时退出

echo "🚀 Launching AI-Trader-Server Environment..."


echo "📊 Now getting and merging price data..."
cd ./data
# Note: get_daily_price.py now automatically calls merge_jsonl.py after fetching
python get_daily_price.py
cd ../

echo "🔧 Now starting MCP services..."
cd ./agent_tools
python start_mcp_services.py
cd ../

#waiting for MCP services to start
sleep 2

echo "🤖 Now starting the main trading agent..."
python main.py configs/default_config.json

echo "✅ AI-Trader-Server stopped"

echo "🔄 Starting web server..."
cd ./docs
python3 -m http.server 8888

echo "✅ Web server started"