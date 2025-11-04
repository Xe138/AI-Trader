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

### trading_days

Core table for each model-day execution with daily P&L metrics.

```sql
CREATE TABLE trading_days (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    model TEXT NOT NULL,
    date TEXT NOT NULL,

    -- Starting position (cash only, holdings from previous day)
    starting_cash REAL NOT NULL,
    starting_portfolio_value REAL NOT NULL,

    -- Daily performance metrics
    daily_profit REAL NOT NULL,
    daily_return_pct REAL NOT NULL,

    -- Ending state (cash only, holdings in separate table)
    ending_cash REAL NOT NULL,
    ending_portfolio_value REAL NOT NULL,

    -- Reasoning
    reasoning_summary TEXT,
    reasoning_full TEXT,

    -- Metadata
    total_actions INTEGER DEFAULT 0,
    session_duration_seconds REAL,
    days_since_last_trading INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,

    UNIQUE(job_id, model, date),
    FOREIGN KEY (job_id) REFERENCES jobs(job_id)
);

CREATE INDEX idx_trading_days_lookup ON trading_days(job_id, model, date);
```

**Column Descriptions:**

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key, auto-incremented |
| job_id | TEXT | Foreign key to jobs table |
| model | TEXT | Model signature/identifier |
| date | TEXT | Trading date (YYYY-MM-DD) |
| starting_cash | REAL | Cash balance at start of day |
| starting_portfolio_value | REAL | Total portfolio value at start (includes holdings valued at current prices) |
| daily_profit | REAL | Dollar P&L from previous close (portfolio appreciation/depreciation) |
| daily_return_pct | REAL | Percentage return from previous close |
| ending_cash | REAL | Cash balance at end of day |
| ending_portfolio_value | REAL | Total portfolio value at end |
| reasoning_summary | TEXT | AI-generated 2-3 sentence summary of trading strategy |
| reasoning_full | TEXT | JSON array of complete conversation log |
| total_actions | INTEGER | Number of trades executed during the day |
| session_duration_seconds | REAL | AI session duration in seconds |
| days_since_last_trading | INTEGER | Days since previous trading day (1=normal, 3=weekend, 0=first day) |
| created_at | TIMESTAMP | Record creation timestamp |
| completed_at | TIMESTAMP | Session completion timestamp |

**Important Notes:**

- **Day-centric structure:** Each row represents one complete trading day for one model
- **First trading day:** `daily_profit = 0`, `daily_return_pct = 0`, `days_since_last_trading = 0`
- **Subsequent days:** Daily P&L calculated by valuing previous day's holdings at current prices
- **Weekend gaps:** System handles multi-day gaps automatically (e.g., Monday following Friday shows `days_since_last_trading = 3`)
- **Starting holdings:** Derived from previous day's ending holdings (not stored in this table, see `holdings` table)
- **Unique constraint:** One record per (job_id, model, date) combination

**Daily P&L Calculation:**

Daily profit accurately reflects portfolio appreciation from price movements:

1. Get previous day's ending holdings and cash
2. Value those holdings at current day's opening prices
3. `daily_profit = current_value - previous_value`
4. `daily_return_pct = (daily_profit / previous_value) * 100`

This ensures buying/selling stocks doesn't affect P&L - only price changes do.

---

### holdings

Portfolio holdings snapshots (ending positions only).

```sql
CREATE TABLE holdings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trading_day_id INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    quantity INTEGER NOT NULL,

    FOREIGN KEY (trading_day_id) REFERENCES trading_days(id) ON DELETE CASCADE,
    UNIQUE(trading_day_id, symbol)
);

CREATE INDEX idx_holdings_day ON holdings(trading_day_id);
```

**Column Descriptions:**

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key, auto-incremented |
| trading_day_id | INTEGER | Foreign key to trading_days table |
| symbol | TEXT | Stock symbol |
| quantity | INTEGER | Number of shares held at end of day |

**Important Notes:**

- **Ending positions only:** This table stores only the final holdings at end of day
- **Starting positions:** Derived by querying holdings for previous day's trading_day_id
- **Cascade deletion:** Holdings are automatically deleted when parent trading_day is deleted
- **Unique constraint:** One row per (trading_day_id, symbol) combination
- **No cash:** Cash is stored directly in trading_days table (`ending_cash`)

---

### actions

Trade execution ledger.

```sql
CREATE TABLE actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trading_day_id INTEGER NOT NULL,

    action_type TEXT NOT NULL,
    symbol TEXT,
    quantity INTEGER,
    price REAL,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (trading_day_id) REFERENCES trading_days(id) ON DELETE CASCADE
);

CREATE INDEX idx_actions_day ON actions(trading_day_id);
```

**Column Descriptions:**

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key, auto-incremented |
| trading_day_id | INTEGER | Foreign key to trading_days table |
| action_type | TEXT | Trade type: 'buy', 'sell', or 'no_trade' |
| symbol | TEXT | Stock symbol (NULL for no_trade) |
| quantity | INTEGER | Number of shares traded (NULL for no_trade) |
| price | REAL | Execution price per share (NULL for no_trade) |
| created_at | TIMESTAMP | Timestamp of trade execution |

**Important Notes:**

- **Trade ledger:** Sequential log of all trades executed during a trading day
- **No_trade actions:** Recorded when agent decides not to trade
- **Cascade deletion:** Actions are automatically deleted when parent trading_day is deleted
- **Execution order:** Use `created_at` to determine trade execution sequence
- **Price snapshot:** Records actual execution price at time of trade

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
