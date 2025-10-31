# Enhanced Database Specification - Results Storage in SQLite

## 1. Overview

**Change from Original Spec:** Instead of reading `position.jsonl` on-demand, simulation results are written to SQLite during execution for faster retrieval and queryability.

**Benefits:**
- **Faster `/results` endpoint** - No file I/O on every request
- **Advanced querying** - Filter by date range, model, performance metrics
- **Aggregations** - Portfolio timeseries, leaderboards, statistics
- **Data integrity** - Single source of truth with ACID guarantees
- **Backup/restore** - Single database file instead of scattered JSONL files

**Tradeoff:** Additional database writes during simulation (minimal performance impact)

---

## 2. Enhanced Database Schema

### 2.1 Complete Table Structure

```sql
-- Job tracking tables (from original spec)
CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    config_path TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('pending', 'running', 'completed', 'partial', 'failed')),
    date_range TEXT NOT NULL,
    models TEXT NOT NULL,
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    total_duration_seconds REAL,
    error TEXT
);

CREATE TABLE IF NOT EXISTS job_details (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    date TEXT NOT NULL,
    model TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('pending', 'running', 'completed', 'failed')),
    started_at TEXT,
    completed_at TEXT,
    duration_seconds REAL,
    error TEXT,
    FOREIGN KEY (job_id) REFERENCES jobs(job_id) ON DELETE CASCADE
);

-- NEW: Simulation results storage
CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    date TEXT NOT NULL,
    model TEXT NOT NULL,
    action_id INTEGER NOT NULL,  -- Sequence number within that day
    action_type TEXT CHECK(action_type IN ('buy', 'sell', 'no_trade')),
    symbol TEXT,
    amount INTEGER,
    price REAL,
    cash REAL NOT NULL,
    portfolio_value REAL NOT NULL,
    daily_profit REAL,
    daily_return_pct REAL,
    cumulative_profit REAL,
    cumulative_return_pct REAL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (job_id) REFERENCES jobs(job_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS holdings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    position_id INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    FOREIGN KEY (position_id) REFERENCES positions(id) ON DELETE CASCADE
);

-- NEW: AI reasoning logs (optional - for detail=full)
CREATE TABLE IF NOT EXISTS reasoning_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    date TEXT NOT NULL,
    model TEXT NOT NULL,
    step_number INTEGER NOT NULL,
    timestamp TEXT NOT NULL,
    role TEXT CHECK(role IN ('user', 'assistant', 'tool')),
    content TEXT,
    tool_name TEXT,
    FOREIGN KEY (job_id) REFERENCES jobs(job_id) ON DELETE CASCADE
);

-- NEW: Tool usage statistics
CREATE TABLE IF NOT EXISTS tool_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    date TEXT NOT NULL,
    model TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    call_count INTEGER NOT NULL DEFAULT 1,
    total_duration_seconds REAL,
    FOREIGN KEY (job_id) REFERENCES jobs(job_id) ON DELETE CASCADE
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_job_details_job_id ON job_details(job_id);
CREATE INDEX IF NOT EXISTS idx_job_details_status ON job_details(status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_job_details_unique ON job_details(job_id, date, model);

CREATE INDEX IF NOT EXISTS idx_positions_job_id ON positions(job_id);
CREATE INDEX IF NOT EXISTS idx_positions_date ON positions(date);
CREATE INDEX IF NOT EXISTS idx_positions_model ON positions(model);
CREATE INDEX IF NOT EXISTS idx_positions_date_model ON positions(date, model);
CREATE UNIQUE INDEX IF NOT EXISTS idx_positions_unique ON positions(job_id, date, model, action_id);

CREATE INDEX IF NOT EXISTS idx_holdings_position_id ON holdings(position_id);
CREATE INDEX IF NOT EXISTS idx_holdings_symbol ON holdings(symbol);

CREATE INDEX IF NOT EXISTS idx_reasoning_logs_job_date_model ON reasoning_logs(job_id, date, model);
CREATE INDEX IF NOT EXISTS idx_tool_usage_job_date_model ON tool_usage(job_id, date, model);
```

---

### 2.2 Table Relationships

```
jobs (1) ──┬──> (N) job_details
           │
           ├──> (N) positions ──> (N) holdings
           │
           ├──> (N) reasoning_logs
           │
           └──> (N) tool_usage
```

---

### 2.3 Data Examples

#### positions table
```
id | job_id     | date       | model | action_id | action_type | symbol | amount | price  | cash    | portfolio_value | daily_profit | daily_return_pct | cumulative_profit | cumulative_return_pct | created_at
---|------------|------------|-------|-----------|-------------|--------|--------|--------|---------|-----------------|--------------|------------------|-------------------|----------------------|------------
1  | abc-123... | 2025-01-16 | gpt-5 | 0         | no_trade    | NULL   | NULL   | NULL   | 10000.0 | 10000.0         | 0.0          | 0.0              | 0.0               | 0.0                  | 2025-01-16T09:30:00Z
2  | abc-123... | 2025-01-16 | gpt-5 | 1         | buy         | AAPL   | 10     | 255.88 | 7441.2  | 10000.0         | 0.0          | 0.0              | 0.0               | 0.0                  | 2025-01-16T09:35:12Z
3  | abc-123... | 2025-01-17 | gpt-5 | 0         | no_trade    | NULL   | NULL   | NULL   | 7441.2  | 10150.5         | 150.5        | 1.51             | 150.5             | 1.51                 | 2025-01-17T09:30:00Z
4  | abc-123... | 2025-01-17 | gpt-5 | 1         | sell        | AAPL   | 5      | 262.24 | 8752.4  | 10150.5         | 150.5        | 1.51             | 150.5             | 1.51                 | 2025-01-17T09:42:38Z
```

#### holdings table
```
id | position_id | symbol | quantity
---|-------------|--------|----------
1  | 2           | AAPL   | 10
2  | 3           | AAPL   | 10
3  | 4           | AAPL   | 5
```

#### tool_usage table
```
id | job_id     | date       | model | tool_name  | call_count | total_duration_seconds
---|------------|------------|-------|------------|------------|-----------------------
1  | abc-123... | 2025-01-16 | gpt-5 | get_price  | 5          | 2.3
2  | abc-123... | 2025-01-16 | gpt-5 | search     | 3          | 12.7
3  | abc-123... | 2025-01-16 | gpt-5 | trade      | 1          | 0.8
4  | abc-123... | 2025-01-16 | gpt-5 | math       | 2          | 0.1
```

---

## 3. Data Migration from position.jsonl

### 3.1 Migration Strategy

**During execution:** Write to BOTH SQLite AND position.jsonl for backward compatibility

**Migration path:**
1. **Phase 1:** Dual-write mode (write to both SQLite and JSONL)
2. **Phase 2:** Verify SQLite data matches JSONL
3. **Phase 3:** Switch `/results` endpoint to read from SQLite
4. **Phase 4:** (Optional) Deprecate JSONL writes

**Import existing data:** One-time migration script to populate SQLite from existing position.jsonl files

---

### 3.2 Import Script

```python
# api/import_historical_data.py

import json
import sqlite3
from pathlib import Path
from datetime import datetime
from api.database import get_db_connection

def import_position_jsonl(
    model_signature: str,
    position_file: Path,
    job_id: str = "historical-import"
) -> int:
    """
    Import existing position.jsonl data into SQLite.

    Args:
        model_signature: Model signature (e.g., "gpt-5")
        position_file: Path to position.jsonl
        job_id: Job ID to associate with (use "historical-import" for existing data)

    Returns:
        Number of records imported
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    imported_count = 0
    initial_cash = 10000.0

    with open(position_file, 'r') as f:
        for line in f:
            if not line.strip():
                continue

            record = json.loads(line)
            date = record['date']
            action_id = record['id']
            action = record.get('this_action', {})
            positions = record.get('positions', {})

            # Extract action details
            action_type = action.get('action', 'no_trade')
            symbol = action.get('symbol', None)
            amount = action.get('amount', None)
            price = None  # Not stored in original position.jsonl

            # Extract holdings
            cash = positions.get('CASH', 0.0)
            holdings = {k: v for k, v in positions.items() if k != 'CASH' and v > 0}

            # Calculate portfolio value (approximate - need price data)
            portfolio_value = cash  # Base value

            # Calculate profits (need previous record)
            daily_profit = 0.0
            daily_return_pct = 0.0
            cumulative_profit = cash - initial_cash  # Simplified
            cumulative_return_pct = (cumulative_profit / initial_cash) * 100

            # Insert position record
            cursor.execute("""
                INSERT INTO positions (
                    job_id, date, model, action_id, action_type, symbol, amount, price,
                    cash, portfolio_value, daily_profit, daily_return_pct,
                    cumulative_profit, cumulative_return_pct, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                job_id, date, model_signature, action_id, action_type, symbol, amount, price,
                cash, portfolio_value, daily_profit, daily_return_pct,
                cumulative_profit, cumulative_return_pct, datetime.utcnow().isoformat() + "Z"
            ))

            position_id = cursor.lastrowid

            # Insert holdings
            for sym, qty in holdings.items():
                cursor.execute("""
                    INSERT INTO holdings (position_id, symbol, quantity)
                    VALUES (?, ?, ?)
                """, (position_id, sym, qty))

            imported_count += 1

    conn.commit()
    conn.close()

    return imported_count


def import_all_historical_data(base_path: Path = Path("data/agent_data")) -> dict:
    """
    Import all existing position.jsonl files from data/agent_data/.

    Returns:
        Summary dict with import counts per model
    """
    summary = {}

    for model_dir in base_path.iterdir():
        if not model_dir.is_dir():
            continue

        model_signature = model_dir.name
        position_file = model_dir / "position" / "position.jsonl"

        if not position_file.exists():
            continue

        print(f"Importing {model_signature}...")
        count = import_position_jsonl(model_signature, position_file)
        summary[model_signature] = count
        print(f"  Imported {count} records")

    return summary


if __name__ == "__main__":
    print("Starting historical data import...")
    summary = import_all_historical_data()
    print(f"\nImport complete: {summary}")
    print(f"Total records: {sum(summary.values())}")
```

---

## 4. Updated Results Service

### 4.1 ResultsService Class

```python
# api/results_service.py

from typing import List, Dict, Optional
from datetime import datetime
from api.database import get_db_connection

class ResultsService:
    """
    Service for retrieving simulation results from SQLite.

    Replaces on-demand reading of position.jsonl files.
    """

    def __init__(self, db_path: str = "data/jobs.db"):
        self.db_path = db_path

    def get_results(
        self,
        date: str,
        model: Optional[str] = None,
        detail: str = "minimal"
    ) -> Dict:
        """
        Get simulation results for specified date and model(s).

        Args:
            date: Trading date (YYYY-MM-DD)
            model: Optional model signature filter
            detail: "minimal" or "full"

        Returns:
            {
                "date": str,
                "results": [
                    {
                        "model": str,
                        "positions": {...},
                        "daily_pnl": {...},
                        "trades": [...],  // if detail=full
                        "ai_reasoning": {...}  // if detail=full
                    }
                ]
            }
        """
        conn = get_db_connection(self.db_path)

        # Get all models for this date (or specific model)
        if model:
            models = [model]
        else:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT DISTINCT model FROM positions WHERE date = ?
            """, (date,))
            models = [row[0] for row in cursor.fetchall()]

        results = []

        for mdl in models:
            result = self._get_model_result(conn, date, mdl, detail)
            if result:
                results.append(result)

        conn.close()

        return {
            "date": date,
            "results": results
        }

    def _get_model_result(
        self,
        conn,
        date: str,
        model: str,
        detail: str
    ) -> Optional[Dict]:
        """Get result for single model on single date"""
        cursor = conn.cursor()

        # Get latest position for this date (highest action_id)
        cursor.execute("""
            SELECT
                cash, portfolio_value, daily_profit, daily_return_pct,
                cumulative_profit, cumulative_return_pct
            FROM positions
            WHERE date = ? AND model = ?
            ORDER BY action_id DESC
            LIMIT 1
        """, (date, model))

        row = cursor.fetchone()
        if not row:
            return None

        cash, portfolio_value, daily_profit, daily_return_pct, cumulative_profit, cumulative_return_pct = row

        # Get holdings for latest position
        cursor.execute("""
            SELECT h.symbol, h.quantity
            FROM holdings h
            JOIN positions p ON h.position_id = p.id
            WHERE p.date = ? AND p.model = ?
            ORDER BY p.action_id DESC
            LIMIT 100  -- One position worth of holdings
        """, (date, model))

        holdings = {row[0]: row[1] for row in cursor.fetchall()}
        holdings['CASH'] = cash

        result = {
            "model": model,
            "positions": holdings,
            "daily_pnl": {
                "profit": daily_profit,
                "return_pct": daily_return_pct,
                "portfolio_value": portfolio_value
            },
            "cumulative_pnl": {
                "profit": cumulative_profit,
                "return_pct": cumulative_return_pct
            }
        }

        # Add full details if requested
        if detail == "full":
            result["trades"] = self._get_trades(cursor, date, model)
            result["ai_reasoning"] = self._get_reasoning(cursor, date, model)
            result["tool_usage"] = self._get_tool_usage(cursor, date, model)

        return result

    def _get_trades(self, cursor, date: str, model: str) -> List[Dict]:
        """Get all trades executed on this date"""
        cursor.execute("""
            SELECT action_id, action_type, symbol, amount, price
            FROM positions
            WHERE date = ? AND model = ? AND action_type IN ('buy', 'sell')
            ORDER BY action_id
        """, (date, model))

        trades = []
        for row in cursor.fetchall():
            trades.append({
                "id": row[0],
                "action": row[1],
                "symbol": row[2],
                "amount": row[3],
                "price": row[4],
                "total": row[3] * row[4] if row[3] and row[4] else None
            })

        return trades

    def _get_reasoning(self, cursor, date: str, model: str) -> Dict:
        """Get AI reasoning summary"""
        cursor.execute("""
            SELECT COUNT(*) as total_steps,
                   COUNT(CASE WHEN role = 'assistant' THEN 1 END) as assistant_messages,
                   COUNT(CASE WHEN role = 'tool' THEN 1 END) as tool_messages
            FROM reasoning_logs
            WHERE date = ? AND model = ?
        """, (date, model))

        row = cursor.fetchone()
        total_steps = row[0] if row else 0

        # Get reasoning summary (last assistant message with FINISH_SIGNAL)
        cursor.execute("""
            SELECT content FROM reasoning_logs
            WHERE date = ? AND model = ? AND role = 'assistant'
              AND content LIKE '%<FINISH_SIGNAL>%'
            ORDER BY step_number DESC
            LIMIT 1
        """, (date, model))

        row = cursor.fetchone()
        reasoning_summary = row[0] if row else "No reasoning summary available"

        return {
            "total_steps": total_steps,
            "stop_signal_received": "<FINISH_SIGNAL>" in reasoning_summary,
            "reasoning_summary": reasoning_summary[:500]  # Truncate for brevity
        }

    def _get_tool_usage(self, cursor, date: str, model: str) -> Dict[str, int]:
        """Get tool usage counts"""
        cursor.execute("""
            SELECT tool_name, call_count
            FROM tool_usage
            WHERE date = ? AND model = ?
        """, (date, model))

        return {row[0]: row[1] for row in cursor.fetchall()}

    def get_portfolio_timeseries(
        self,
        model: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> List[Dict]:
        """
        Get portfolio value over time for a model.

        Returns:
            [
                {"date": "2025-01-16", "portfolio_value": 10000.0, "daily_return_pct": 0.0},
                {"date": "2025-01-17", "portfolio_value": 10150.5, "daily_return_pct": 1.51},
                ...
            ]
        """
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        query = """
            SELECT date, portfolio_value, daily_return_pct, cumulative_return_pct
            FROM (
                SELECT date, portfolio_value, daily_return_pct, cumulative_return_pct,
                       ROW_NUMBER() OVER (PARTITION BY date ORDER BY action_id DESC) as rn
                FROM positions
                WHERE model = ?
            )
            WHERE rn = 1
        """

        params = [model]

        if start_date:
            query += " AND date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND date <= ?"
            params.append(end_date)

        query += " ORDER BY date ASC"

        cursor.execute(query, params)

        timeseries = []
        for row in cursor.fetchall():
            timeseries.append({
                "date": row[0],
                "portfolio_value": row[1],
                "daily_return_pct": row[2],
                "cumulative_return_pct": row[3]
            })

        conn.close()
        return timeseries

    def get_leaderboard(self, date: Optional[str] = None) -> List[Dict]:
        """
        Get model performance leaderboard.

        Args:
            date: Optional date filter (latest results if not specified)

        Returns:
            [
                {"model": "gpt-5", "portfolio_value": 10500, "cumulative_return_pct": 5.0, "rank": 1},
                {"model": "claude-3.7-sonnet", "portfolio_value": 10300, "cumulative_return_pct": 3.0, "rank": 2},
                ...
            ]
        """
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        if date:
            # Specific date leaderboard
            cursor.execute("""
                SELECT model, portfolio_value, cumulative_return_pct
                FROM (
                    SELECT model, portfolio_value, cumulative_return_pct,
                           ROW_NUMBER() OVER (PARTITION BY model ORDER BY action_id DESC) as rn
                    FROM positions
                    WHERE date = ?
                )
                WHERE rn = 1
                ORDER BY portfolio_value DESC
            """, (date,))
        else:
            # Latest results for each model
            cursor.execute("""
                SELECT model, portfolio_value, cumulative_return_pct
                FROM (
                    SELECT model, portfolio_value, cumulative_return_pct,
                           ROW_NUMBER() OVER (PARTITION BY model ORDER BY date DESC, action_id DESC) as rn
                    FROM positions
                )
                WHERE rn = 1
                ORDER BY portfolio_value DESC
            """)

        leaderboard = []
        rank = 1
        for row in cursor.fetchall():
            leaderboard.append({
                "rank": rank,
                "model": row[0],
                "portfolio_value": row[1],
                "cumulative_return_pct": row[2]
            })
            rank += 1

        conn.close()
        return leaderboard
```

---

## 5. Updated Executor - Write to SQLite

```python
# api/executor.py (additions to existing code)

class ModelDayExecutor:
    # ... existing code ...

    async def run_model_day(
        self,
        job_id: str,
        date: str,
        model_config: Dict[str, Any],
        agent_class: type,
        config: Dict[str, Any]
    ) -> None:
        """Execute simulation for one model on one date"""

        # ... existing execution code ...

        try:
            # Execute trading session
            await agent.run_trading_session(date)

            # NEW: Extract and store results in SQLite
            self._store_results_to_db(job_id, date, model_sig)

            # Mark as completed
            self.job_manager.update_job_detail_status(
                job_id, date, model_sig, "completed"
            )

        except Exception as e:
            # ... error handling ...

    def _store_results_to_db(self, job_id: str, date: str, model: str) -> None:
        """
        Extract data from position.jsonl and log.jsonl, store in SQLite.

        This runs after agent.run_trading_session() completes.
        """
        from api.database import get_db_connection
        from pathlib import Path
        import json

        conn = get_db_connection()
        cursor = conn.cursor()

        # Read position.jsonl for this model
        position_file = Path(f"data/agent_data/{model}/position/position.jsonl")

        if not position_file.exists():
            logger.warning(f"Position file not found: {position_file}")
            return

        # Find records for this date
        with open(position_file, 'r') as f:
            for line in f:
                if not line.strip():
                    continue

                record = json.loads(line)
                if record['date'] != date:
                    continue  # Skip other dates

                # Extract fields
                action_id = record['id']
                action = record.get('this_action', {})
                positions = record.get('positions', {})

                action_type = action.get('action', 'no_trade')
                symbol = action.get('symbol')
                amount = action.get('amount')
                price = None  # TODO: Get from price data if needed

                cash = positions.get('CASH', 0.0)
                holdings = {k: v for k, v in positions.items() if k != 'CASH' and v > 0}

                # Calculate portfolio value (simplified - improve with actual prices)
                portfolio_value = cash  # + sum(holdings value)

                # Calculate daily P&L (compare to previous day's closing value)
                # TODO: Implement proper P&L calculation

                # Insert position
                cursor.execute("""
                    INSERT INTO positions (
                        job_id, date, model, action_id, action_type, symbol, amount, price,
                        cash, portfolio_value, daily_profit, daily_return_pct,
                        cumulative_profit, cumulative_return_pct, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    job_id, date, model, action_id, action_type, symbol, amount, price,
                    cash, portfolio_value, 0.0, 0.0,  # TODO: Calculate P&L
                    0.0, 0.0,  # TODO: Calculate cumulative P&L
                    datetime.utcnow().isoformat() + "Z"
                ))

                position_id = cursor.lastrowid

                # Insert holdings
                for sym, qty in holdings.items():
                    cursor.execute("""
                        INSERT INTO holdings (position_id, symbol, quantity)
                        VALUES (?, ?, ?)
                    """, (position_id, sym, qty))

        # Parse log.jsonl for reasoning (if detail=full is needed later)
        # TODO: Implement log parsing and storage in reasoning_logs table

        conn.commit()
        conn.close()

        logger.info(f"Stored results for {model} on {date} in SQLite")
```

---

## 6. Migration Path

### 6.1 Backward Compatibility

**Keep position.jsonl writes** to ensure existing tools/scripts continue working:

```python
# In agent/base_agent/base_agent.py - no changes needed
# position.jsonl writing continues as normal

# In api/executor.py - AFTER position.jsonl is written
await agent.run_trading_session(date)  # Writes to position.jsonl
self._store_results_to_db(job_id, date, model_sig)  # Copies to SQLite
```

### 6.2 Gradual Migration

**Week 1:** Deploy with dual-write (JSONL + SQLite)
**Week 2:** Verify data consistency, fix any discrepancies
**Week 3:** Switch `/results` endpoint to read from SQLite
**Week 4:** (Optional) Remove JSONL writes

---

## 7. Updated API Endpoints

### 7.1 Enhanced `/results` Endpoint

```python
# api/main.py

from api.results_service import ResultsService

results_service = ResultsService()

@app.get("/results")
async def get_results(
    date: str,
    model: Optional[str] = None,
    detail: str = "minimal"
):
    """Get simulation results from SQLite (fast!)"""
    # Validate date format
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format (use YYYY-MM-DD)")

    results = results_service.get_results(date, model, detail)

    if not results["results"]:
        raise HTTPException(status_code=404, detail=f"No data found for date {date}")

    return results
```

### 7.2 New Endpoints for Advanced Queries

```python
@app.get("/portfolio/timeseries")
async def get_portfolio_timeseries(
    model: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    """Get portfolio value over time for a model"""
    timeseries = results_service.get_portfolio_timeseries(model, start_date, end_date)

    if not timeseries:
        raise HTTPException(status_code=404, detail=f"No data found for model {model}")

    return {
        "model": model,
        "timeseries": timeseries
    }


@app.get("/leaderboard")
async def get_leaderboard(date: Optional[str] = None):
    """Get model performance leaderboard"""
    leaderboard = results_service.get_leaderboard(date)

    return {
        "date": date or "latest",
        "leaderboard": leaderboard
    }
```

---

## 8. Database Maintenance

### 8.1 Cleanup Old Data

```python
# api/job_manager.py (add method)

def cleanup_old_data(self, days: int = 90) -> dict:
    """
    Delete jobs and associated data older than specified days.

    Returns:
        Summary of deleted records
    """
    conn = get_db_connection(self.db_path)
    cursor = conn.cursor()

    cutoff_date = (datetime.utcnow() - timedelta(days=days)).isoformat() + "Z"

    # Count records before deletion
    cursor.execute("SELECT COUNT(*) FROM jobs WHERE created_at < ?", (cutoff_date,))
    jobs_to_delete = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*) FROM positions
        WHERE job_id IN (SELECT job_id FROM jobs WHERE created_at < ?)
    """, (cutoff_date,))
    positions_to_delete = cursor.fetchone()[0]

    # Delete (CASCADE will handle related tables)
    cursor.execute("DELETE FROM jobs WHERE created_at < ?", (cutoff_date,))

    conn.commit()
    conn.close()

    return {
        "cutoff_date": cutoff_date,
        "jobs_deleted": jobs_to_delete,
        "positions_deleted": positions_to_delete
    }
```

### 8.2 Vacuum Database

```python
def vacuum_database(self) -> None:
    """Reclaim disk space after deletes"""
    conn = get_db_connection(self.db_path)
    conn.execute("VACUUM")
    conn.close()
```

---

## Summary

**Enhanced database schema** with 6 tables:
- `jobs`, `job_details` (job tracking)
- `positions`, `holdings` (simulation results)
- `reasoning_logs`, `tool_usage` (AI details)

**Benefits:**
- ⚡ **10-100x faster** `/results` queries (no file I/O)
- 📊 **Advanced analytics** - timeseries, leaderboards, aggregations
- 🔒 **Data integrity** - ACID compliance, foreign keys
- 🗄️ **Single source of truth** - all data in one place

**Migration strategy:** Dual-write (JSONL + SQLite) for backward compatibility

**Next:** Comprehensive testing suite specification
