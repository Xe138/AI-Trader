"""Tests for reasoning log storage in model_day_executor."""

import pytest
import sqlite3
from api.model_day_executor import ModelDayExecutor
from api.database import initialize_database, get_db_connection


@pytest.fixture
def test_db(tmp_path):
    """Create test database with job record."""
    db_path = str(tmp_path / "test.db")
    initialize_database(db_path)

    # Create a job record to satisfy foreign key constraint
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO jobs (job_id, config_path, status, date_range, models, created_at)
        VALUES ('test-job', 'configs/default_config.json', 'running', '["2025-01-01"]', '["test-model"]', '2025-01-01T00:00:00Z')
    """)
    conn.commit()
    conn.close()

    return db_path


def test_create_trading_session(test_db):
    """Should create trading session record."""
    executor = ModelDayExecutor(
        job_id="test-job",
        date="2025-01-01",
        model_sig="test-model",
        config_path="configs/default_config.json",
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
        config_path="configs/default_config.json",
        db_path=test_db
    )

    # Create mock agent
    agent = BaseAgent(
        signature="test-model",
        basemodel="mock",
        stock_symbols=["AAPL"],
        init_date="2025-01-01"
    )
    agent.model = MockChatModel(model="test", signature="test")

    # Create conversation
    conversation = [
        {"role": "user", "content": "Analyze market", "timestamp": "2025-01-01T10:00:00Z"},
        {"role": "assistant", "content": "Bought AAPL 10 shares based on strong earnings", "timestamp": "2025-01-01T10:05:00Z"}
    ]

    conn = get_db_connection(test_db)
    cursor = conn.cursor()
    session_id = executor._create_trading_session(cursor)

    await executor._store_reasoning_logs(cursor, session_id, conversation, agent)
    conn.commit()

    # Verify logs stored
    cursor.execute("SELECT * FROM reasoning_logs WHERE session_id = ? ORDER BY message_index", (session_id,))
    logs = cursor.fetchall()

    assert len(logs) == 2
    assert logs[0]['role'] == 'user'
    assert logs[0]['content'] == 'Analyze market'
    assert logs[0]['summary'] is None  # No summary for user messages

    assert logs[1]['role'] == 'assistant'
    assert logs[1]['content'] == 'Bought AAPL 10 shares based on strong earnings'
    assert logs[1]['summary'] is not None  # Summary generated for assistant

    conn.close()


@pytest.mark.asyncio
async def test_update_session_summary(test_db):
    """Should update session with overall summary."""
    from agent.mock_provider.mock_langchain_model import MockChatModel
    from agent.base_agent.base_agent import BaseAgent

    executor = ModelDayExecutor(
        job_id="test-job",
        date="2025-01-01",
        model_sig="test-model",
        config_path="configs/default_config.json",
        db_path=test_db
    )

    # Create mock agent
    agent = BaseAgent(
        signature="test-model",
        basemodel="mock",
        stock_symbols=["AAPL"],
        init_date="2025-01-01"
    )
    agent.model = MockChatModel(model="test", signature="test")

    # Create conversation
    conversation = [
        {"role": "user", "content": "Analyze market", "timestamp": "2025-01-01T10:00:00Z"},
        {"role": "assistant", "content": "Bought AAPL 10 shares", "timestamp": "2025-01-01T10:05:00Z"},
        {"role": "assistant", "content": "Sold MSFT 5 shares", "timestamp": "2025-01-01T10:10:00Z"}
    ]

    conn = get_db_connection(test_db)
    cursor = conn.cursor()
    session_id = executor._create_trading_session(cursor)

    await executor._update_session_summary(cursor, session_id, conversation, agent)
    conn.commit()

    # Verify session updated
    cursor.execute("SELECT * FROM trading_sessions WHERE id = ?", (session_id,))
    session = cursor.fetchone()

    assert session['session_summary'] is not None
    assert len(session['session_summary']) > 0
    assert session['completed_at'] is not None
    assert session['total_messages'] == 3

    conn.close()


@pytest.mark.asyncio
async def test_store_reasoning_logs_with_tool_messages(test_db):
    """Should store tool messages with tool_name and tool_input."""
    from agent.mock_provider.mock_langchain_model import MockChatModel
    from agent.base_agent.base_agent import BaseAgent

    executor = ModelDayExecutor(
        job_id="test-job",
        date="2025-01-01",
        model_sig="test-model",
        config_path="configs/default_config.json",
        db_path=test_db
    )

    # Create mock agent
    agent = BaseAgent(
        signature="test-model",
        basemodel="mock",
        stock_symbols=["AAPL"],
        init_date="2025-01-01"
    )
    agent.model = MockChatModel(model="test", signature="test")

    # Create conversation with tool message
    conversation = [
        {"role": "user", "content": "Get price", "timestamp": "2025-01-01T10:00:00Z"},
        {
            "role": "tool",
            "content": "AAPL: $150.00",
            "tool_name": "get_price",
            "tool_input": '{"symbol": "AAPL"}',
            "timestamp": "2025-01-01T10:01:00Z"
        },
        {"role": "assistant", "content": "AAPL is $150", "timestamp": "2025-01-01T10:02:00Z"}
    ]

    conn = get_db_connection(test_db)
    cursor = conn.cursor()
    session_id = executor._create_trading_session(cursor)

    await executor._store_reasoning_logs(cursor, session_id, conversation, agent)
    conn.commit()

    # Verify tool message stored correctly
    cursor.execute("SELECT * FROM reasoning_logs WHERE session_id = ? AND role = 'tool'", (session_id,))
    tool_log = cursor.fetchone()

    assert tool_log is not None
    assert tool_log['tool_name'] == 'get_price'
    assert tool_log['tool_input'] == '{"symbol": "AAPL"}'
    assert tool_log['content'] == 'AAPL: $150.00'
    assert tool_log['summary'] is None  # No summary for tool messages

    conn.close()


@pytest.mark.skip(reason="Method _write_results_to_db() removed - positions written by trade tools")
def test_write_results_includes_session_id(test_db):
    """DEPRECATED: This test verified _write_results_to_db() which has been removed."""
    pass
