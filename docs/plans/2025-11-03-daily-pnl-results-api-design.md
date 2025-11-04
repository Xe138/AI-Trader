# Daily P&L Calculation & Results API Refactor - Design Document

**Date:** 2025-11-03
**Status:** Approved - Ready for Implementation

---

## Problem Statement

The current results API returns data in an action-centric format where every trade action is a separate record. This has several issues:

1. **Incorrect Daily Metrics:** `daily_profit` and `daily_return_pct` always return 0
2. **Data Structure:** Multiple position records per day with redundant portfolio snapshots
3. **API Design:** Separate `/results` and `/reasoning` endpoints that should be unified
4. **Missing Context:** No clear distinction between starting/ending positions for a day

**Example of Current Incorrect Output:**
```json
{
  "daily_profit": 0,
  "daily_return_pct": 0,
  "portfolio_value": 10062.15
}
```

Even though portfolio clearly changed from $9,957.96 to $10,062.15.

---

## Solution Design

### Core Principles

1. **Day-Centric Data Model:** Each trading day is the primary unit, not individual actions
2. **Ledger-Based Holdings:** Use snapshot approach (ending holdings only) for performance
3. **Calculate P&L at Market Open:** Value yesterday's holdings at today's prices
4. **Unified API:** Single `/results` endpoint with optional reasoning parameter
5. **AI-Generated Summaries:** Create summaries during simulation, not on-demand

---

## Database Schema (Normalized)

### trading_days Table

**Purpose:** Core table for each model-day execution with daily metrics

```sql
CREATE TABLE trading_days (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    model TEXT NOT NULL,
    date TEXT NOT NULL,

    -- Starting state (cash only, holdings from previous day)
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
    reasoning_full TEXT,  -- JSON array

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

### holdings Table

**Purpose:** Ending portfolio snapshots (starting holdings derived from previous day)

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

**Key Design Decision:** Only store ending holdings. Starting holdings = previous day's ending holdings.

### actions Table

**Purpose:** Trade execution ledger

```sql
CREATE TABLE actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trading_day_id INTEGER NOT NULL,

    action_type TEXT NOT NULL,  -- 'buy', 'sell', 'no_trade'
    symbol TEXT,
    quantity INTEGER,
    price REAL,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (trading_day_id) REFERENCES trading_days(id) ON DELETE CASCADE
);

CREATE INDEX idx_actions_day ON actions(trading_day_id);
```

---

## Daily P&L Calculation Logic

### When to Calculate

**Timing:** At the start of each trading day, after loading current market prices.

### Calculation Method

```python
def calculate_daily_pnl(previous_day, current_date, current_prices):
    """
    Calculate P&L by valuing yesterday's holdings at today's prices.

    Args:
        previous_day: {
            "date": "2025-01-15",
            "ending_cash": 9000.0,
            "ending_portfolio_value": 10000.0,
            "holdings": [{"symbol": "AAPL", "quantity": 10}]
        }
        current_date: "2025-01-16"
        current_prices: {"AAPL": 150.0}

    Returns:
        {
            "daily_profit": 500.0,
            "daily_return_pct": 5.0,
            "starting_portfolio_value": 10500.0,
            "days_since_last_trading": 1
        }
    """
    if previous_day is None:
        # First trading day
        return {
            "daily_profit": 0.0,
            "daily_return_pct": 0.0,
            "starting_portfolio_value": initial_cash,
            "days_since_last_trading": 0
        }

    # Value previous holdings at current prices
    current_value = cash
    for holding in previous_holdings:
        current_value += holding["quantity"] * current_prices[holding["symbol"]]

    # Calculate P&L
    previous_value = previous_day["ending_portfolio_value"]
    daily_profit = current_value - previous_value
    daily_return_pct = (daily_profit / previous_value) * 100

    return {
        "daily_profit": daily_profit,
        "daily_return_pct": daily_return_pct,
        "starting_portfolio_value": current_value,
        "days_since_last_trading": calculate_day_gap(previous_day["date"], current_date)
    }
```

### Key Insight: P&L from Price Changes, Not Trades

**Important:** Since all trades within a day use the same day's prices, portfolio value doesn't change between trades. P&L only changes when moving to the next day with new prices.

**Example:**
- Friday close: Hold 10 AAPL at $100 = $1000 total
- Monday open: AAPL now $110
- Monday P&L: 10 × ($110 - $100) = **+$100 profit**
- All Monday trades use $110 price, so P&L remains constant for that day

---

## Weekend/Holiday Handling

### Problem

Trading days are not consecutive calendar days:
- Friday → Monday (3-day gap)
- Before holidays (4+ day gaps)

### Solution

Use `ORDER BY date DESC LIMIT 1` to find **most recent trading day**, not just previous calendar date.

```sql
SELECT td_prev.id
FROM trading_days td_current
JOIN trading_days td_prev ON
    td_prev.job_id = td_current.job_id AND
    td_prev.model = td_current.model AND
    td_prev.date < td_current.date
WHERE td_current.id = ?
ORDER BY td_prev.date DESC
LIMIT 1
```

This automatically handles:
- Normal weekdays (1 day gap)
- Weekends (3 day gap)
- Long weekends (4+ day gap)

---

## Reasoning Summary Generation

### When to Generate

**Timing:** After trading session completes, before storing final results.

### Implementation

```python
async def generate_reasoning_summary(reasoning_log, ai_model):
    """
    Use same AI model to summarize its own trading decisions.

    Prompt: "Summarize your trading strategy and key decisions in 2-3 sentences."
    """
    try:
        summary = await ai_model.ainvoke([{
            "role": "user",
            "content": build_summary_prompt(reasoning_log)
        }])
        return extract_content(summary)

    except Exception as e:
        # Fallback: Statistical summary
        return f"Executed {trade_count} trades using {search_count} searches."
```

### Model Choice

**Use same model that did the trading** (Option A from brainstorming):
- Pro: Consistency, model summarizing its own reasoning
- Pro: Simpler configuration
- Con: Extra API cost per day (acceptable for quality)

---

## Unified Results API

### Endpoint Design

```
GET /results?job_id={id}&model={sig}&date={date}&reasoning={level}
```

**Parameters:**
- `job_id` (optional) - Filter by job
- `model` (optional) - Filter by model
- `date` (optional) - Filter by date
- `reasoning` (optional) - `none` (default), `summary`, `full`

### Response Structure

```json
{
  "count": 2,
  "results": [
    {
      "date": "2025-10-06",
      "model": "gpt-5",
      "job_id": "d8b52033-...",

      "starting_position": {
        "holdings": [
          {"symbol": "AMZN", "quantity": 11},
          {"symbol": "MSFT", "quantity": 10}
        ],
        "cash": 100.0,
        "portfolio_value": 9900.0
      },

      "daily_metrics": {
        "profit": 57.96,
        "return_pct": 0.585,
        "days_since_last_trading": 1
      },

      "trades": [
        {
          "action_type": "buy",
          "symbol": "NVDA",
          "quantity": 12,
          "price": 186.23,
          "created_at": "2025-10-06T14:30:00Z"
        }
      ],

      "final_position": {
        "holdings": [
          {"symbol": "AMZN", "quantity": 11},
          {"symbol": "MSFT", "quantity": 10},
          {"symbol": "NVDA", "quantity": 12}
        ],
        "cash": 114.86,
        "portfolio_value": 9957.96
      },

      "metadata": {
        "total_actions": 1,
        "session_duration_seconds": 45.2,
        "completed_at": "2025-10-06T14:31:00Z"
      },

      "reasoning": null  // or summary string or full array
    }
  ]
}
```

### Reasoning Levels

**`reasoning=none`** (default)
- `"reasoning": null`
- Fastest, no DB lookup of reasoning fields

**`reasoning=summary`**
- `"reasoning": "Analyzed AAPL earnings. Bought 10 shares..."`
- Pre-generated AI summary (2-3 sentences)

**`reasoning=full`**
- `"reasoning": [{role: "assistant", content: "..."}, {...}]`
- Complete conversation log (JSON array)

---

## Implementation Flow

### Simulation Execution (per model-day)

```python
async def run_trading_session(date):
    # 1. Get previous trading day data
    previous_day = db.get_previous_trading_day(job_id, model, date)

    # 2. Load today's prices
    current_prices = get_prices_for_date(date)

    # 3. Calculate daily P&L
    pnl_metrics = calculate_daily_pnl(previous_day, date, current_prices)

    # 4. Create trading_day record
    trading_day_id = db.create_trading_day(
        job_id, model, date,
        starting_cash=cash,
        starting_portfolio_value=pnl_metrics["starting_portfolio_value"],
        daily_profit=pnl_metrics["daily_profit"],
        daily_return_pct=pnl_metrics["daily_return_pct"],
        # ... other fields
    )

    # 5. Run AI trading session
    reasoning_log = []
    for step in range(max_steps):
        response = await ai_model.ainvoke(messages)
        reasoning_log.append(response)

        # Extract and execute trades
        trades = extract_trades(response)
        for trade in trades:
            execute_trade(trade)
            db.create_action(trading_day_id, trade)

        if "<FINISH_SIGNAL>" in response:
            break

    # 6. Generate reasoning summary
    summary = await generate_reasoning_summary(reasoning_log, ai_model)

    # 7. Save final holdings
    for symbol, quantity in holdings.items():
        db.create_holding(trading_day_id, symbol, quantity)

    # 8. Update trading_day with completion data
    db.update_trading_day(
        trading_day_id,
        ending_cash=cash,
        ending_portfolio_value=calculate_portfolio_value(),
        reasoning_summary=summary,
        reasoning_full=json.dumps(reasoning_log)
    )
```

---

## Error Handling & Edge Cases

### First Trading Day

**Scenario:** No previous day exists
**Solution:** Return zero P&L, starting value = initial cash

```python
if previous_day is None:
    return {
        "daily_profit": 0.0,
        "daily_return_pct": 0.0,
        "starting_portfolio_value": initial_cash
    }
```

### Weekend Gaps

**Scenario:** Friday → Monday (no trading Sat/Sun)
**Solution:** Query finds Friday as previous day automatically
**Metadata:** `days_since_last_trading: 3`

### Missing Price Data

**Scenario:** Holdings contain symbol with no price
**Solution:** Raise `ValueError` with clear message

```python
if symbol not in prices:
    raise ValueError(f"Missing price data for {symbol} on {date}")
```

### Reasoning Summary Failure

**Scenario:** AI API fails when generating summary
**Solution:** Fallback to statistical summary

```python
return f"Executed {trade_count} trades using {search_count} searches. Full log available."
```

### Interrupted Trading Day

**Scenario:** Simulation crashes mid-day
**Solution:** Mark trading_day as failed, preserve partial actions for debugging

```python
db.execute("UPDATE trading_days SET status='failed', error_message=? WHERE id=?")
# Keep partial action records
```

---

## Migration Strategy

### Chosen Approach: Clean Break

**Decision:** Delete old `positions` table, start fresh with new schema.

**Rationale:**
- Simpler than data migration
- Acceptable for development phase
- Clean slate ensures no legacy issues

**Implementation:**
```python
def migrate_clean_database():
    db.execute("DROP TABLE IF EXISTS positions")
    create_trading_days_schema(db)
```

---

## Testing Strategy

### Unit Tests

- Daily P&L calculation logic
  - First day (zero P&L)
  - Positive/negative returns
  - Weekend gaps
  - Multiple holdings
- Database helper methods
  - Create trading_day
  - Get previous trading day
  - Get starting/ending holdings

### Integration Tests

- BaseAgent P&L integration
  - First day creates record with zero P&L
  - Second day calculates P&L from price changes
- Results API
  - Response structure
  - Reasoning parameter variations
  - Filtering by job_id, model, date

### End-to-End Tests

- Complete simulation workflow
  - Multi-day simulation
  - Verify holdings chain across days
  - Verify P&L calculations
  - Verify reasoning summaries

### Performance Tests

- Query speed with large datasets
- Reasoning inclusion impact on response time

---

## Success Criteria

✅ **Functional Requirements:**
1. Daily P&L shows non-zero values when portfolio changes
2. Weekend gaps handled correctly (finds Friday when starting Monday)
3. Results API returns day-centric structure
4. Reasoning available at 3 levels (none/summary/full)
5. Holdings chain correctly across days
6. First day shows zero P&L

✅ **Technical Requirements:**
1. Test coverage >85%
2. No data duplication (normalized schema)
3. API response time <2s for 100 days
4. Database auto-initializes new schema
5. Old positions table removed

✅ **Documentation:**
1. API reference updated
2. Database schema documented
3. Implementation plan created
4. Migration guide provided

---

## Implementation Estimate

**Total Time:** 8-12 hours for experienced developer

**Breakdown:**
- Task 1: Database schema migration (1-2h)
- Task 2: Database helpers (1h)
- Task 3: P&L calculator (1h)
- Task 4: Reasoning summarizer (1h)
- Task 5: BaseAgent integration (2h)
- Task 6: Results API endpoint (1-2h)
- Task 7-11: Testing, docs, cleanup (2-3h)

---

## Future Enhancements (Not in Scope)

- Historical P&L charts
- Configurable summary model (cheaper alternative)
- Streaming reasoning logs
- P&L breakdown by position
- Benchmarking against indices

---

## References

- Implementation Plan: `docs/plans/2025-11-03-daily-pnl-results-api-refactor.md`
- Database Schema: `docs/developer/database-schema.md`
- API Reference: `API_REFERENCE.md`

---

**Status:** ✅ Design Approved - Ready for Implementation
**Next Step:** Execute implementation plan task-by-task
