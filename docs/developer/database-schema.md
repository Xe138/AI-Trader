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
