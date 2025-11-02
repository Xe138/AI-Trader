# Reasoning Logs API Design

**Date:** 2025-11-02
**Status:** Approved for Implementation

## Overview

Add API endpoint to retrieve AI reasoning logs for simulation days, replacing JSONL file-based logging with database-only storage. The system will store both full conversation history and AI-generated summaries, with clear associations to trading positions.

## Goals

1. **Database-only storage** - Eliminate JSONL files (`data/agent_data/[model]/log/[date]/log.jsonl`)
2. **Dual storage** - Store both full conversation and AI-generated summaries in same table
3. **Trading event association** - Easy to review reasoning alongside positions taken
4. **Query flexibility** - Filter by job_id, date, and/or model

## Database Schema Changes

### New Table: trading_sessions

One record per model-day trading session.

```sql
CREATE TABLE IF NOT EXISTS trading_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    date TEXT NOT NULL,
    model TEXT NOT NULL,
    session_summary TEXT,          -- AI-generated summary of entire session
    started_at TEXT NOT NULL,
    completed_at TEXT,
    total_messages INTEGER,
    FOREIGN KEY (job_id) REFERENCES jobs(job_id) ON DELETE CASCADE,
    UNIQUE(job_id, date, model)
)
```

### Modified Table: reasoning_logs

Store individual messages linked to trading session.

```sql
CREATE TABLE IF NOT EXISTS reasoning_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    message_index INTEGER NOT NULL,  -- Order in conversation (0, 1, 2...)
    role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'tool')),
    content TEXT NOT NULL,           -- Full message content
    summary TEXT,                     -- AI-generated summary (for assistant messages)
    tool_name TEXT,                   -- Tool name (for tool role)
    tool_input TEXT,                  -- Tool input args (for tool role)
    timestamp TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES trading_sessions(id) ON DELETE CASCADE,
    UNIQUE(session_id, message_index)
)
```

**Key changes from current schema:**
- Added `session_id` foreign key instead of `(job_id, date, model)` tuple
- Added `message_index` to preserve conversation order
- Added `summary` column for AI-generated summaries of assistant responses
- Added `tool_input` to capture tool call arguments
- Changed `content` to NOT NULL
- Removed `step_number` (replaced by `message_index`)
- Added UNIQUE constraint to enforce ordering

### Modified Table: positions

Add link to trading session.

```sql
ALTER TABLE positions ADD COLUMN session_id INTEGER REFERENCES trading_sessions(id)
```

**Migration:** Column addition is non-breaking. Existing rows will have NULL `session_id`.

## Data Flow

### 1. Trading Session Lifecycle

**Start of simulation day:**
```python
session_id = create_trading_session(
    job_id=job_id,
    date=date,
    model=model_sig,
    started_at=datetime.utcnow().isoformat() + "Z"
)
```

**During agent execution:**
- BaseAgent captures all messages in memory via `get_conversation_history()`
- No file I/O during execution

**After agent completes:**
```python
conversation = agent.get_conversation_history()

# Store all messages
for idx, message in enumerate(conversation):
    summary = None
    if message["role"] == "assistant":
        # Use same AI model to generate summary
        summary = await agent.generate_summary(message["content"])

    insert_reasoning_log(
        session_id=session_id,
        message_index=idx,
        role=message["role"],
        content=message["content"],
        summary=summary,
        tool_name=message.get("tool_name"),
        tool_input=message.get("tool_input"),
        timestamp=message.get("timestamp")
    )

# Generate and store session summary
session_summary = await agent.generate_summary(
    "\n\n".join([m["content"] for m in conversation if m["role"] == "assistant"])
)
update_trading_session(session_id, session_summary=session_summary)
```

### 2. Position Linking

When inserting positions, include `session_id`:

```python
cursor.execute("""
    INSERT INTO positions (
        job_id, date, model, action_id, action_type, symbol,
        amount, price, cash, portfolio_value, daily_profit,
        daily_return_pct, session_id, created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
""", (..., session_id, created_at))
```

## Summary Generation

### Strategy: Use Same Model

For each assistant message, generate a concise summary using the same AI model:

```python
async def generate_summary(self, content: str) -> str:
    """
    Generate 1-2 sentence summary of reasoning.

    Uses same model that generated the content to ensure
    consistency and accuracy.
    """
    prompt = f"""Summarize the following trading decision in 1-2 sentences,
focusing on the key reasoning and actions taken:

{content[:2000]}  # Truncate to avoid token limits

Summary:"""

    response = await self.model.ainvoke(prompt)
    return response.content.strip()
```

**Cost consideration:** Summaries add minimal token cost (50-100 tokens per message) compared to full reasoning.

**Session summary:** Concatenate all assistant messages and summarize the entire trading day's reasoning.

## API Endpoint

### GET /reasoning

Retrieve reasoning logs with optional filters.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `job_id` | string | No | Filter by job UUID |
| `date` | string | No | Filter by date (YYYY-MM-DD) |
| `model` | string | No | Filter by model signature |
| `include_full_conversation` | boolean | No | Include all messages (default: false, only returns summaries) |

**Response (200 OK):**

```json
{
  "sessions": [
    {
      "session_id": 123,
      "job_id": "550e8400-e29b-41d4-a716-446655440000",
      "date": "2025-10-02",
      "model": "gpt-5",
      "session_summary": "Analyzed AI infrastructure market conditions. Decided to establish positions in NVDA, GOOGL, AMD, and CRWD based on secular AI demand trends and strong Q2 results. Maintained 51% cash reserve for volatility management.",
      "started_at": "2025-10-02T10:00:00Z",
      "completed_at": "2025-10-02T10:05:23Z",
      "total_messages": 4,
      "positions": [
        {
          "action_id": 1,
          "action_type": "buy",
          "symbol": "NVDA",
          "amount": 10,
          "price": 189.60,
          "cash_after": 8104.00,
          "portfolio_value": 10000.00
        },
        {
          "action_id": 2,
          "action_type": "buy",
          "symbol": "GOOGL",
          "amount": 6,
          "price": 245.15,
          "cash_after": 6633.10,
          "portfolio_value": 10104.00
        }
      ],
      "conversation": [  // Only if include_full_conversation=true
        {
          "message_index": 0,
          "role": "user",
          "content": "Please analyze and update today's (2025-10-02) positions.",
          "timestamp": "2025-10-02T10:00:00Z"
        },
        {
          "message_index": 1,
          "role": "assistant",
          "content": "Key intermediate steps\n\n- Read yesterday's positions...",
          "summary": "Analyzed market conditions and decided to buy NVDA (10 shares), GOOGL (6 shares), AMD (6 shares), and CRWD (1 share) based on AI infrastructure trends.",
          "timestamp": "2025-10-02T10:05:20Z"
        }
      ]
    }
  ],
  "count": 1
}
```

**Error Responses:**

- **400 Bad Request** - Invalid date format
- **404 Not Found** - No sessions found matching filters

**Examples:**

```bash
# Get summaries for all sessions in a job
curl "http://localhost:8080/reasoning?job_id=550e8400-..."

# Get full conversation for specific model-day
curl "http://localhost:8080/reasoning?date=2025-10-02&model=gpt-5&include_full_conversation=true"

# Get all reasoning for a specific date
curl "http://localhost:8080/reasoning?date=2025-10-02"
```

## Implementation Plan

### Phase 1: Database Schema (Step 1)

**Files to modify:**
- `api/database.py`
  - Add `trading_sessions` table to `initialize_database()`
  - Modify `reasoning_logs` table schema
  - Add migration logic for `positions.session_id` column

**Tasks:**
1. Update `initialize_database()` with new schema
2. Create `initialize_dev_database()` variant for testing
3. Write unit tests for schema creation

### Phase 2: Data Capture (Steps 2-3)

**Files to modify:**
- `agent/base_agent/base_agent.py`
  - Add `conversation_history` instance variable
  - Add `get_conversation_history()` method
  - Add `generate_summary()` method
  - Capture messages during execution
  - Remove JSONL file logging

- `api/model_day_executor.py`
  - Add `_create_trading_session()` method
  - Add `_store_reasoning_logs()` method
  - Add `_update_session_summary()` method
  - Modify position insertion to include `session_id`
  - Remove old `get_reasoning_steps()` logic

**Tasks:**
1. Implement conversation history capture in BaseAgent
2. Implement summary generation in BaseAgent
3. Update model_day_executor to create sessions and store logs
4. Write unit tests for conversation capture
5. Write unit tests for summary generation

### Phase 3: API Endpoint (Step 4)

**Files to modify:**
- `api/main.py`
  - Add `/reasoning` endpoint
  - Add request/response models
  - Add query logic with filters

**Tasks:**
1. Create Pydantic models for request/response
2. Implement endpoint handler
3. Write unit tests for endpoint
4. Write integration tests

### Phase 4: Documentation & Cleanup (Step 5)

**Files to modify:**
- `API_REFERENCE.md` - Document new endpoint
- `CLAUDE.md` - Update architecture docs
- `docs/developer/database-schema.md` - Document new tables

**Tasks:**
1. Update API documentation
2. Update architecture documentation
3. Create cleanup script for old JSONL files
4. Remove JSONL-related code from BaseAgent

### Phase 5: Testing (Step 6)

**Test scenarios:**
1. Run simulation and verify reasoning logs stored
2. Query reasoning endpoint with various filters
3. Verify positions linked to sessions
4. Test with/without `include_full_conversation`
5. Verify summaries are meaningful
6. Test dev mode behavior

## Migration Strategy

### Database Migration

**Production:**
```sql
-- Run on existing production database
ALTER TABLE positions ADD COLUMN session_id INTEGER REFERENCES trading_sessions(id);
```

**Note:** Existing positions will have NULL `session_id`. This is acceptable as they predate the new system.

### JSONL File Cleanup

**After verifying new system works:**

```bash
# Production cleanup script
#!/bin/bash
# cleanup_old_logs.sh

# Verify database has reasoning_logs data
echo "Checking database for reasoning logs..."
REASONING_COUNT=$(sqlite3 data/jobs.db "SELECT COUNT(*) FROM reasoning_logs")

if [ "$REASONING_COUNT" -gt 0 ]; then
    echo "Found $REASONING_COUNT reasoning log entries in database"
    echo "Removing old JSONL files..."

    # Backup first (optional)
    tar -czf data/agent_data_logs_backup_$(date +%Y%m%d).tar.gz data/agent_data/*/log/

    # Remove log directories
    find data/agent_data/*/log -type f -name "*.jsonl" -delete
    find data/agent_data/*/log -type d -empty -delete

    echo "Cleanup complete"
else
    echo "WARNING: No reasoning logs found in database. Keeping JSONL files."
fi
```

## Rollback Plan

If issues arise:

1. **Keep JSONL logging temporarily** - Don't remove `_log_message()` calls until database storage is proven
2. **Database rollback** - Drop new tables if needed:
   ```sql
   DROP TABLE IF EXISTS reasoning_logs;
   DROP TABLE IF EXISTS trading_sessions;
   ALTER TABLE positions DROP COLUMN session_id;
   ```
3. **API rollback** - Remove `/reasoning` endpoint

## Success Criteria

1. ✅ Trading sessions created for each model-day execution
2. ✅ Full conversation history stored in `reasoning_logs` table
3. ✅ Summaries generated for assistant messages
4. ✅ Positions linked to trading sessions via `session_id`
5. ✅ `/reasoning` endpoint returns sessions with filters
6. ✅ API documentation updated
7. ✅ All tests passing
8. ✅ JSONL files eliminated
