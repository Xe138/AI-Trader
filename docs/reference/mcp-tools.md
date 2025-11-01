# MCP Tools Reference

Model Context Protocol tools available to AI agents.

---

## Available Tools

### Math Tool (Port 8000)
Mathematical calculations and analysis.

### Search Tool (Port 8001)
Market intelligence via Jina AI search.
- News articles
- Analyst reports
- Financial data

### Trade Tool (Port 8002)
Buy/sell execution.
- Place orders
- Check balances
- View positions

### Price Tool (Port 8003)
Historical and current price data.
- OHLCV data
- Multiple symbols
- Date filtering

---

## Usage

AI agents access tools automatically through MCP protocol.
Tools are localhost-only and not exposed to external network.

---

See `agent_tools/` directory for implementations.
