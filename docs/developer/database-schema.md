# Database Schema

SQLite database schema reference.

---

## Tables

### jobs
Job metadata and overall status.

```sql
CREATE TABLE jobs (
    job_id TEXT PRIMARY KEY,
    config_path TEXT NOT NULL,
    status TEXT CHECK(status IN ('pending', 'running', 'completed', 'partial', 'failed')),
    date_range TEXT,  -- JSON array
    models TEXT,      -- JSON array
    created_at TEXT,
    started_at TEXT,
    completed_at TEXT,
    total_duration_seconds REAL,
    error TEXT
);
```

### job_details
Per model-day execution details.

```sql
CREATE TABLE job_details (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT,
    model_signature TEXT,
    trading_date TEXT,
    status TEXT CHECK(status IN ('pending', 'running', 'completed', 'failed')),
    start_time TEXT,
    end_time TEXT,
    duration_seconds REAL,
    error TEXT,
    FOREIGN KEY (job_id) REFERENCES jobs(job_id) ON DELETE CASCADE
);
```

### positions
Trading position records with P&L.

```sql
CREATE TABLE positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT,
    date TEXT,
    model TEXT,
    action_id INTEGER,
    action_type TEXT,
    symbol TEXT,
    amount INTEGER,
    price REAL,
    cash REAL,
    portfolio_value REAL,
    daily_profit REAL,
    daily_return_pct REAL,
    created_at TEXT
);
```

**Column Descriptions:**

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key, auto-incremented |
| job_id | TEXT | Foreign key to jobs table |
| date | TEXT | Trading date (YYYY-MM-DD) |
| model | TEXT | Model signature/identifier |
| action_id | INTEGER | Sequential action ID for the day (0 = start-of-day baseline) |
| action_type | TEXT | Type of action: 'no_trade', 'buy', or 'sell' |
| symbol | TEXT | Stock symbol (null for no_trade) |
| amount | INTEGER | Number of shares traded (null for no_trade) |
| price | REAL | Price per share (null for no_trade) |
| cash | REAL | Cash balance after action |
| portfolio_value | REAL | Total portfolio value (cash + holdings value) |
| daily_profit | REAL | **Daily profit/loss compared to start-of-day portfolio value (action_id=0).** Calculated as: `current_portfolio_value - start_of_day_portfolio_value`. This shows the actual gain/loss from price movements and trading decisions, not affected by merely buying/selling stocks. |
| daily_return_pct | REAL | **Daily return percentage compared to start-of-day portfolio value.** Calculated as: `(daily_profit / start_of_day_portfolio_value) * 100` |
| created_at | TEXT | ISO 8601 timestamp with 'Z' suffix |

**Important Notes:**

- **Position tracking flow:** Positions are written by trade tools (`buy()`, `sell()` in `agent_tools/tool_trade.py`) and no-trade records (`add_no_trade_record_to_db()` in `tools/price_tools.py`). Each trade creates a new position record.

- **Action ID sequence:**
  - `action_id=0`: Start-of-day position (created by `ModelDayExecutor._initialize_starting_position()` on first day only)
  - `action_id=1+`: Each trade or no-trade action increments the action_id

- **Profit calculation:** Daily profit is calculated by comparing current portfolio value to the **start-of-day** portfolio value (action_id=0 for the current date). This ensures that:
  - Buying stocks doesn't show as a loss (cash ↓, stock value ↑ equally)
  - Selling stocks doesn't show as a gain (cash ↑, stock value ↓ equally)
  - Only actual price movements and strategic trading show as profit/loss

### holdings
Portfolio holdings breakdown per position.

```sql
CREATE TABLE holdings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    position_id INTEGER,
    symbol TEXT,
    quantity REAL,
    FOREIGN KEY (position_id) REFERENCES positions(id) ON DELETE CASCADE
);
```

### price_data
Cached historical price data.

### price_coverage
Data availability tracking per symbol.

### reasoning_logs
AI decision reasoning (when enabled).

### tool_usage
MCP tool usage statistics.

---

See `api/database.py` for complete schema definitions.
