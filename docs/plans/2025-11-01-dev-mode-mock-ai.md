# Development Mode with Mock AI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add `DEPLOYMENT_MODE` environment variable that disables AI API calls in DEV mode and isolates dev data to separate database and file paths.

**Architecture:**
- Separate data paths (`data/agent_data/` vs `data/dev_agent_data/`) and databases (`trading.db` vs `trading_dev.db`) based on `DEPLOYMENT_MODE`
- Mock AI provider returns static but rotating responses (Day 1: AAPL, Day 2: MSFT, Day 3: GOOGL, etc.)
- Dev database reset on startup (unless `PRESERVE_DEV_DATA=true`)
- Warning logs when production API keys detected in DEV mode
- API responses include `deployment_mode` field

**Tech Stack:** Python 3.10+, LangChain, SQLite, environment variables

---

## Task 1: Update Environment Configuration

**Files:**
- Modify: `.env.example`
- Read: `.env.example:1-42`

**Step 1: Document deployment mode variables**

Add the following to `.env.example` after line 42:

```bash
# =============================================================================
# Deployment Mode Configuration
# =============================================================================
# DEPLOYMENT_MODE controls AI model calls and data isolation
# - PROD: Real AI API calls, uses data/agent_data/ and data/trading.db
# - DEV: Mock AI responses, uses data/dev_agent_data/ and data/trading_dev.db
DEPLOYMENT_MODE=PROD

# Preserve dev data between runs (DEV mode only)
# Set to true to keep dev database and files for debugging
PRESERVE_DEV_DATA=false
```

**Step 2: Verify changes**

Run: `cat .env.example`
Expected: New section appears at end of file

**Step 3: Commit**

```bash
git add .env.example
git commit -m "docs: add DEPLOYMENT_MODE configuration to env example"
```

---

## Task 2: Create Mock AI Provider

**Files:**
- Create: `agent/mock_provider/mock_ai_provider.py`
- Create: `agent/mock_provider/__init__.py`

**Step 1: Write test for mock provider rotation**

Create `tests/unit/test_mock_provider.py`:

```python
import pytest
from agent.mock_provider.mock_ai_provider import MockAIProvider


def test_mock_provider_rotates_stocks():
    """Test that mock provider returns different stocks on different days"""
    provider = MockAIProvider()

    # Day 1 should recommend AAPL
    response1 = provider.generate_response("2025-01-01", step=0)
    assert "AAPL" in response1
    assert "<FINISH_SIGNAL>" in response1

    # Day 2 should recommend MSFT
    response2 = provider.generate_response("2025-01-02", step=0)
    assert "MSFT" in response2
    assert "<FINISH_SIGNAL>" in response2

    # Responses should be different
    assert response1 != response2


def test_mock_provider_finish_signal():
    """Test that all responses include finish signal"""
    provider = MockAIProvider()
    response = provider.generate_response("2025-01-01", step=0)
    assert "<FINISH_SIGNAL>" in response


def test_mock_provider_valid_json_tool_calls():
    """Test that responses contain valid tool call syntax"""
    provider = MockAIProvider()
    response = provider.generate_response("2025-01-01", step=0)
    assert "[calls tool_get_price" in response or "get_price" in response.lower()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_mock_provider.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'agent.mock_provider'"

**Step 3: Create mock provider implementation**

Create `agent/mock_provider/__init__.py`:

```python
"""Mock AI provider for development mode testing"""
from .mock_ai_provider import MockAIProvider

__all__ = ["MockAIProvider"]
```

Create `agent/mock_provider/mock_ai_provider.py`:

```python
"""
Mock AI Provider for Development Mode

Returns static but rotating trading responses to test orchestration without AI API costs.
Rotates through NASDAQ 100 stocks in a predictable pattern.
"""

from typing import Optional
from datetime import datetime


class MockAIProvider:
    """Mock AI provider that returns pre-defined trading responses"""

    # Rotation of stocks for variety in testing
    STOCK_ROTATION = [
        "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA",
        "META", "TSLA", "BRK.B", "UNH", "JNJ"
    ]

    def __init__(self):
        """Initialize mock provider"""
        pass

    def generate_response(self, date: str, step: int = 0) -> str:
        """
        Generate mock trading response based on date

        Args:
            date: Trading date (YYYY-MM-DD)
            step: Current step in reasoning loop (0-indexed)

        Returns:
            Mock AI response string with tool calls and finish signal
        """
        # Use date to deterministically select stock
        date_obj = datetime.strptime(date, "%Y-%m-%d")
        day_offset = (date_obj - datetime(2025, 1, 1)).days
        stock_idx = day_offset % len(self.STOCK_ROTATION)
        selected_stock = self.STOCK_ROTATION[stock_idx]

        # Generate mock response
        response = f"""Let me analyze the market for today ({date}).

I'll check the current price for {selected_stock}.
[calls tool_get_price with symbol={selected_stock}]

Based on the analysis, I'll make a small purchase to test the system.
[calls tool_trade with action=buy, symbol={selected_stock}, amount=5]

I've completed today's trading session.
<FINISH_SIGNAL>"""

        return response

    def __str__(self):
        return "MockAIProvider(mode=development)"

    def __repr__(self):
        return self.__str__()
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_mock_provider.py -v`
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add agent/mock_provider/ tests/unit/test_mock_provider.py
git commit -m "feat: add mock AI provider for dev mode with stock rotation"
```

---

## Task 3: Create Mock LangChain Model Wrapper

**Files:**
- Create: `agent/mock_provider/mock_langchain_model.py`
- Modify: `agent/mock_provider/__init__.py`

**Step 1: Write test for LangChain model wrapper**

Add to `tests/unit/test_mock_provider.py`:

```python
import asyncio
from agent.mock_provider.mock_langchain_model import MockChatModel


def test_mock_chat_model_invoke():
    """Test synchronous invoke returns proper message format"""
    model = MockChatModel(date="2025-01-01")

    messages = [{"role": "user", "content": "Analyze the market"}]
    response = model.invoke(messages)

    assert hasattr(response, "content")
    assert "AAPL" in response.content
    assert "<FINISH_SIGNAL>" in response.content


def test_mock_chat_model_ainvoke():
    """Test asynchronous invoke returns proper message format"""
    async def run_test():
        model = MockChatModel(date="2025-01-02")
        messages = [{"role": "user", "content": "Analyze the market"}]
        response = await model.ainvoke(messages)

        assert hasattr(response, "content")
        assert "MSFT" in response.content
        assert "<FINISH_SIGNAL>" in response.content

    asyncio.run(run_test())


def test_mock_chat_model_different_dates():
    """Test that different dates produce different responses"""
    model1 = MockChatModel(date="2025-01-01")
    model2 = MockChatModel(date="2025-01-02")

    msg = [{"role": "user", "content": "Trade"}]
    response1 = model1.invoke(msg)
    response2 = model2.invoke(msg)

    assert response1.content != response2.content
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_mock_provider.py::test_mock_chat_model_invoke -v`
Expected: FAIL with "ImportError: cannot import name 'MockChatModel'"

**Step 3: Implement mock LangChain model**

Create `agent/mock_provider/mock_langchain_model.py`:

```python
"""
Mock LangChain-compatible chat model for development mode

Wraps MockAIProvider to work with LangChain's agent framework.
"""

from typing import Any, List, Optional, Dict
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatResult, ChatGeneration
from .mock_ai_provider import MockAIProvider


class MockChatModel(BaseChatModel):
    """
    Mock chat model compatible with LangChain's agent framework

    Attributes:
        date: Current trading date for response generation
        step_counter: Tracks reasoning steps within a trading session
    """

    date: str = "2025-01-01"
    step_counter: int = 0

    def __init__(self, date: str = "2025-01-01", **kwargs):
        """
        Initialize mock chat model

        Args:
            date: Trading date for mock responses
            **kwargs: Additional LangChain model parameters
        """
        super().__init__(**kwargs)
        self.date = date
        self.step_counter = 0
        self.provider = MockAIProvider()

    @property
    def _llm_type(self) -> str:
        """Return identifier for this LLM type"""
        return "mock-chat-model"

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[Any] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """
        Generate mock response (synchronous)

        Args:
            messages: Input messages (ignored in mock)
            stop: Stop sequences (ignored in mock)
            run_manager: LangChain run manager
            **kwargs: Additional generation parameters

        Returns:
            ChatResult with mock AI response
        """
        response_text = self.provider.generate_response(self.date, self.step_counter)
        self.step_counter += 1

        message = AIMessage(
            content=response_text,
            response_metadata={"finish_reason": "stop"}
        )

        generation = ChatGeneration(message=message)
        return ChatResult(generations=[generation])

    async def _agenerate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[Any] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """
        Generate mock response (asynchronous)

        Same as _generate but async-compatible for LangChain agents.
        """
        return self._generate(messages, stop, run_manager, **kwargs)

    def invoke(self, input: Any, **kwargs) -> AIMessage:
        """Synchronous invoke (LangChain compatibility)"""
        if isinstance(input, list):
            messages = input
        else:
            messages = []

        result = self._generate(messages, **kwargs)
        return result.generations[0].message

    async def ainvoke(self, input: Any, **kwargs) -> AIMessage:
        """Asynchronous invoke (LangChain compatibility)"""
        if isinstance(input, list):
            messages = input
        else:
            messages = []

        result = await self._agenerate(messages, **kwargs)
        return result.generations[0].message
```

Update `agent/mock_provider/__init__.py`:

```python
"""Mock AI provider for development mode testing"""
from .mock_ai_provider import MockAIProvider
from .mock_langchain_model import MockChatModel

__all__ = ["MockAIProvider", "MockChatModel"]
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_mock_provider.py -v`
Expected: PASS (6 tests)

**Step 5: Commit**

```bash
git add agent/mock_provider/mock_langchain_model.py agent/mock_provider/__init__.py tests/unit/test_mock_provider.py
git commit -m "feat: add LangChain-compatible mock chat model wrapper"
```

---

## Task 4: Add Deployment Mode Configuration Module

**Files:**
- Create: `tools/deployment_config.py`
- Modify: `tools/__init__.py`

**Step 1: Write tests for deployment config**

Create `tests/unit/test_deployment_config.py`:

```python
import os
import pytest
from tools.deployment_config import (
    get_deployment_mode,
    is_dev_mode,
    is_prod_mode,
    get_data_path,
    get_db_path,
    should_preserve_dev_data,
    log_api_key_warning
)


def test_get_deployment_mode_default():
    """Test default deployment mode is PROD"""
    # Clear env to test default
    os.environ.pop("DEPLOYMENT_MODE", None)
    assert get_deployment_mode() == "PROD"


def test_get_deployment_mode_dev():
    """Test DEV mode detection"""
    os.environ["DEPLOYMENT_MODE"] = "DEV"
    assert get_deployment_mode() == "DEV"
    assert is_dev_mode() == True
    assert is_prod_mode() == False


def test_get_deployment_mode_prod():
    """Test PROD mode detection"""
    os.environ["DEPLOYMENT_MODE"] = "PROD"
    assert get_deployment_mode() == "PROD"
    assert is_dev_mode() == False
    assert is_prod_mode() == True


def test_get_data_path_prod():
    """Test production data path"""
    os.environ["DEPLOYMENT_MODE"] = "PROD"
    assert get_data_path("./data/agent_data") == "./data/agent_data"


def test_get_data_path_dev():
    """Test dev data path substitution"""
    os.environ["DEPLOYMENT_MODE"] = "DEV"
    assert get_data_path("./data/agent_data") == "./data/dev_agent_data"


def test_get_db_path_prod():
    """Test production database path"""
    os.environ["DEPLOYMENT_MODE"] = "PROD"
    assert get_db_path("data/trading.db") == "data/trading.db"


def test_get_db_path_dev():
    """Test dev database path substitution"""
    os.environ["DEPLOYMENT_MODE"] = "DEV"
    assert get_db_path("data/trading.db") == "data/trading_dev.db"
    assert get_db_path("data/jobs.db") == "data/jobs_dev.db"


def test_should_preserve_dev_data_default():
    """Test default preserve flag is False"""
    os.environ.pop("PRESERVE_DEV_DATA", None)
    assert should_preserve_dev_data() == False


def test_should_preserve_dev_data_true():
    """Test preserve flag can be enabled"""
    os.environ["PRESERVE_DEV_DATA"] = "true"
    assert should_preserve_dev_data() == True


def test_log_api_key_warning_in_dev(capsys):
    """Test warning logged when API keys present in DEV mode"""
    os.environ["DEPLOYMENT_MODE"] = "DEV"
    os.environ["OPENAI_API_KEY"] = "sk-test123"

    log_api_key_warning()

    captured = capsys.readouterr()
    assert "⚠️  WARNING: Production API keys detected in DEV mode" in captured.out
    assert "OPENAI_API_KEY" in captured.out
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_deployment_config.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'tools.deployment_config'"

**Step 3: Implement deployment config module**

Create `tools/deployment_config.py`:

```python
"""
Deployment mode configuration utilities

Handles PROD vs DEV mode differentiation including:
- Data path isolation
- Database path isolation
- API key validation warnings
- Deployment mode detection
"""

import os
from typing import Optional


def get_deployment_mode() -> str:
    """
    Get current deployment mode

    Returns:
        "PROD" or "DEV" (defaults to PROD if not set)
    """
    mode = os.getenv("DEPLOYMENT_MODE", "PROD").upper()
    if mode not in ["PROD", "DEV"]:
        print(f"⚠️  Invalid DEPLOYMENT_MODE '{mode}', defaulting to PROD")
        return "PROD"
    return mode


def is_dev_mode() -> bool:
    """Check if running in DEV mode"""
    return get_deployment_mode() == "DEV"


def is_prod_mode() -> bool:
    """Check if running in PROD mode"""
    return get_deployment_mode() == "PROD"


def get_data_path(base_path: str) -> str:
    """
    Get data path based on deployment mode

    Args:
        base_path: Base data path (e.g., "./data/agent_data")

    Returns:
        Modified path for DEV mode or original for PROD

    Example:
        PROD: "./data/agent_data" -> "./data/agent_data"
        DEV:  "./data/agent_data" -> "./data/dev_agent_data"
    """
    if is_dev_mode():
        # Replace agent_data with dev_agent_data
        return base_path.replace("agent_data", "dev_agent_data")
    return base_path


def get_db_path(base_db_path: str) -> str:
    """
    Get database path based on deployment mode

    Args:
        base_db_path: Base database path (e.g., "data/trading.db")

    Returns:
        Modified path for DEV mode or original for PROD

    Example:
        PROD: "data/trading.db" -> "data/trading.db"
        DEV:  "data/trading.db" -> "data/trading_dev.db"
    """
    if is_dev_mode():
        # Insert _dev before .db extension
        if base_db_path.endswith(".db"):
            return base_db_path[:-3] + "_dev.db"
        return base_db_path + "_dev"
    return base_db_path


def should_preserve_dev_data() -> bool:
    """
    Check if dev data should be preserved between runs

    Returns:
        True if PRESERVE_DEV_DATA=true, False otherwise
    """
    preserve = os.getenv("PRESERVE_DEV_DATA", "false").lower()
    return preserve in ["true", "1", "yes"]


def log_api_key_warning() -> None:
    """
    Log warning if production API keys are detected in DEV mode

    Checks for common API key environment variables and warns if found.
    """
    if not is_dev_mode():
        return

    # List of API key environment variables to check
    api_key_vars = [
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "ALPHAADVANTAGE_API_KEY",
        "JINA_API_KEY"
    ]

    detected_keys = []
    for var in api_key_vars:
        value = os.getenv(var)
        if value and value != "" and "your_" not in value.lower():
            detected_keys.append(var)

    if detected_keys:
        print("⚠️  WARNING: Production API keys detected in DEV mode")
        print(f"   Detected: {', '.join(detected_keys)}")
        print("   These keys will NOT be used - mock AI responses will be returned")
        print("   This is expected if you're testing dev mode with existing .env file")


def get_deployment_mode_dict() -> dict:
    """
    Get deployment mode information as dictionary (for API responses)

    Returns:
        Dictionary with deployment mode metadata
    """
    return {
        "deployment_mode": get_deployment_mode(),
        "is_dev_mode": is_dev_mode(),
        "preserve_dev_data": should_preserve_dev_data() if is_dev_mode() else None
    }
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_deployment_config.py -v`
Expected: PASS (10 tests)

**Step 5: Commit**

```bash
git add tools/deployment_config.py tests/unit/test_deployment_config.py
git commit -m "feat: add deployment mode configuration utilities"
```

---

## Task 5: Add Dev Database Initialization and Cleanup

**Files:**
- Modify: `api/database.py:42-213`
- Create: `tests/unit/test_dev_database.py`

**Step 1: Write tests for dev database handling**

Create `tests/unit/test_dev_database.py`:

```python
import os
import pytest
from pathlib import Path
from api.database import initialize_dev_database, cleanup_dev_database


def test_initialize_dev_database_creates_fresh_db(tmp_path):
    """Test dev database initialization creates clean schema"""
    db_path = str(tmp_path / "test_dev.db")

    # Create initial database with some data
    from api.database import get_db_connection, initialize_database
    initialize_database(db_path)
    conn = get_db_connection(db_path)
    conn.execute("INSERT INTO jobs (job_id, config_path, status, date_range, models, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                 ("test-job", "config.json", "completed", "2025-01-01:2025-01-31", '["model1"]', "2025-01-01T00:00:00"))
    conn.commit()
    conn.close()

    # Verify data exists
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM jobs")
    assert cursor.fetchone()[0] == 1
    conn.close()

    # Initialize dev database (should reset)
    initialize_dev_database(db_path)

    # Verify data is cleared
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM jobs")
    assert cursor.fetchone()[0] == 0
    conn.close()


def test_cleanup_dev_database_removes_files(tmp_path):
    """Test dev cleanup removes database and data files"""
    # Setup dev files
    db_path = str(tmp_path / "test_dev.db")
    data_path = str(tmp_path / "dev_agent_data")

    Path(db_path).touch()
    Path(data_path).mkdir(parents=True, exist_ok=True)
    (Path(data_path) / "test_file.jsonl").touch()

    # Verify files exist
    assert Path(db_path).exists()
    assert Path(data_path).exists()

    # Cleanup
    cleanup_dev_database(db_path, data_path)

    # Verify files removed
    assert not Path(db_path).exists()
    assert not Path(data_path).exists()


def test_initialize_dev_respects_preserve_flag(tmp_path):
    """Test that PRESERVE_DEV_DATA flag prevents cleanup"""
    os.environ["PRESERVE_DEV_DATA"] = "true"
    db_path = str(tmp_path / "test_dev.db")

    # Create database with data
    from api.database import get_db_connection, initialize_database
    initialize_database(db_path)
    conn = get_db_connection(db_path)
    conn.execute("INSERT INTO jobs (job_id, config_path, status, date_range, models, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                 ("test-job", "config.json", "completed", "2025-01-01:2025-01-31", '["model1"]', "2025-01-01T00:00:00"))
    conn.commit()
    conn.close()

    # Initialize with preserve flag
    initialize_dev_database(db_path)

    # Verify data is preserved
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM jobs")
    assert cursor.fetchone()[0] == 1
    conn.close()

    os.environ.pop("PRESERVE_DEV_DATA")
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_dev_database.py -v`
Expected: FAIL with "ImportError: cannot import name 'initialize_dev_database'"

**Step 3: Add dev database functions to database.py**

Add to `api/database.py` after line 213 (after `initialize_database` function):

```python
def initialize_dev_database(db_path: str = "data/trading_dev.db") -> None:
    """
    Initialize dev database with clean schema

    Deletes and recreates dev database unless PRESERVE_DEV_DATA=true.
    Used at startup in DEV mode to ensure clean testing environment.

    Args:
        db_path: Path to dev database file
    """
    from tools.deployment_config import should_preserve_dev_data

    if should_preserve_dev_data():
        print(f"ℹ️  PRESERVE_DEV_DATA=true, keeping existing dev database: {db_path}")
        # Ensure schema exists even if preserving data
        if not Path(db_path).exists():
            print(f"📁 Dev database doesn't exist, creating: {db_path}")
            initialize_database(db_path)
        return

    # Delete existing dev database
    if Path(db_path).exists():
        print(f"🗑️  Removing existing dev database: {db_path}")
        Path(db_path).unlink()

    # Create fresh dev database
    print(f"📁 Creating fresh dev database: {db_path}")
    initialize_database(db_path)


def cleanup_dev_database(db_path: str = "data/trading_dev.db", data_path: str = "./data/dev_agent_data") -> None:
    """
    Cleanup dev database and data files

    Args:
        db_path: Path to dev database file
        data_path: Path to dev data directory
    """
    import shutil

    # Remove dev database
    if Path(db_path).exists():
        print(f"🗑️  Removing dev database: {db_path}")
        Path(db_path).unlink()

    # Remove dev data directory
    if Path(data_path).exists():
        print(f"🗑️  Removing dev data directory: {data_path}")
        shutil.rmtree(data_path)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_dev_database.py -v`
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add api/database.py tests/unit/test_dev_database.py
git commit -m "feat: add dev database initialization and cleanup functions"
```

---

## Task 6: Update Database Module to Support Deployment Modes

**Files:**
- Modify: `api/database.py:16-39`

**Step 1: Write test for automatic db path resolution**

Add to `tests/unit/test_dev_database.py`:

```python
def test_get_db_connection_resolves_dev_path():
    """Test that get_db_connection uses dev path in DEV mode"""
    import os
    os.environ["DEPLOYMENT_MODE"] = "DEV"

    # This should automatically resolve to dev database
    # We're just testing the path logic, not actually creating DB
    from api.database import resolve_db_path

    prod_path = "data/trading.db"
    dev_path = resolve_db_path(prod_path)

    assert dev_path == "data/trading_dev.db"

    os.environ["DEPLOYMENT_MODE"] = "PROD"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_dev_database.py::test_get_db_connection_resolves_dev_path -v`
Expected: FAIL with "ImportError: cannot import name 'resolve_db_path'"

**Step 3: Update database module with deployment mode support**

Modify `api/database.py`, add import at top after line 13:

```python
from tools.deployment_config import get_db_path
```

Modify `get_db_connection` function (lines 16-39):

```python
def get_db_connection(db_path: str = "data/jobs.db") -> sqlite3.Connection:
    """
    Get SQLite database connection with proper configuration.

    Automatically resolves to dev database if DEPLOYMENT_MODE=DEV.

    Args:
        db_path: Path to SQLite database file

    Returns:
        Configured SQLite connection

    Configuration:
        - Foreign keys enabled for referential integrity
        - Row factory for dict-like access
        - Check same thread disabled for FastAPI async compatibility
    """
    # Resolve path based on deployment mode
    resolved_path = get_db_path(db_path)

    # Ensure data directory exists
    db_path_obj = Path(resolved_path)
    db_path_obj.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(resolved_path, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row

    return conn


def resolve_db_path(db_path: str) -> str:
    """
    Resolve database path based on deployment mode

    Convenience function for testing.

    Args:
        db_path: Base database path

    Returns:
        Resolved path (dev or prod)
    """
    return get_db_path(db_path)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_dev_database.py::test_get_db_connection_resolves_dev_path -v`
Expected: PASS

**Step 5: Run all database tests**

Run: `pytest tests/unit/test_database.py tests/unit/test_dev_database.py -v`
Expected: All tests PASS

**Step 6: Commit**

```bash
git add api/database.py
git commit -m "feat: integrate deployment mode path resolution in database module"
```

---

## Task 7: Update BaseAgent to Support Mock AI Provider

**Files:**
- Modify: `agent/base_agent/base_agent.py:146-189`

**Step 1: Write test for BaseAgent mock integration**

Create `tests/unit/test_base_agent_mock.py`:

```python
import os
import pytest
import asyncio
from agent.base_agent.base_agent import BaseAgent


def test_base_agent_uses_mock_in_dev_mode():
    """Test BaseAgent uses mock model when DEPLOYMENT_MODE=DEV"""
    os.environ["DEPLOYMENT_MODE"] = "DEV"

    agent = BaseAgent(
        signature="test-agent",
        basemodel="mock/test-trader",
        log_path="./data/dev_agent_data"
    )

    # Initialize should create mock model
    asyncio.run(agent.initialize())

    assert agent.model is not None
    assert "Mock" in str(type(agent.model))

    os.environ["DEPLOYMENT_MODE"] = "PROD"


def test_base_agent_warns_about_api_keys_in_dev(capsys):
    """Test BaseAgent logs warning about API keys in DEV mode"""
    os.environ["DEPLOYMENT_MODE"] = "DEV"
    os.environ["OPENAI_API_KEY"] = "sk-test123"

    agent = BaseAgent(
        signature="test-agent",
        basemodel="mock/test-trader"
    )

    asyncio.run(agent.initialize())

    captured = capsys.readouterr()
    assert "WARNING" in captured.out or "DEV" in captured.out

    os.environ.pop("OPENAI_API_KEY")
    os.environ["DEPLOYMENT_MODE"] = "PROD"


def test_base_agent_uses_dev_data_path():
    """Test BaseAgent uses dev data paths in DEV mode"""
    os.environ["DEPLOYMENT_MODE"] = "DEV"

    agent = BaseAgent(
        signature="test-agent",
        basemodel="mock/test-trader",
        log_path="./data/agent_data"  # Original path
    )

    # Should be converted to dev path
    assert "dev_agent_data" in agent.base_log_path

    os.environ["DEPLOYMENT_MODE"] = "PROD"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_base_agent_mock.py -v`
Expected: FAIL (BaseAgent doesn't use mock yet)

**Step 3: Update BaseAgent __init__ to handle deployment mode**

Modify `agent/base_agent/base_agent.py`, add imports after line 25:

```python
from tools.deployment_config import (
    is_dev_mode,
    get_data_path,
    log_api_key_warning,
    get_deployment_mode
)
```

Modify `__init__` method around line 103 to update log path:

```python
        # Set log path (apply deployment mode path resolution)
        self.base_log_path = get_data_path(log_path or "./data/agent_data")
```

**Step 4: Update BaseAgent initialize() to use mock in dev mode**

Modify `initialize` method (lines 146-189):

```python
    async def initialize(self) -> None:
        """Initialize MCP client and AI model"""
        print(f"🚀 Initializing agent: {self.signature}")
        print(f"🔧 Deployment mode: {get_deployment_mode()}")

        # Log API key warning if in dev mode
        log_api_key_warning()

        # Validate OpenAI configuration (only in PROD mode)
        if not is_dev_mode():
            if not self.openai_api_key:
                raise ValueError("❌ OpenAI API key not set. Please configure OPENAI_API_KEY in environment or config file.")
            if not self.openai_base_url:
                print("⚠️  OpenAI base URL not set, using default")

        try:
            # Create MCP client
            self.client = MultiServerMCPClient(self.mcp_config)

            # Get tools
            self.tools = await self.client.get_tools()
            if not self.tools:
                print("⚠️  Warning: No MCP tools loaded. MCP services may not be running.")
                print(f"   MCP configuration: {self.mcp_config}")
            else:
                print(f"✅ Loaded {len(self.tools)} MCP tools")
        except Exception as e:
            raise RuntimeError(
                f"❌ Failed to initialize MCP client: {e}\n"
                f"   Please ensure MCP services are running at the configured ports.\n"
                f"   Run: python agent_tools/start_mcp_services.py"
            )

        try:
            # Create AI model (mock in DEV mode, real in PROD mode)
            if is_dev_mode():
                from agent.mock_provider import MockChatModel
                self.model = MockChatModel(date="2025-01-01")  # Date will be updated per session
                print(f"🤖 Using MockChatModel (DEV mode)")
            else:
                self.model = ChatOpenAI(
                    model=self.basemodel,
                    base_url=self.openai_base_url,
                    api_key=self.openai_api_key,
                    max_retries=3,
                    timeout=30
                )
                print(f"🤖 Using {self.basemodel} (PROD mode)")
        except Exception as e:
            raise RuntimeError(f"❌ Failed to initialize AI model: {e}")

        # Note: agent will be created in run_trading_session() based on specific date
        # because system_prompt needs the current date and price information

        print(f"✅ Agent {self.signature} initialization completed")
```

**Step 5: Update run_trading_session to set date on mock model**

Modify `run_trading_session` method around line 236:

```python
    async def run_trading_session(self, today_date: str) -> None:
        """
        Run single day trading session

        Args:
            today_date: Trading date
        """
        print(f"📈 Starting trading session: {today_date}")

        # Update mock model date if in dev mode
        if is_dev_mode():
            self.model.date = today_date

        # Set up logging
        log_file = self._setup_logging(today_date)

        # Update system prompt
        self.agent = create_agent(
            self.model,
            tools=self.tools,
            system_prompt=get_agent_system_prompt(today_date, self.signature),
        )

        # ... rest of method unchanged
```

**Step 6: Run tests to verify they pass**

Run: `pytest tests/unit/test_base_agent_mock.py -v`
Expected: PASS (3 tests)

**Step 7: Commit**

```bash
git add agent/base_agent/base_agent.py tests/unit/test_base_agent_mock.py
git commit -m "feat: integrate mock AI provider in BaseAgent for DEV mode"
```

---

## Task 8: Update Main Entry Point with Dev Database Initialization

**Files:**
- Modify: `main.py:94-110`

**Step 1: Add import statements**

Add after line 11 in `main.py`:

```python
from tools.deployment_config import (
    is_dev_mode,
    get_deployment_mode,
    log_api_key_warning
)
from api.database import initialize_dev_database
```

**Step 2: Add dev initialization before main loop**

Modify `main` function, add after line 101 (after config is loaded):

```python
    # Initialize dev environment if needed
    if is_dev_mode():
        print("=" * 60)
        print("🛠️  DEVELOPMENT MODE ACTIVE")
        print("=" * 60)
        log_api_key_warning()

        # Initialize dev database (reset unless PRESERVE_DEV_DATA=true)
        from tools.deployment_config import get_db_path
        dev_db_path = get_db_path("data/jobs.db")
        initialize_dev_database(dev_db_path)
        print("=" * 60)
```

**Step 3: Test dev mode initialization manually**

Run: `DEPLOYMENT_MODE=DEV python main.py configs/default_config.json`
Expected: Prints "DEVELOPMENT MODE ACTIVE" and initializes dev database

**Step 4: Verify database files**

Run: `ls -la data/*.db`
Expected: Shows `jobs_dev.db` file

**Step 5: Commit**

```bash
git add main.py
git commit -m "feat: add dev mode initialization to main entry point"
```

---

## Task 9: Update API to Include Deployment Mode Flag

**Files:**
- Modify: `api/main.py` (find API response locations)
- Create: `tests/integration/test_api_deployment_flag.py`

**Step 1: Find API response generation locations**

Run: `grep -n "return.*job" api/main.py | head -20`

**Step 2: Write test for API deployment mode flag**

Create `tests/integration/test_api_deployment_flag.py`:

```python
import os
import pytest
from fastapi.testclient import TestClient


def test_api_includes_deployment_mode_flag():
    """Test API responses include deployment_mode field"""
    os.environ["DEPLOYMENT_MODE"] = "DEV"

    from api.main import app
    client = TestClient(app)

    # Test GET /health endpoint (should include deployment info)
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()

    assert "deployment_mode" in data
    assert data["deployment_mode"] == "DEV"


def test_job_response_includes_deployment_mode():
    """Test job creation response includes deployment mode"""
    os.environ["DEPLOYMENT_MODE"] = "PROD"

    from api.main import app
    client = TestClient(app)

    # Create a test job
    config = {
        "agent_type": "BaseAgent",
        "date_range": {"init_date": "2025-01-01", "end_date": "2025-01-02"},
        "models": [{"name": "test", "basemodel": "mock/test", "signature": "test", "enabled": True}]
    }

    response = client.post("/run", json={"config": config})

    if response.status_code == 200:
        data = response.json()
        assert "deployment_mode" in data
        assert data["deployment_mode"] == "PROD"
```

**Step 3: Run test to verify it fails**

Run: `pytest tests/integration/test_api_deployment_flag.py -v`
Expected: FAIL (deployment_mode not in response)

**Step 4: Update API responses to include deployment mode**

Find `api/main.py` and locate response return statements. Add deployment mode to responses.

For `/health` endpoint:

```python
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    from tools.deployment_config import get_deployment_mode_dict
    return {
        "status": "healthy",
        **get_deployment_mode_dict()
    }
```

For job-related endpoints, add to response dict:

```python
from tools.deployment_config import get_deployment_mode_dict

# In response returns, add:
{
    # ... existing fields
    **get_deployment_mode_dict()
}
```

**Step 5: Run test to verify it passes**

Run: `pytest tests/integration/test_api_deployment_flag.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add api/main.py tests/integration/test_api_deployment_flag.py
git commit -m "feat: add deployment_mode flag to API responses"
```

---

## Task 10: Update Documentation

**Files:**
- Modify: `README.md`
- Modify: `API_REFERENCE.md`
- Modify: `CLAUDE.md`

**Step 1: Update README with dev mode section**

Add to `README.md` after the "Configuration" section:

```markdown
## Development Mode

AI-Trader supports a development mode that mocks AI API calls for testing without costs.

### Quick Start

```bash
# Set environment variables
export DEPLOYMENT_MODE=DEV
export PRESERVE_DEV_DATA=false

# Run simulation (uses mock AI, isolated dev database)
python main.py configs/default_config.json
```

### How It Works

**DEPLOYMENT_MODE=DEV:**
- Mock AI responses (no API calls to OpenAI/Anthropic)
- Separate database: `data/trading_dev.db`
- Separate data directory: `data/dev_agent_data/`
- Dev database reset on startup (unless PRESERVE_DEV_DATA=true)
- Warnings logged if production API keys detected

**DEPLOYMENT_MODE=PROD** (default):
- Real AI API calls
- Production database: `data/trading.db`
- Production data directory: `data/agent_data/`

### Mock AI Behavior

The mock provider returns deterministic responses that rotate through stocks:
- Day 1: AAPL
- Day 2: MSFT
- Day 3: GOOGL
- Etc. (cycles through 10 stocks)

Each mock response includes:
- Price queries for selected stock
- Buy order for 5 shares
- Finish signal to end session

### Environment Variables

```bash
DEPLOYMENT_MODE=PROD          # PROD or DEV (default: PROD)
PRESERVE_DEV_DATA=false      # Keep dev data between runs (default: false)
```

### Use Cases

- **Orchestration testing:** Verify agent loop, position tracking, logging
- **CI/CD pipelines:** Run tests without API costs
- **Configuration validation:** Test date ranges, model configs
- **Development iteration:** Rapid testing of code changes

### Limitations

- Mock responses are static (not context-aware)
- No actual market analysis
- Fixed trading pattern
- For logic testing only, not trading strategy validation
```

**Step 2: Update API_REFERENCE.md**

Add section after "Response Format":

```markdown
### Deployment Mode

All API responses include a `deployment_mode` field:

```json
{
  "job_id": "abc123",
  "status": "completed",
  "deployment_mode": "DEV",
  "is_dev_mode": true,
  "preserve_dev_data": false
}
```

**Fields:**
- `deployment_mode`: "PROD" or "DEV"
- `is_dev_mode`: Boolean flag
- `preserve_dev_data`: Null in PROD, boolean in DEV

**DEV Mode Behavior:**
- No AI API calls (mock responses)
- Separate dev database (`jobs_dev.db`)
- Separate data directory (`dev_agent_data/`)
- Database reset on startup (unless PRESERVE_DEV_DATA=true)
```

**Step 3: Update CLAUDE.md**

Add section to "Important Implementation Details":

```markdown
### Development Mode

**Deployment Modes:**
- `DEPLOYMENT_MODE=PROD`: Real AI calls, production data paths
- `DEPLOYMENT_MODE=DEV`: Mock AI, isolated dev environment

**DEV Mode Characteristics:**
- Uses `MockChatModel` from `agent/mock_provider/`
- Data paths: `data/dev_agent_data/` and `data/trading_dev.db`
- Dev database reset on startup (controlled by `PRESERVE_DEV_DATA`)
- API responses flagged with `deployment_mode` field

**Implementation Details:**
- Deployment config: `tools/deployment_config.py`
- Mock provider: `agent/mock_provider/mock_ai_provider.py`
- LangChain wrapper: `agent/mock_provider/mock_langchain_model.py`
- BaseAgent integration: `agent/base_agent/base_agent.py:146-189`
- Database handling: `api/database.py` (automatic path resolution)

**Testing Dev Mode:**
```bash
DEPLOYMENT_MODE=DEV python main.py configs/default_config.json
```
```

**Step 4: Verify documentation changes**

Run: `grep -n "DEPLOYMENT_MODE" README.md API_REFERENCE.md CLAUDE.md`
Expected: Shows added sections in all three files

**Step 5: Commit**

```bash
git add README.md API_REFERENCE.md CLAUDE.md
git commit -m "docs: add development mode documentation"
```

---

## Task 11: Integration Testing

**Files:**
- Create: `tests/integration/test_dev_mode_e2e.py`

**Step 1: Write end-to-end dev mode test**

Create `tests/integration/test_dev_mode_e2e.py`:

```python
import os
import json
import pytest
import asyncio
from pathlib import Path
from agent.base_agent.base_agent import BaseAgent


@pytest.fixture
def dev_mode_env():
    """Setup and teardown for dev mode testing"""
    # Setup
    original_mode = os.environ.get("DEPLOYMENT_MODE")
    os.environ["DEPLOYMENT_MODE"] = "DEV"
    os.environ["PRESERVE_DEV_DATA"] = "false"

    yield

    # Teardown
    if original_mode:
        os.environ["DEPLOYMENT_MODE"] = original_mode
    else:
        os.environ.pop("DEPLOYMENT_MODE", None)
    os.environ.pop("PRESERVE_DEV_DATA", None)


def test_dev_mode_full_simulation(dev_mode_env, tmp_path):
    """Test complete simulation run in dev mode"""

    # Setup config
    config = {
        "agent_type": "BaseAgent",
        "date_range": {
            "init_date": "2025-01-01",
            "end_date": "2025-01-03"
        },
        "models": [{
            "name": "test-model",
            "basemodel": "mock/test-trader",
            "signature": "test-dev-agent",
            "enabled": True
        }],
        "agent_config": {
            "max_steps": 5,
            "max_retries": 1,
            "base_delay": 0.1,
            "initial_cash": 10000.0
        },
        "log_config": {
            "log_path": str(tmp_path / "dev_agent_data")
        }
    }

    # Create agent
    model_config = config["models"][0]
    agent = BaseAgent(
        signature=model_config["signature"],
        basemodel=model_config["basemodel"],
        log_path=config["log_config"]["log_path"],
        max_steps=config["agent_config"]["max_steps"],
        initial_cash=config["agent_config"]["initial_cash"],
        init_date=config["date_range"]["init_date"]
    )

    # Initialize and run
    asyncio.run(agent.initialize())

    # Verify mock model
    assert agent.model is not None
    assert "Mock" in str(type(agent.model))

    # Run single day
    asyncio.run(agent.run_trading_session("2025-01-01"))

    # Verify logs created
    log_path = Path(agent.base_log_path) / agent.signature / "log" / "2025-01-01" / "log.jsonl"
    assert log_path.exists()

    # Verify log content
    with open(log_path, "r") as f:
        logs = [json.loads(line) for line in f]

    assert len(logs) > 0
    assert any("AAPL" in str(log) for log in logs)  # Day 1 should mention AAPL


def test_dev_database_isolation(dev_mode_env, tmp_path):
    """Test dev and prod databases are separate"""
    from api.database import get_db_connection, initialize_database

    # Initialize prod database
    prod_db = str(tmp_path / "test_prod.db")
    initialize_database(prod_db)

    conn = get_db_connection(prod_db)
    conn.execute("INSERT INTO jobs (job_id, config_path, status, date_range, models, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                 ("prod-job", "config.json", "running", "2025-01-01:2025-01-31", '["model1"]', "2025-01-01T00:00:00"))
    conn.commit()
    conn.close()

    # Initialize dev database (different path)
    dev_db = str(tmp_path / "test_dev.db")
    from api.database import initialize_dev_database
    initialize_dev_database(dev_db)

    # Verify prod data still exists
    conn = get_db_connection(prod_db)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM jobs WHERE job_id = 'prod-job'")
    assert cursor.fetchone()[0] == 1
    conn.close()

    # Verify dev database is empty
    conn = get_db_connection(dev_db)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM jobs")
    assert cursor.fetchone()[0] == 0
    conn.close()


def test_preserve_dev_data_flag(dev_mode_env, tmp_path):
    """Test PRESERVE_DEV_DATA prevents cleanup"""
    os.environ["PRESERVE_DEV_DATA"] = "true"

    from api.database import initialize_dev_database, get_db_connection

    dev_db = str(tmp_path / "test_dev_preserve.db")

    # Create database with data
    from api.database import initialize_database
    initialize_database(dev_db)
    conn = get_db_connection(dev_db)
    conn.execute("INSERT INTO jobs (job_id, config_path, status, date_range, models, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                 ("dev-job-1", "config.json", "completed", "2025-01-01:2025-01-31", '["model1"]', "2025-01-01T00:00:00"))
    conn.commit()
    conn.close()

    # Initialize again (should preserve)
    initialize_dev_database(dev_db)

    # Verify data preserved
    conn = get_db_connection(dev_db)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM jobs WHERE job_id = 'dev-job-1'")
    assert cursor.fetchone()[0] == 1
    conn.close()
```

**Step 2: Run integration tests**

Run: `pytest tests/integration/test_dev_mode_e2e.py -v -s`
Expected: PASS (3 tests)

**Step 3: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests PASS

**Step 4: Commit**

```bash
git add tests/integration/test_dev_mode_e2e.py
git commit -m "test: add end-to-end integration tests for dev mode"
```

---

## Task 12: Manual Verification and Final Testing

**Files:**
- N/A (manual testing)

**Step 1: Test dev mode startup**

Run:
```bash
export DEPLOYMENT_MODE=DEV
python main.py configs/default_config.json
```

Verify output shows:
- "DEVELOPMENT MODE ACTIVE"
- "Using MockChatModel (DEV mode)"
- Warning about API keys (if .env has keys)
- Creates `data/trading_dev.db`
- Creates `data/dev_agent_data/`

**Step 2: Test prod mode (default)**

Run:
```bash
unset DEPLOYMENT_MODE
python main.py configs/default_config.json
```

Verify output shows:
- No "DEVELOPMENT MODE" message
- "Using [actual model] (PROD mode)"
- Uses `data/trading.db`
- Uses `data/agent_data/`

**Step 3: Test preserve flag**

Run:
```bash
export DEPLOYMENT_MODE=DEV
export PRESERVE_DEV_DATA=true
python main.py configs/default_config.json
# Run again
python main.py configs/default_config.json
```

Verify:
- Second run shows "PRESERVE_DEV_DATA=true"
- Dev database not deleted between runs
- Position data persists

**Step 4: Verify database isolation**

Run:
```bash
ls -la data/*.db
sqlite3 data/trading_dev.db "SELECT COUNT(*) FROM jobs"
sqlite3 data/trading.db "SELECT COUNT(*) FROM jobs"
```

Verify:
- Both databases exist
- Contain different data
- Dev database can be deleted without affecting prod

**Step 5: Test API with deployment flag**

Run:
```bash
export DEPLOYMENT_MODE=DEV
uvicorn api.main:app --reload
# In another terminal:
curl http://localhost:8000/health
```

Verify response includes:
```json
{
  "status": "healthy",
  "deployment_mode": "DEV",
  "is_dev_mode": true,
  "preserve_dev_data": false
}
```

**Step 6: Document any issues found**

Create issue tickets for any bugs discovered during manual testing.

**Step 7: Final commit**

```bash
# If any fixes were needed during manual testing:
git add .
git commit -m "fix: address issues found during manual verification"

# Tag the feature
git tag -a v0.1.0-dev-mode -m "Add development mode with mock AI provider"
```

---

## Summary

This implementation adds a complete development mode feature to AI-Trader:

✅ **Environment Configuration**
- `DEPLOYMENT_MODE` (PROD/DEV)
- `PRESERVE_DEV_DATA` flag
- Documentation in `.env.example`

✅ **Mock AI Provider**
- Deterministic stock rotation
- LangChain-compatible wrapper
- No API costs in DEV mode

✅ **Data Isolation**
- Separate dev database (`trading_dev.db`)
- Separate dev data directory (`dev_agent_data/`)
- Automatic path resolution

✅ **Database Management**
- Dev database reset on startup
- Preserve flag for debugging
- Cleanup utilities

✅ **Integration**
- BaseAgent mock integration
- Main entry point initialization
- API deployment mode flag

✅ **Testing**
- Unit tests for all components
- Integration tests for E2E flows
- Manual verification checklist

✅ **Documentation**
- README with dev mode guide
- API reference updates
- CLAUDE.md implementation notes

**Total Tasks:** 12
**Estimated Time:** 2-3 hours (bite-sized tasks, frequent commits)
**Test Coverage:** Unit + Integration + Manual

**Key Design Decisions:**
- Deployment mode controlled by environment variable (not config file)
- Automatic path resolution (transparent to existing code)
- Mock provider uses rotation for test variety
- Preserve flag for debugging (default: false for clean slate)
- API responses flagged for observability
