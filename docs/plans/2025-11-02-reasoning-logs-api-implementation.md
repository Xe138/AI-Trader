# Reasoning Logs API Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement conversation history capture and API endpoint to retrieve AI reasoning logs from database with full/summary views

**Architecture:** Add conversation tracking to BaseAgent, modify model_day_executor to store reasoning in trading_sessions/reasoning_logs tables, create GET /reasoning endpoint, eliminate JSONL file logging

**Tech Stack:** SQLite, FastAPI, Python asyncio, LangChain (for AI model integration)

---

## Prerequisites

**Database schema changes completed:**
- ✅ `trading_sessions` table created
- ✅ `reasoning_logs` table redesigned
- ✅ `positions.session_id` column added
- ✅ All indexes created

**Reference documents:**
- Design: `docs/plans/2025-11-02-reasoning-logs-api-design.md`
- Current API: `API_REFERENCE.md`
- Database: `api/database.py` (already updated)

---

## Task 1: Add Conversation History Tracking to BaseAgent

**Files:**
- Modify: `agent/base_agent/base_agent.py`
- Test: `tests/unit/test_base_agent_conversation.py` (create)

### Step 1: Add conversation_history instance variable

In `agent/base_agent/base_agent.py`, add to `__init__` method after line 128:

```python
# Conversation history for reasoning logs
self.conversation_history: List[Dict[str, Any]] = []
```

### Step 2: Create method to capture messages

Add method to BaseAgent class:

```python
def _capture_message(self, role: str, content: str, tool_name: str = None, tool_input: str = None) -> None:
    """
    Capture a message in conversation history.

    Args:
        role: Message role ('user', 'assistant', 'tool')
        content: Message content
        tool_name: Tool name for tool messages
        tool_input: Tool input for tool messages
    """
    from datetime import datetime

    message = {
        "role": role,
        "content": content,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }

    if tool_name:
        message["tool_name"] = tool_name
    if tool_input:
        message["tool_input"] = tool_input

    self.conversation_history.append(message)
```

### Step 3: Create method to get conversation history

Add method to BaseAgent class:

```python
def get_conversation_history(self) -> List[Dict[str, Any]]:
    """
    Get the complete conversation history for this trading session.

    Returns:
        List of message dictionaries with role, content, timestamp
    """
    return self.conversation_history.copy()
```

### Step 4: Create method to clear conversation history

Add method to BaseAgent class:

```python
def clear_conversation_history(self) -> None:
    """Clear conversation history (called at start of each trading day)."""
    self.conversation_history = []
```

### Step 5: Capture system prompt in run_trading_session

In `agent/base_agent/base_agent.py`, modify `run_trading_session` method around line 237:

Find:
```python
def run_trading_session(self, date: str) -> Any:
    """Run trading session for a specific date"""
    # ... existing code ...

    system_prompt = get_agent_system_prompt(...)
```

Replace with:
```python
def run_trading_session(self, date: str) -> Any:
    """Run trading session for a specific date"""
    # Clear conversation history for new trading day
    self.clear_conversation_history()

    # ... existing code ...

    system_prompt = get_agent_system_prompt(...)

    # Capture user prompt
    self._capture_message("user", system_prompt)
```

### Step 6: Capture AI response

In same method, after AI invocation (around line 250):

Find:
```python
result = self.model.invoke(messages)
```

Add after:
```python
result = self.model.invoke(messages)

# Capture assistant response
if hasattr(result, 'content'):
    self._capture_message("assistant", result.content)
elif isinstance(result, dict) and 'content' in result:
    self._capture_message("assistant", result['content'])
```

### Step 7: Write unit test for conversation capture

Create `tests/unit/test_base_agent_conversation.py`:

```python
"""Tests for BaseAgent conversation history tracking."""

import pytest
from agent.base_agent.base_agent import BaseAgent


def test_conversation_history_initialized_empty():
    """Conversation history should start empty."""
    agent = BaseAgent(config={}, today_date="2025-01-01")
    assert agent.conversation_history == []
    assert agent.get_conversation_history() == []


def test_capture_message_user():
    """Should capture user message."""
    agent = BaseAgent(config={}, today_date="2025-01-01")
    agent._capture_message("user", "Test prompt")

    history = agent.get_conversation_history()
    assert len(history) == 1
    assert history[0]["role"] == "user"
    assert history[0]["content"] == "Test prompt"
    assert "timestamp" in history[0]


def test_capture_message_assistant():
    """Should capture assistant message."""
    agent = BaseAgent(config={}, today_date="2025-01-01")
    agent._capture_message("assistant", "Test response")

    history = agent.get_conversation_history()
    assert len(history) == 1
    assert history[0]["role"] == "assistant"
    assert history[0]["content"] == "Test response"


def test_capture_message_tool():
    """Should capture tool message with tool info."""
    agent = BaseAgent(config={}, today_date="2025-01-01")
    agent._capture_message(
        "tool",
        "Tool result",
        tool_name="get_price",
        tool_input='{"symbol": "AAPL"}'
    )

    history = agent.get_conversation_history()
    assert len(history) == 1
    assert history[0]["role"] == "tool"
    assert history[0]["tool_name"] == "get_price"
    assert history[0]["tool_input"] == '{"symbol": "AAPL"}'


def test_clear_conversation_history():
    """Should clear conversation history."""
    agent = BaseAgent(config={}, today_date="2025-01-01")
    agent._capture_message("user", "Test")
    assert len(agent.get_conversation_history()) == 1

    agent.clear_conversation_history()
    assert len(agent.get_conversation_history()) == 0


def test_get_conversation_history_returns_copy():
    """Should return a copy to prevent external modification."""
    agent = BaseAgent(config={}, today_date="2025-01-01")
    agent._capture_message("user", "Test")

    history1 = agent.get_conversation_history()
    history2 = agent.get_conversation_history()

    # Modify one copy
    history1.append({"role": "user", "content": "Extra"})

    # Other copy should be unaffected
    assert len(history2) == 1
    assert len(agent.conversation_history) == 1
```

### Step 8: Run tests

```bash
pytest tests/unit/test_base_agent_conversation.py -v
```

Expected: All tests PASS

### Step 9: Commit

```bash
git add agent/base_agent/base_agent.py tests/unit/test_base_agent_conversation.py
git commit -m "feat: add conversation history tracking to BaseAgent"
```

---

## Task 2: Add Summary Generation to BaseAgent

**Files:**
- Modify: `agent/base_agent/base_agent.py`
- Test: `tests/unit/test_base_agent_summary.py` (create)

### Step 1: Add async summary generation method

Add method to BaseAgent class:

```python
async def generate_summary(self, content: str, max_length: int = 200) -> str:
    """
    Generate a concise summary of reasoning content.

    Uses the same AI model to summarize its own reasoning.

    Args:
        content: Full reasoning content to summarize
        max_length: Approximate character limit for summary

    Returns:
        1-2 sentence summary of key decisions and reasoning
    """
    # Truncate content to avoid token limits (keep first 2000 chars)
    truncated = content[:2000] if len(content) > 2000 else content

    prompt = f"""Summarize the following trading decision in 1-2 sentences (max {max_length} characters), focusing on the key reasoning and actions taken:

{truncated}

Summary:"""

    try:
        # Use ainvoke for async call
        response = await self.model.ainvoke(prompt)

        # Extract content from response
        if hasattr(response, 'content'):
            summary = response.content.strip()
        elif isinstance(response, dict) and 'content' in response:
            summary = response['content'].strip()
        else:
            summary = str(response).strip()

        # Truncate if too long
        if len(summary) > max_length:
            summary = summary[:max_length-3] + "..."

        return summary

    except Exception as e:
        # If summary generation fails, return truncated original
        return truncated[:max_length-3] + "..."
```

### Step 2: Add synchronous wrapper for backwards compatibility

Add method to BaseAgent class:

```python
def generate_summary_sync(self, content: str, max_length: int = 200) -> str:
    """
    Synchronous wrapper for generate_summary.

    Args:
        content: Full reasoning content to summarize
        max_length: Approximate character limit for summary

    Returns:
        Summary string
    """
    import asyncio

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(self.generate_summary(content, max_length))
```

### Step 3: Write unit test for summary generation

Create `tests/unit/test_base_agent_summary.py`:

```python
"""Tests for BaseAgent summary generation."""

import pytest
from agent.base_agent.base_agent import BaseAgent
from agent.mock_provider.mock_langchain_model import MockChatModel


@pytest.mark.asyncio
async def test_generate_summary_basic():
    """Should generate summary from content."""
    agent = BaseAgent(config={}, today_date="2025-01-01")

    # Use mock model for testing
    agent.model = MockChatModel(model="test", signature="test")

    content = """Key intermediate steps

- Read yesterday's positions: all zeros, $10,000 cash
- Analyzed NVDA strong Q2 results, bought 10 shares
- Analyzed AMD AI momentum, bought 6 shares
- Portfolio now 51% cash reserve for volatility management

<FINISH_SIGNAL>"""

    summary = await agent.generate_summary(content)

    assert isinstance(summary, str)
    assert len(summary) > 0
    assert len(summary) <= 203  # 200 + "..."


def test_generate_summary_sync():
    """Synchronous summary generation should work."""
    agent = BaseAgent(config={}, today_date="2025-01-01")
    agent.model = MockChatModel(model="test", signature="test")

    content = "Bought AAPL 10 shares based on strong earnings."
    summary = agent.generate_summary_sync(content)

    assert isinstance(summary, str)
    assert len(summary) > 0


@pytest.mark.asyncio
async def test_generate_summary_truncates_long_content():
    """Should truncate very long content before summarizing."""
    agent = BaseAgent(config={}, today_date="2025-01-01")
    agent.model = MockChatModel(model="test", signature="test")

    # Create content > 2000 chars
    content = "Analysis: " + ("x" * 3000)

    summary = await agent.generate_summary(content)

    # Summary should be generated (not throw error)
    assert isinstance(summary, str)
    assert len(summary) <= 203


@pytest.mark.asyncio
async def test_generate_summary_handles_errors():
    """Should handle errors gracefully."""
    agent = BaseAgent(config={}, today_date="2025-01-01")

    # No model set - will fail
    agent.model = None

    content = "Test content"
    summary = await agent.generate_summary(content)

    # Should return truncated original on error
    assert summary == "Test content"
```

### Step 4: Run tests

```bash
pytest tests/unit/test_base_agent_summary.py -v
```

Expected: All tests PASS

### Step 5: Commit

```bash
git add agent/base_agent/base_agent.py tests/unit/test_base_agent_summary.py
git commit -m "feat: add AI-powered summary generation to BaseAgent"
```

---

## Task 3: Update model_day_executor to Store Reasoning Logs

**Files:**
- Modify: `api/model_day_executor.py`
- Test: `tests/unit/test_model_day_executor_reasoning.py` (create)

### Step 1: Add method to create trading session

In `api/model_day_executor.py`, add method to `ModelDayExecutor` class:

```python
def _create_trading_session(self, cursor: sqlite3.Cursor) -> int:
    """
    Create trading session record.

    Args:
        cursor: Database cursor

    Returns:
        session_id (int)
    """
    from datetime import datetime

    started_at = datetime.utcnow().isoformat() + "Z"

    cursor.execute("""
        INSERT INTO trading_sessions (
            job_id, date, model, started_at
        )
        VALUES (?, ?, ?, ?)
    """, (self.job_id, self.date, self.model_sig, started_at))

    return cursor.lastrowid
```

### Step 2: Add method to store reasoning logs

Add method to `ModelDayExecutor` class:

```python
async def _store_reasoning_logs(
    self,
    cursor: sqlite3.Cursor,
    session_id: int,
    conversation: List[Dict[str, Any]],
    agent: Any
) -> None:
    """
    Store reasoning logs with AI-generated summaries.

    Args:
        cursor: Database cursor
        session_id: Trading session ID
        conversation: List of messages from agent
        agent: BaseAgent instance for summary generation
    """
    for idx, message in enumerate(conversation):
        summary = None

        # Generate summary for assistant messages
        if message["role"] == "assistant":
            summary = await agent.generate_summary(message["content"])

        cursor.execute("""
            INSERT INTO reasoning_logs (
                session_id, message_index, role, content,
                summary, tool_name, tool_input, timestamp
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session_id,
            idx,
            message["role"],
            message["content"],
            summary,
            message.get("tool_name"),
            message.get("tool_input"),
            message["timestamp"]
        ))
```

### Step 3: Add method to update session summary

Add method to `ModelDayExecutor` class:

```python
async def _update_session_summary(
    self,
    cursor: sqlite3.Cursor,
    session_id: int,
    conversation: List[Dict[str, Any]],
    agent: Any
) -> None:
    """
    Update session with overall summary.

    Args:
        cursor: Database cursor
        session_id: Trading session ID
        conversation: List of messages from agent
        agent: BaseAgent instance for summary generation
    """
    from datetime import datetime

    # Concatenate all assistant messages
    assistant_messages = [
        msg["content"]
        for msg in conversation
        if msg["role"] == "assistant"
    ]

    combined_content = "\n\n".join(assistant_messages)

    # Generate session summary (longer: 500 chars)
    session_summary = await agent.generate_summary(combined_content, max_length=500)

    completed_at = datetime.utcnow().isoformat() + "Z"

    cursor.execute("""
        UPDATE trading_sessions
        SET session_summary = ?,
            completed_at = ?,
            total_messages = ?
        WHERE id = ?
    """, (session_summary, completed_at, len(conversation), session_id))
```

### Step 4: Modify execute() method to use new flow

In `api/model_day_executor.py`, find the `execute()` method around line 180. Modify it:

Find:
```python
def execute(self) -> Dict[str, Any]:
    """Execute model-day simulation and store results in database."""
```

Replace entire method with:
```python
async def execute(self) -> Dict[str, Any]:
    """Execute model-day simulation and store results in database."""
    import asyncio

    # ... keep existing validation code ...

    # Create trading session at start
    conn = get_db_connection(self.db_path)
    cursor = conn.cursor()
    session_id = self._create_trading_session(cursor)
    conn.commit()

    try:
        # Run agent
        agent = self._create_agent()
        result = agent.run_trading_session(self.date)

        # Get conversation history
        conversation = agent.get_conversation_history()

        # Store reasoning logs with summaries
        await self._store_reasoning_logs(cursor, session_id, conversation, agent)

        # Update session summary
        await self._update_session_summary(cursor, session_id, conversation, agent)

        # Store positions (existing code, but add session_id)
        self._write_results_to_db(agent, session_id)

        conn.commit()

        return {"status": "success", "session_id": session_id}

    except Exception as e:
        conn.rollback()
        raise
    finally:
        conn.close()
```

### Step 5: Update _write_results_to_db to accept session_id

Find `_write_results_to_db` method signature:

```python
def _write_results_to_db(self, agent) -> None:
```

Change to:
```python
def _write_results_to_db(self, agent, session_id: int) -> None:
```

Then in the INSERT INTO positions statement (around line 285), add session_id:

```python
cursor.execute("""
    INSERT INTO positions (
        job_id, date, model, action_id, action_type, symbol,
        amount, price, cash, portfolio_value, daily_profit, daily_return_pct,
        session_id, created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
""", (
    self.job_id, self.date, self.model_sig, action_id, action_type,
    symbol, amount, price, cash, total_value,
    daily_profit, daily_return_pct, session_id, created_at
))
```

### Step 6: Remove old reasoning_logs code

In `_write_results_to_db`, find and remove this block (around line 303):

```python
# Insert reasoning logs (if available)
if hasattr(agent, 'get_reasoning_steps'):
    reasoning_steps = agent.get_reasoning_steps()
    for step in reasoning_steps:
        cursor.execute("""
            INSERT INTO reasoning_logs (
                job_id, date, model, step_number, timestamp, content
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            self.job_id, self.date, self.model_sig,
            step.get("step"), created_at, step.get("reasoning")
        ))
```

Delete this entire block.

### Step 7: Make execute() wrapper to handle async

Since `execute()` is now async but called synchronously, wrap it:

Add new synchronous execute method:

```python
def execute_sync(self) -> Dict[str, Any]:
    """Synchronous wrapper for execute()."""
    import asyncio

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(self.execute())
```

And rename current execute to execute_async:

```python
async def execute_async(self) -> Dict[str, Any]:
    # ... current execute() implementation ...
```

Then add:

```python
def execute(self) -> Dict[str, Any]:
    """Execute model-day simulation (sync wrapper)."""
    return self.execute_sync()
```

### Step 8: Write unit test

Create `tests/unit/test_model_day_executor_reasoning.py`:

```python
"""Tests for reasoning log storage in model_day_executor."""

import pytest
import sqlite3
from api.model_day_executor import ModelDayExecutor
from api.database import initialize_database, get_db_connection


@pytest.fixture
def test_db(tmp_path):
    """Create test database."""
    db_path = str(tmp_path / "test.db")
    initialize_database(db_path)
    return db_path


def test_create_trading_session(test_db):
    """Should create trading session record."""
    executor = ModelDayExecutor(
        job_id="test-job",
        date="2025-01-01",
        model_sig="test-model",
        config={},
        db_path=test_db
    )

    conn = get_db_connection(test_db)
    cursor = conn.cursor()

    session_id = executor._create_trading_session(cursor)
    conn.commit()

    # Verify session created
    cursor.execute("SELECT * FROM trading_sessions WHERE id = ?", (session_id,))
    session = cursor.fetchone()

    assert session is not None
    assert session['job_id'] == "test-job"
    assert session['date'] == "2025-01-01"
    assert session['model'] == "test-model"
    assert session['started_at'] is not None

    conn.close()


@pytest.mark.asyncio
async def test_store_reasoning_logs(test_db):
    """Should store conversation with summaries."""
    from agent.mock_provider.mock_langchain_model import MockChatModel
    from agent.base_agent.base_agent import BaseAgent

    executor = ModelDayExecutor(
        job_id="test-job",
        date="2025-01-01",
        model_sig="test-model",
        config={},
        db_path=test_db
    )

    # Create mock agent
    agent = BaseAgent(config={}, today_date="2025-01-01")
    agent.model = MockChatModel(model="test", signature="test")

    # Create conversation
    conversation = [
        {"role": "user", "content": "Analyze market", "timestamp": "2025-01-01T10:00:00Z"},
        {"role": "assistant", "content": "Bought AAPL 10 shares", "timestamp": "2025-01-01T10:05:00Z"}
    ]

    conn = get_db_connection(test_db)
    cursor = conn.cursor()
    session_id = executor._create_trading_session(cursor)

    await executor._store_reasoning_logs(cursor, session_id, conversation, agent)
    conn.commit()

    # Verify logs stored
    cursor.execute("SELECT * FROM reasoning_logs WHERE session_id = ?", (session_id,))
    logs = cursor.fetchall()

    assert len(logs) == 2
    assert logs[0]['role'] == 'user'
    assert logs[1]['role'] == 'assistant'
    assert logs[1]['summary'] is not None  # Summary generated for assistant

    conn.close()
```

### Step 9: Run tests

```bash
pytest tests/unit/test_model_day_executor_reasoning.py -v
```

Expected: All tests PASS

### Step 10: Commit

```bash
git add api/model_day_executor.py tests/unit/test_model_day_executor_reasoning.py
git commit -m "feat: store reasoning logs with sessions in model_day_executor"
```

---

## Task 4: Add GET /reasoning API Endpoint

**Files:**
- Modify: `api/main.py`
- Test: `tests/unit/test_api_reasoning_endpoint.py` (create)

### Step 1: Add Pydantic models for reasoning endpoint

In `api/main.py`, after existing model definitions (around line 115), add:

```python
class ReasoningMessage(BaseModel):
    """Individual message in conversation."""
    message_index: int
    role: str
    content: str
    summary: Optional[str] = None
    tool_name: Optional[str] = None
    tool_input: Optional[str] = None
    timestamp: str


class PositionSummary(BaseModel):
    """Position summary for reasoning response."""
    action_id: int
    action_type: str
    symbol: Optional[str] = None
    amount: Optional[int] = None
    price: Optional[float] = None
    cash_after: float
    portfolio_value: float


class TradingSessionResponse(BaseModel):
    """Single trading session with reasoning and positions."""
    session_id: int
    job_id: str
    date: str
    model: str
    session_summary: Optional[str] = None
    started_at: str
    completed_at: Optional[str] = None
    total_messages: Optional[int] = None
    positions: List[PositionSummary]
    conversation: Optional[List[ReasoningMessage]] = None


class ReasoningResponse(BaseModel):
    """Response body for GET /reasoning."""
    sessions: List[TradingSessionResponse]
    count: int
```

### Step 2: Add GET /reasoning endpoint

In `api/main.py`, before the `return app` line (around line 520), add:

```python
@app.get("/reasoning", response_model=ReasoningResponse)
async def get_reasoning(
    job_id: Optional[str] = Query(None, description="Filter by job ID"),
    date: Optional[str] = Query(None, description="Filter by date (YYYY-MM-DD)"),
    model: Optional[str] = Query(None, description="Filter by model signature"),
    include_full_conversation: bool = Query(False, description="Include full conversation (default: summaries only)")
):
    """
    Retrieve reasoning logs for trading sessions.

    Returns session summaries by default. Set include_full_conversation=true
    to get full conversation history.

    Args:
        job_id: Optional job UUID filter
        date: Optional date filter (YYYY-MM-DD)
        model: Optional model signature filter
        include_full_conversation: Include all messages (default: false)

    Returns:
        List of trading sessions with reasoning and positions
    """
    try:
        conn = get_db_connection(app.state.db_path)
        cursor = conn.cursor()

        # Build query for trading sessions
        query = """
            SELECT
                id, job_id, date, model, session_summary,
                started_at, completed_at, total_messages
            FROM trading_sessions
            WHERE 1=1
        """
        params = []

        if job_id:
            query += " AND job_id = ?"
            params.append(job_id)
        if date:
            query += " AND date = ?"
            params.append(date)
        if model:
            query += " AND model = ?"
            params.append(model)

        query += " ORDER BY date DESC, model"

        cursor.execute(query, params)
        sessions = cursor.fetchall()

        results = []

        for session in sessions:
            session_id = session[0]

            # Get positions for this session
            cursor.execute("""
                SELECT
                    action_id, action_type, symbol, amount, price,
                    cash, portfolio_value
                FROM positions
                WHERE session_id = ?
                ORDER BY action_id
            """, (session_id,))

            positions = [
                PositionSummary(
                    action_id=row[0],
                    action_type=row[1],
                    symbol=row[2],
                    amount=row[3],
                    price=row[4],
                    cash_after=row[5],
                    portfolio_value=row[6]
                )
                for row in cursor.fetchall()
            ]

            # Get conversation if requested
            conversation = None
            if include_full_conversation:
                cursor.execute("""
                    SELECT
                        message_index, role, content, summary,
                        tool_name, tool_input, timestamp
                    FROM reasoning_logs
                    WHERE session_id = ?
                    ORDER BY message_index
                """, (session_id,))

                conversation = [
                    ReasoningMessage(
                        message_index=row[0],
                        role=row[1],
                        content=row[2],
                        summary=row[3],
                        tool_name=row[4],
                        tool_input=row[5],
                        timestamp=row[6]
                    )
                    for row in cursor.fetchall()
                ]

            results.append(TradingSessionResponse(
                session_id=session_id,
                job_id=session[1],
                date=session[2],
                model=session[3],
                session_summary=session[4],
                started_at=session[5],
                completed_at=session[6],
                total_messages=session[7],
                positions=positions,
                conversation=conversation
            ))

        conn.close()

        return ReasoningResponse(sessions=results, count=len(results))

    except Exception as e:
        logger.error(f"Failed to retrieve reasoning logs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
```

### Step 3: Write API endpoint test

Create `tests/unit/test_api_reasoning_endpoint.py`:

```python
"""Tests for GET /reasoning endpoint."""

import pytest
from fastapi.testclient import TestClient
from api.main import create_app
from api.database import initialize_database, get_db_connection


@pytest.fixture
def test_app(tmp_path):
    """Create test app with database."""
    db_path = str(tmp_path / "test.db")
    initialize_database(db_path)

    app = create_app(db_path=db_path)
    app.state.test_mode = True

    return TestClient(app), db_path


def test_get_reasoning_empty(test_app):
    """Should return empty list when no sessions exist."""
    client, _ = test_app

    response = client.get("/reasoning")

    assert response.status_code == 200
    data = response.json()
    assert data["sessions"] == []
    assert data["count"] == 0


def test_get_reasoning_with_session(test_app):
    """Should return session with summary."""
    client, db_path = test_app

    # Create test data
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    # Create job
    cursor.execute("""
        INSERT INTO jobs (job_id, config_path, status, date_range, models, created_at)
        VALUES ('test-job', 'config.json', 'completed', '["2025-01-01"]', '["test-model"]', '2025-01-01T00:00:00Z')
    """)

    # Create session
    cursor.execute("""
        INSERT INTO trading_sessions (job_id, date, model, session_summary, started_at, total_messages)
        VALUES ('test-job', '2025-01-01', 'test-model', 'Bought AAPL based on earnings', '2025-01-01T10:00:00Z', 2)
    """)
    session_id = cursor.lastrowid

    # Create position
    cursor.execute("""
        INSERT INTO positions (
            job_id, date, model, action_id, action_type, symbol, amount, price,
            cash, portfolio_value, daily_profit, daily_return_pct, session_id, created_at
        )
        VALUES ('test-job', '2025-01-01', 'test-model', 1, 'buy', 'AAPL', 10, 150.0, 8500.0, 10000.0, 0.0, 0.0, ?, '2025-01-01T10:00:00Z')
    """, (session_id,))

    conn.commit()
    conn.close()

    # Query reasoning
    response = client.get("/reasoning?date=2025-01-01")

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    assert len(data["sessions"]) == 1

    session = data["sessions"][0]
    assert session["date"] == "2025-01-01"
    assert session["model"] == "test-model"
    assert session["session_summary"] == "Bought AAPL based on earnings"
    assert len(session["positions"]) == 1
    assert session["conversation"] is None  # Not included by default


def test_get_reasoning_with_full_conversation(test_app):
    """Should include conversation when requested."""
    client, db_path = test_app

    # Create test data
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO jobs (job_id, config_path, status, date_range, models, created_at)
        VALUES ('test-job', 'config.json', 'completed', '["2025-01-01"]', '["test-model"]', '2025-01-01T00:00:00Z')
    """)

    cursor.execute("""
        INSERT INTO trading_sessions (job_id, date, model, started_at, total_messages)
        VALUES ('test-job', '2025-01-01', 'test-model', '2025-01-01T10:00:00Z', 2)
    """)
    session_id = cursor.lastrowid

    # Add reasoning logs
    cursor.execute("""
        INSERT INTO reasoning_logs (session_id, message_index, role, content, timestamp)
        VALUES (?, 0, 'user', 'Analyze market', '2025-01-01T10:00:00Z')
    """, (session_id,))

    cursor.execute("""
        INSERT INTO reasoning_logs (session_id, message_index, role, content, summary, timestamp)
        VALUES (?, 1, 'assistant', 'Full reasoning...', 'Bought AAPL', '2025-01-01T10:05:00Z')
    """, (session_id,))

    conn.commit()
    conn.close()

    # Query with full conversation
    response = client.get("/reasoning?date=2025-01-01&include_full_conversation=true")

    assert response.status_code == 200
    data = response.json()

    session = data["sessions"][0]
    assert session["conversation"] is not None
    assert len(session["conversation"]) == 2
    assert session["conversation"][0]["role"] == "user"
    assert session["conversation"][1]["role"] == "assistant"
    assert session["conversation"][1]["summary"] == "Bought AAPL"
```

### Step 4: Run tests

```bash
pytest tests/unit/test_api_reasoning_endpoint.py -v
```

Expected: All tests PASS

### Step 5: Commit

```bash
git add api/main.py tests/unit/test_api_reasoning_endpoint.py
git commit -m "feat: add GET /reasoning API endpoint"
```

---

## Task 5: Update API Documentation

**Files:**
- Modify: `API_REFERENCE.md`

### Step 1: Add reasoning endpoint documentation

In `API_REFERENCE.md`, after the `/results` endpoint section (around line 462), add:

```markdown
---

### GET /reasoning

Retrieve AI reasoning logs for trading sessions with optional filters.

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
      "session_summary": "Analyzed AI infrastructure market conditions. Decided to establish positions in NVDA, GOOGL, AMD, and CRWD based on secular AI demand trends. Maintained 51% cash reserve.",
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
      "conversation": null
    }
  ],
  "count": 1
}
```

**With full conversation** (`include_full_conversation=true`):

```json
{
  "sessions": [
    {
      "session_id": 123,
      "job_id": "550e8400-e29b-41d4-a716-446655440000",
      "date": "2025-10-02",
      "model": "gpt-5",
      "session_summary": "Analyzed AI infrastructure market conditions...",
      "started_at": "2025-10-02T10:00:00Z",
      "completed_at": "2025-10-02T10:05:23Z",
      "total_messages": 4,
      "positions": [...],
      "conversation": [
        {
          "message_index": 0,
          "role": "user",
          "content": "Please analyze and update today's (2025-10-02) positions.",
          "summary": null,
          "tool_name": null,
          "tool_input": null,
          "timestamp": "2025-10-02T10:00:00Z"
        },
        {
          "message_index": 1,
          "role": "assistant",
          "content": "Key intermediate steps\n\n- Read yesterday's positions...",
          "summary": "Decided to buy NVDA (10 shares), GOOGL (6 shares), AMD (6 shares), CRWD (1 share) based on AI infrastructure trends.",
          "tool_name": null,
          "tool_input": null,
          "timestamp": "2025-10-02T10:05:20Z"
        }
      ]
    }
  ],
  "count": 1
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `sessions` | array[object] | Array of trading session records |
| `count` | integer | Number of sessions returned |

**Trading Session Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `session_id` | integer | Unique session ID |
| `job_id` | string | Job UUID |
| `date` | string | Trading date (YYYY-MM-DD) |
| `model` | string | Model signature |
| `session_summary` | string | AI-generated summary of entire trading session |
| `started_at` | string | ISO 8601 timestamp when session started |
| `completed_at` | string | ISO 8601 timestamp when session completed |
| `total_messages` | integer | Number of messages in conversation |
| `positions` | array[object] | Trading positions from this session |
| `conversation` | array[object] | Full conversation (only if `include_full_conversation=true`) |

**Position Summary Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `action_id` | integer | Action sequence number |
| `action_type` | string | Action type: `buy`, `sell`, or `no_trade` |
| `symbol` | string | Stock symbol (or null for no_trade) |
| `amount` | integer | Quantity (or null for no_trade) |
| `price` | float | Price per share (or null for no_trade) |
| `cash_after` | float | Cash balance after this action |
| `portfolio_value` | float | Total portfolio value after this action |

**Conversation Message Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `message_index` | integer | Message order in conversation (0, 1, 2...) |
| `role` | string | Message role: `user`, `assistant`, or `tool` |
| `content` | string | Full message content |
| `summary` | string | AI-generated summary (for assistant messages only) |
| `tool_name` | string | Tool name (for tool messages only) |
| `tool_input` | string | Tool input (for tool messages only) |
| `timestamp` | string | ISO 8601 timestamp |

**Examples:**

Get summaries for all sessions in a job:
```bash
curl "http://localhost:8080/reasoning?job_id=550e8400-e29b-41d4-a716-446655440000"
```

Get full conversation for specific model-day:
```bash
curl "http://localhost:8080/reasoning?date=2025-10-02&model=gpt-5&include_full_conversation=true"
```

Get all reasoning for a specific date:
```bash
curl "http://localhost:8080/reasoning?date=2025-10-02"
```

**Use Cases:**

- **Audit trading decisions:** Review AI reasoning for specific days
- **Compare models:** See how different models reasoned about same market conditions
- **Debug issues:** Investigate why a model made unexpected trades
- **Research:** Analyze decision patterns across multiple sessions
```

### Step 2: Update database schema documentation

In `API_REFERENCE.md`, find the "Data Persistence" section (around line 689) and update the table list:

Change:
```markdown
- **reasoning_logs** - AI decision reasoning (if enabled)
```

To:
```markdown
- **trading_sessions** - One record per model-day trading session
- **reasoning_logs** - AI conversation history linked to sessions
```

### Step 3: Commit

```bash
git add API_REFERENCE.md
git commit -m "docs: add GET /reasoning endpoint to API reference"
```

---

## Task 6: Remove JSONL Logging Code

**Files:**
- Modify: `agent/base_agent/base_agent.py`

### Step 1: Remove _get_log_file method

In `agent/base_agent/base_agent.py`, find and delete the `_get_log_file` method (around line 210):

```python
def _get_log_file(self, today_date: str) -> str:
    """Get log file path for today"""
    log_path = os.path.join(self.base_log_path, self.signature, 'log', today_date)
    if not os.path.exists(log_path):
        os.makedirs(log_path)
    return os.path.join(log_path, "log.jsonl")
```

Delete entire method.

### Step 2: Remove _log_message method

Find and delete the `_log_message` method (around line 215):

```python
def _log_message(self, log_file: str, new_messages: List[Dict[str, str]]) -> None:
    """Log messages to log file"""
    # ... implementation ...
```

Delete entire method.

### Step 3: Remove log file writing from run_trading_session

In `run_trading_session` method, find and remove any calls to `_log_message` or log file operations.

Look for patterns like:
```python
log_file = self._get_log_file(date)
self._log_message(log_file, ...)
```

Delete these calls.

### Step 4: Commit

```bash
git add agent/base_agent/base_agent.py
git commit -m "refactor: remove JSONL logging in favor of database storage"
```

---

## Task 7: Integration Testing

**Files:**
- Create: `tests/integration/test_reasoning_e2e.py`

### Step 1: Write end-to-end test

Create `tests/integration/test_reasoning_e2e.py`:

```python
"""End-to-end test for reasoning logs feature."""

import pytest
from fastapi.testclient import TestClient
from api.main import create_app
from api.database import initialize_database


@pytest.fixture
def test_system(tmp_path):
    """Set up complete test system."""
    db_path = str(tmp_path / "test.db")
    initialize_database(db_path)

    app = create_app(db_path=db_path)
    app.state.test_mode = True

    client = TestClient(app)

    return client, db_path


def test_complete_reasoning_workflow(test_system):
    """Test complete flow: trigger simulation -> get reasoning logs."""
    client, db_path = test_system

    # Step 1: Trigger simulation
    trigger_response = client.post("/simulate/trigger", json={
        "start_date": "2025-01-16",
        "end_date": "2025-01-16",
        "models": ["test-model"]
    })

    assert trigger_response.status_code == 200
    job_id = trigger_response.json()["job_id"]

    # Step 2: Wait for completion (in test mode, immediate)
    # In real implementation, would poll /simulate/status

    # Step 3: Get reasoning logs (summary only)
    reasoning_response = client.get(f"/reasoning?job_id={job_id}")

    assert reasoning_response.status_code == 200
    data = reasoning_response.json()

    # Verify structure
    assert data["count"] > 0
    assert len(data["sessions"]) > 0

    session = data["sessions"][0]
    assert session["job_id"] == job_id
    assert session["date"] == "2025-01-16"
    assert session["session_summary"] is not None
    assert len(session["positions"]) > 0
    assert session["conversation"] is None  # Not included

    # Step 4: Get full conversation
    full_response = client.get(
        f"/reasoning?job_id={job_id}&include_full_conversation=true"
    )

    assert full_response.status_code == 200
    full_data = full_response.json()

    full_session = full_data["sessions"][0]
    assert full_session["conversation"] is not None
    assert len(full_session["conversation"]) > 0

    # Verify message structure
    messages = full_session["conversation"]
    assert messages[0]["role"] in ["user", "assistant", "tool"]
    assert "content" in messages[0]
    assert "timestamp" in messages[0]
```

### Step 2: Run integration test

```bash
pytest tests/integration/test_reasoning_e2e.py -v
```

Expected: Test PASS

### Step 3: Commit

```bash
git add tests/integration/test_reasoning_e2e.py
git commit -m "test: add end-to-end test for reasoning logs feature"
```

---

## Task 8: Final Verification

### Step 1: Run all tests

```bash
pytest tests/ -v
```

Expected: All tests PASS

### Step 2: Test in dev mode

```bash
DEPLOYMENT_MODE=DEV python -m pytest tests/integration/test_reasoning_e2e.py -v
```

Expected: Test PASS with mock AI

### Step 3: Manual API test (optional)

Start server:
```bash
uvicorn api.main:app --reload
```

Trigger simulation:
```bash
curl -X POST http://localhost:8080/simulate/trigger \
  -H "Content-Type: application/json" \
  -d '{"start_date": "2025-01-16", "end_date": "2025-01-16", "models": ["test-model"]}'
```

Get reasoning:
```bash
curl "http://localhost:8080/reasoning?date=2025-01-16&include_full_conversation=true"
```

### Step 4: Final commit

```bash
git add -A
git commit -m "feat: complete reasoning logs API implementation

- Add conversation history tracking to BaseAgent
- Add AI-powered summary generation
- Store reasoning logs in trading_sessions/reasoning_logs tables
- Add GET /reasoning API endpoint with full/summary views
- Remove JSONL file logging
- Update API documentation
- Add comprehensive test coverage"
```

---

## Production Deployment

### Step 1: Database migration (production)

**On production server, run:**

```bash
# Backup database first
cp data/jobs.db data/jobs.db.backup.$(date +%Y%m%d)

# Connect to database
sqlite3 data/jobs.db

-- Verify schema
.schema trading_sessions
.schema reasoning_logs

-- Check if session_id column exists in positions
PRAGMA table_info(positions);

-- Exit
.quit
```

If tables don't exist, the migration in `database.py` will create them automatically on next API restart.

### Step 2: Clean up old JSONL files (after verification)

**After verifying reasoning logs are being stored in database:**

```bash
# Create backup of JSONL files
tar -czf data/agent_data_logs_backup_$(date +%Y%m%d).tar.gz data/agent_data/*/log/

# Verify backup created
ls -lh data/agent_data_logs_backup_*.tar.gz

# Remove JSONL files (optional, after confirming database storage works)
# find data/agent_data/*/log -type f -name "*.jsonl" -delete
# find data/agent_data/*/log -type d -empty -delete
```

### Step 3: Restart API server

```bash
# Docker deployment
docker-compose restart

# Or manual deployment
systemctl restart ai-trader-api
```

### Step 4: Verify API works

```bash
curl http://localhost:8080/health

curl "http://localhost:8080/reasoning?date=2025-10-02" | jq '.'
```

---

## Success Criteria

- ✅ All tests passing
- ✅ Conversation history captured in BaseAgent
- ✅ Summaries generated for assistant messages
- ✅ Reasoning logs stored in database with session linkage
- ✅ Positions linked to sessions via session_id
- ✅ GET /reasoning endpoint returns sessions with summaries
- ✅ Full conversation available with include_full_conversation=true
- ✅ JSONL logging removed
- ✅ API documentation updated
- ✅ No regressions in existing functionality

---

## Rollback Plan

If issues arise:

1. **Revert commits:**
   ```bash
   git log --oneline  # Find commit before changes
   git revert <commit-hash>..HEAD
   ```

2. **Database rollback (if needed):**
   ```bash
   # Restore backup
   cp data/jobs.db.backup.YYYYMMDD data/jobs.db
   ```

3. **Keep JSONL files** until database storage proven stable
