# Fix IF_TRADE Flag and DeepSeek Tool Calls Validation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix two bugs: (1) "No trading" message always displayed despite trading activity, and (2) sporadic Pydantic validation errors for DeepSeek tool_calls arguments.

**Architecture:**
- Issue #1: Change IF_TRADE initialization from False to True in runtime config manager
- Issue #2: Replace ChatOpenAI with native ChatDeepSeek for DeepSeek models to eliminate OpenAI compatibility layer issues

**Tech Stack:** Python 3.10+, LangChain 1.0.2, langchain-deepseek, FastAPI, SQLite

---

## Task 1: Fix IF_TRADE Initialization Bug

**Files:**
- Modify: `api/runtime_manager.py:80-86`
- Test: `tests/unit/test_runtime_manager.py`
- Verify: `agent/base_agent/base_agent.py:745-752`

**Root Cause:**
`IF_TRADE` is initialized to `False` but never updated when trades execute. The design documents show it should initialize to `True` (trades are expected by default).

**Step 1: Write failing test for IF_TRADE initialization**

Add to `tests/unit/test_runtime_manager.py` after existing tests:

```python
def test_create_runtime_config_if_trade_defaults_true(self):
    """Test that IF_TRADE initializes to True (trades expected by default)"""
    manager = RuntimeConfigManager()

    config_path = manager.create_runtime_config(
        date="2025-01-16",
        model_sig="test-model",
        job_id="test-job-123",
        trading_day_id=1
    )

    try:
        # Read the config file
        with open(config_path, 'r') as f:
            config = json.load(f)

        # Verify IF_TRADE is True by default
        assert config["IF_TRADE"] is True, "IF_TRADE should initialize to True"
    finally:
        # Cleanup
        if os.path.exists(config_path):
            os.remove(config_path)
```

**Step 2: Run test to verify it fails**

Run: `./venv/bin/python -m pytest tests/unit/test_runtime_manager.py::TestRuntimeConfigManager::test_create_runtime_config_if_trade_defaults_true -v`

Expected: FAIL with assertion error showing `IF_TRADE` is `False`

**Step 3: Fix IF_TRADE initialization**

In `api/runtime_manager.py`, change line 83:

```python
# BEFORE (line 80-86):
initial_config = {
    "TODAY_DATE": date,
    "SIGNATURE": model_sig,
    "IF_TRADE": False,  # BUG: Should be True
    "JOB_ID": job_id,
    "TRADING_DAY_ID": trading_day_id
}

# AFTER:
initial_config = {
    "TODAY_DATE": date,
    "SIGNATURE": model_sig,
    "IF_TRADE": True,  # FIX: Trades are expected by default
    "JOB_ID": job_id,
    "TRADING_DAY_ID": trading_day_id
}
```

**Step 4: Run test to verify it passes**

Run: `./venv/bin/python -m pytest tests/unit/test_runtime_manager.py::TestRuntimeConfigManager::test_create_runtime_config_if_trade_defaults_true -v`

Expected: PASS

**Step 5: Update existing test expectations**

The existing test `test_create_runtime_config_creates_file` at line 66 expects `IF_TRADE` to be `False`. Update it:

```python
# In test_create_runtime_config_creates_file, change line 66:
# BEFORE:
assert config["IF_TRADE"] is False

# AFTER:
assert config["IF_TRADE"] is True
```

**Step 6: Run all runtime_manager tests**

Run: `./venv/bin/python -m pytest tests/unit/test_runtime_manager.py -v`

Expected: All tests PASS

**Step 7: Verify integration test expectations**

Check `tests/integration/test_agent_pnl_integration.py` line 63:

```python
# Current mock (line 62-66):
mock_get_config.side_effect = lambda key: {
    "IF_TRADE": False,  # This may need updating depending on test scenario
    "JOB_ID": "test-job",
    "TODAY_DATE": "2025-01-15",
    "SIGNATURE": "test-model"
}.get(key)
```

This test mocks a no-trade scenario, so `False` is correct here. No change needed.

**Step 8: Commit IF_TRADE fix**

```bash
git add api/runtime_manager.py tests/unit/test_runtime_manager.py
git commit -m "fix: initialize IF_TRADE to True (trades expected by default)

Root cause: IF_TRADE was initialized to False and never updated when
trades executed, causing 'No trading' message to always display.

Design documents (2025-02-11-complete-schema-migration) specify
IF_TRADE should start as True, with trades setting it to False only
after completion.

Fixes sporadic issue where all trading sessions reported 'No trading'
despite successful buy/sell actions."
```

---

## Task 2: Add langchain-deepseek Dependency

**Files:**
- Modify: `requirements.txt`
- Verify: `venv/bin/pip list`

**Step 1: Add langchain-deepseek to requirements.txt**

Add after line 3 in `requirements.txt`:

```txt
langchain==1.0.2
langchain-openai==1.0.1
langchain-mcp-adapters>=0.1.0
langchain-deepseek>=0.1.20
```

**Step 2: Install new dependency**

Run: `./venv/bin/pip install -r requirements.txt`

Expected: Successfully installs `langchain-deepseek` and its dependencies

**Step 3: Verify installation**

Run: `./venv/bin/pip show langchain-deepseek`

Expected: Shows package info with version >= 0.1.20

**Step 4: Commit dependency addition**

```bash
git add requirements.txt
git commit -m "deps: add langchain-deepseek for native DeepSeek support

Adds official LangChain DeepSeek integration to replace ChatOpenAI
wrapper approach for DeepSeek models. Native integration provides:
- Better tool_calls argument parsing
- DeepSeek-specific error handling
- No OpenAI compatibility layer issues

Version 0.1.20+ includes tool calling support for deepseek-chat."
```

---

## Task 3: Implement Model Provider Factory

**Files:**
- Create: `agent/model_factory.py`
- Test: `tests/unit/test_model_factory.py`

**Rationale:**
Currently `base_agent.py` hardcodes model creation logic. Extract to factory pattern to support multiple providers (OpenAI, DeepSeek, Anthropic, etc.) with provider-specific handling.

**Step 1: Write failing test for model factory**

Create `tests/unit/test_model_factory.py`:

```python
"""Unit tests for model factory - provider-specific model creation"""

import pytest
from unittest.mock import Mock, patch
from agent.model_factory import create_model


class TestModelFactory:
    """Tests for create_model factory function"""

    @patch('agent.model_factory.ChatDeepSeek')
    def test_create_model_deepseek(self, mock_deepseek_class):
        """Test that DeepSeek models use ChatDeepSeek"""
        mock_model = Mock()
        mock_deepseek_class.return_value = mock_model

        result = create_model(
            basemodel="deepseek/deepseek-chat",
            api_key="test-key",
            base_url="https://api.deepseek.com",
            temperature=0.7,
            timeout=30
        )

        # Verify ChatDeepSeek was called with correct params
        mock_deepseek_class.assert_called_once_with(
            model="deepseek-chat",  # Extracted from "deepseek/deepseek-chat"
            api_key="test-key",
            base_url="https://api.deepseek.com",
            temperature=0.7,
            timeout=30
        )
        assert result == mock_model

    @patch('agent.model_factory.ChatOpenAI')
    def test_create_model_openai(self, mock_openai_class):
        """Test that OpenAI models use ChatOpenAI"""
        mock_model = Mock()
        mock_openai_class.return_value = mock_model

        result = create_model(
            basemodel="openai/gpt-4",
            api_key="test-key",
            base_url="https://api.openai.com/v1",
            temperature=0.7,
            timeout=30
        )

        # Verify ChatOpenAI was called with correct params
        mock_openai_class.assert_called_once_with(
            model="openai/gpt-4",
            api_key="test-key",
            base_url="https://api.openai.com/v1",
            temperature=0.7,
            timeout=30
        )
        assert result == mock_model

    @patch('agent.model_factory.ChatOpenAI')
    def test_create_model_anthropic(self, mock_openai_class):
        """Test that Anthropic models use ChatOpenAI (via compatibility)"""
        mock_model = Mock()
        mock_openai_class.return_value = mock_model

        result = create_model(
            basemodel="anthropic/claude-sonnet-4.5",
            api_key="test-key",
            base_url="https://api.anthropic.com/v1",
            temperature=0.7,
            timeout=30
        )

        # Verify ChatOpenAI was used (Anthropic via OpenAI-compatible endpoint)
        mock_openai_class.assert_called_once()
        assert result == mock_model

    @patch('agent.model_factory.ChatOpenAI')
    def test_create_model_generic_provider(self, mock_openai_class):
        """Test that unknown providers default to ChatOpenAI"""
        mock_model = Mock()
        mock_openai_class.return_value = mock_model

        result = create_model(
            basemodel="custom/custom-model",
            api_key="test-key",
            base_url="https://api.custom.com",
            temperature=0.7,
            timeout=30
        )

        # Should fall back to ChatOpenAI for unknown providers
        mock_openai_class.assert_called_once()
        assert result == mock_model

    def test_create_model_deepseek_extracts_model_name(self):
        """Test that DeepSeek model name is extracted correctly"""
        with patch('agent.model_factory.ChatDeepSeek') as mock_class:
            create_model(
                basemodel="deepseek/deepseek-chat-v3.1",
                api_key="key",
                base_url="url",
                temperature=0,
                timeout=30
            )

            # Check that model param is just "deepseek-chat-v3.1"
            call_kwargs = mock_class.call_args[1]
            assert call_kwargs['model'] == "deepseek-chat-v3.1"
```

**Step 2: Run test to verify it fails**

Run: `./venv/bin/python -m pytest tests/unit/test_model_factory.py -v`

Expected: FAIL with "ModuleNotFoundError: No module named 'agent.model_factory'"

**Step 3: Implement model factory**

Create `agent/model_factory.py`:

```python
"""
Model factory for creating provider-specific chat models.

Supports multiple AI providers with native integrations where available:
- DeepSeek: Uses ChatDeepSeek for native tool calling support
- OpenAI: Uses ChatOpenAI
- Others: Fall back to ChatOpenAI (OpenAI-compatible endpoints)
"""

from typing import Any
from langchain_openai import ChatOpenAI
from langchain_deepseek import ChatDeepSeek


def create_model(
    basemodel: str,
    api_key: str,
    base_url: str,
    temperature: float,
    timeout: int
) -> Any:
    """
    Create appropriate chat model based on provider.

    Args:
        basemodel: Model identifier (e.g., "deepseek/deepseek-chat", "openai/gpt-4")
        api_key: API key for the provider
        base_url: Base URL for API endpoint
        temperature: Sampling temperature (0-1)
        timeout: Request timeout in seconds

    Returns:
        Provider-specific chat model instance

    Examples:
        >>> model = create_model("deepseek/deepseek-chat", "key", "url", 0.7, 30)
        >>> isinstance(model, ChatDeepSeek)
        True

        >>> model = create_model("openai/gpt-4", "key", "url", 0.7, 30)
        >>> isinstance(model, ChatOpenAI)
        True
    """
    # Extract provider from basemodel (format: "provider/model-name")
    provider = basemodel.split("/")[0].lower() if "/" in basemodel else "unknown"

    if provider == "deepseek":
        # Use native ChatDeepSeek for DeepSeek models
        # Extract model name without provider prefix
        model_name = basemodel.split("/", 1)[1] if "/" in basemodel else basemodel

        return ChatDeepSeek(
            model=model_name,
            api_key=api_key,
            base_url=base_url,
            temperature=temperature,
            timeout=timeout
        )
    else:
        # Use ChatOpenAI for OpenAI and OpenAI-compatible endpoints
        # (Anthropic, Google, Qwen, etc. via compatibility layer)
        return ChatOpenAI(
            model=basemodel,
            api_key=api_key,
            base_url=base_url,
            temperature=temperature,
            timeout=timeout
        )
```

**Step 4: Run tests to verify they pass**

Run: `./venv/bin/python -m pytest tests/unit/test_model_factory.py -v`

Expected: All tests PASS

**Step 5: Commit model factory**

```bash
git add agent/model_factory.py tests/unit/test_model_factory.py
git commit -m "feat: add model factory for provider-specific chat models

Implements factory pattern to create appropriate chat model based on
provider prefix in basemodel string.

Supported providers:
- deepseek/*: Uses ChatDeepSeek (native tool calling)
- openai/*: Uses ChatOpenAI
- others: Fall back to ChatOpenAI (OpenAI-compatible)

This enables native DeepSeek integration while maintaining backward
compatibility with existing OpenAI-compatible providers."
```

---

## Task 4: Integrate Model Factory into BaseAgent

**Files:**
- Modify: `agent/base_agent/base_agent.py:146-220`
- Test: `tests/unit/test_base_agent.py` (if exists) or manual verification

**Step 1: Import model factory in base_agent.py**

Add after line 33 in `agent/base_agent/base_agent.py`:

```python
from agent.reasoning_summarizer import ReasoningSummarizer
from agent.model_factory import create_model  # ADD THIS
```

**Step 2: Replace model creation logic**

Replace lines 208-220 in `agent/base_agent/base_agent.py`:

```python
# BEFORE (lines 208-220):
if is_dev_mode():
    from agent.mock_provider import MockChatModel
    self.model = MockChatModel(date="2025-01-01")
    print(f"🤖 Using MockChatModel (DEV mode)")
else:
    self.model = ChatOpenAI(
        model=self.basemodel,
        base_url=self.openai_base_url,
        api_key=self.openai_api_key,
        temperature=0.7,
        timeout=30
    )
    print(f"🤖 Using {self.basemodel} (PROD mode)")

# AFTER:
if is_dev_mode():
    from agent.mock_provider import MockChatModel
    self.model = MockChatModel(date="2025-01-01")
    print(f"🤖 Using MockChatModel (DEV mode)")
else:
    # Use model factory for provider-specific implementations
    self.model = create_model(
        basemodel=self.basemodel,
        api_key=self.openai_api_key,
        base_url=self.openai_base_url,
        temperature=0.7,
        timeout=30
    )

    # Determine model type for logging
    model_class = self.model.__class__.__name__
    print(f"🤖 Using {self.basemodel} via {model_class} (PROD mode)")
```

**Step 3: Remove ChatOpenAI import if no longer used**

Check if `ChatOpenAI` is imported but no longer used in `base_agent.py`:

```python
# If line ~11 has:
from langchain_openai import ChatOpenAI

# And it's only used in the section we just replaced, remove it
# (Keep if used elsewhere in file)
```

**Step 4: Manual verification test**

Since this changes core agent initialization, test with actual execution:

Run: `DEPLOYMENT_MODE=DEV python main.py configs/default_config.json`

Expected:
- Logs show "Using deepseek-chat-v3.1 via ChatDeepSeek (PROD mode)" for DeepSeek
- Logs show "Using openai/gpt-5 via ChatOpenAI (PROD mode)" for OpenAI
- No import errors or model creation failures

**Step 5: Run existing agent tests**

Run: `./venv/bin/python -m pytest tests/unit/ -k agent -v`

Expected: All agent-related tests still PASS (factory is transparent to existing behavior)

**Step 6: Commit model factory integration**

```bash
git add agent/base_agent/base_agent.py
git commit -m "refactor: use model factory in BaseAgent

Replaces direct ChatOpenAI instantiation with create_model() factory.

Benefits:
- DeepSeek models now use native ChatDeepSeek
- Other models continue using ChatOpenAI
- Provider-specific optimizations in one place
- Easier to add new providers

Logging now shows both model name and provider class for debugging."
```

---

## Task 5: Add Integration Test for DeepSeek Tool Calls

**Files:**
- Create: `tests/integration/test_deepseek_tool_calls.py`
- Reference: `agent_tools/tool_math.py` (math tool for testing)

**Rationale:**
Verify that DeepSeek's tool_calls arguments are properly parsed to dicts without Pydantic validation errors.

**Step 1: Write integration test**

Create `tests/integration/test_deepseek_tool_calls.py`:

```python
"""
Integration test for DeepSeek tool calls argument parsing.

Tests that ChatDeepSeek properly converts tool_calls.arguments (JSON string)
to tool_calls.args (dict) without Pydantic validation errors.
"""

import pytest
import os
from unittest.mock import patch, AsyncMock
from langchain_core.messages import AIMessage
from agent.model_factory import create_model


@pytest.mark.integration
class TestDeepSeekToolCalls:
    """Integration tests for DeepSeek tool calling"""

    def test_create_model_returns_chat_deepseek_for_deepseek_models(self):
        """Verify that DeepSeek models use ChatDeepSeek class"""
        # Skip if no DeepSeek API key available
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not available")

        model = create_model(
            basemodel="deepseek/deepseek-chat",
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_API_BASE"),
            temperature=0,
            timeout=30
        )

        # Verify it's a ChatDeepSeek instance
        assert model.__class__.__name__ == "ChatDeepSeek"

    @pytest.mark.asyncio
    async def test_deepseek_tool_calls_args_are_dicts(self):
        """Test that DeepSeek tool_calls.args are dicts, not strings"""
        # Skip if no API key
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not available")

        # Create DeepSeek model
        model = create_model(
            basemodel="deepseek/deepseek-chat",
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_API_BASE"),
            temperature=0,
            timeout=30
        )

        # Bind a simple math tool
        from langchain_core.tools import tool

        @tool
        def add(a: float, b: float) -> float:
            """Add two numbers"""
            return a + b

        model_with_tools = model.bind_tools([add])

        # Invoke with a query that should trigger tool call
        result = await model_with_tools.ainvoke(
            "What is 5 plus 3?"
        )

        # Verify response is AIMessage
        assert isinstance(result, AIMessage)

        # Verify tool_calls exist
        assert len(result.tool_calls) > 0, "Expected at least one tool call"

        # Verify args are dicts, not strings
        for tool_call in result.tool_calls:
            assert isinstance(tool_call['args'], dict), \
                f"tool_calls.args should be dict, got {type(tool_call['args'])}"
            assert 'a' in tool_call['args'], "Missing expected arg 'a'"
            assert 'b' in tool_call['args'], "Missing expected arg 'b'"

    @pytest.mark.asyncio
    async def test_deepseek_no_pydantic_validation_errors(self):
        """Test that DeepSeek doesn't produce Pydantic validation errors"""
        # Skip if no API key
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not available")

        model = create_model(
            basemodel="deepseek/deepseek-chat",
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_API_BASE"),
            temperature=0,
            timeout=30
        )

        from langchain_core.tools import tool

        @tool
        def multiply(a: float, b: float) -> float:
            """Multiply two numbers"""
            return a * b

        model_with_tools = model.bind_tools([multiply])

        # This should NOT raise Pydantic validation errors
        try:
            result = await model_with_tools.ainvoke(
                "Calculate 7 times 8"
            )
            assert isinstance(result, AIMessage)
        except Exception as e:
            # Check that it's not a Pydantic validation error
            error_msg = str(e).lower()
            assert "validation error" not in error_msg, \
                f"Pydantic validation error occurred: {e}"
            assert "input should be a valid dictionary" not in error_msg, \
                f"tool_calls.args validation error occurred: {e}"
            # Re-raise if it's a different error
            raise
```

**Step 2: Run test (may require API access)**

Run: `./venv/bin/python -m pytest tests/integration/test_deepseek_tool_calls.py -v`

Expected:
- If API key available: Tests PASS
- If no API key: Tests SKIPPED with message "OPENAI_API_KEY not available"

**Step 3: Commit integration test**

```bash
git add tests/integration/test_deepseek_tool_calls.py
git commit -m "test: add DeepSeek tool calls integration tests

Verifies that ChatDeepSeek properly handles tool_calls arguments:
- Returns ChatDeepSeek for deepseek/* models
- tool_calls.args are dicts (not JSON strings)
- No Pydantic validation errors on args

Tests skip gracefully if API keys not available."
```

---

## Task 6: Update Documentation

**Files:**
- Modify: `CLAUDE.md` (sections on model configuration and troubleshooting)
- Modify: `CHANGELOG.md`

**Step 1: Update CLAUDE.md architecture section**

In `CLAUDE.md`, find the "Agent System" section (around line 125) and update:

```markdown
**BaseAgent Key Methods:**
- `initialize()`: Connect to MCP services, create AI model via model factory
- `run_trading_session(date)`: Execute single day's trading with retry logic
- `run_date_range(init_date, end_date)`: Process all weekdays in range
- `get_trading_dates()`: Resume from last date in position.jsonl
- `register_agent()`: Create initial position file with $10,000 cash

**Model Factory:**
The `create_model()` factory automatically selects the appropriate chat model:
- `deepseek/*` models → `ChatDeepSeek` (native tool calling support)
- `openai/*` models → `ChatOpenAI`
- Other providers → `ChatOpenAI` (OpenAI-compatible endpoint)

**Adding Custom Agents:**
[existing content remains the same]
```

**Step 2: Update CLAUDE.md common issues section**

In `CLAUDE.md`, find "Common Issues" (around line 420) and add:

```markdown
**DeepSeek Pydantic Validation Errors:**
- Error: "Input should be a valid dictionary [type=dict_type, input_value='...', input_type=str]"
- Cause: Using `ChatOpenAI` for DeepSeek models (OpenAI compatibility layer issue)
- Fix: Ensure `langchain-deepseek` is installed and basemodel uses `deepseek/` prefix
- The model factory automatically uses `ChatDeepSeek` for native support
```

**Step 3: Update CHANGELOG.md**

Add new version entry at top of `CHANGELOG.md`:

```markdown
## [0.4.2] - 2025-11-05

### Fixed
- Fixed "No trading" message always displaying despite trading activity by initializing `IF_TRADE` to `True` (trades expected by default)
- Resolved sporadic Pydantic validation errors for DeepSeek tool_calls arguments by switching to native `ChatDeepSeek` integration

### Added
- Added `agent/model_factory.py` for provider-specific model creation
- Added `langchain-deepseek` dependency for native DeepSeek support
- Added integration tests for DeepSeek tool calls argument parsing

### Changed
- `BaseAgent` now uses model factory instead of direct `ChatOpenAI` instantiation
- DeepSeek models (`deepseek/*`) now use `ChatDeepSeek` instead of OpenAI compatibility layer
```

**Step 4: Commit documentation updates**

```bash
git add CLAUDE.md CHANGELOG.md
git commit -m "docs: update for IF_TRADE and DeepSeek fixes

- Document model factory architecture
- Add troubleshooting for DeepSeek validation errors
- Update changelog with version 0.4.2 fixes"
```

---

## Task 7: End-to-End Verification

**Files:**
- Test: Full simulation with DeepSeek model
- Verify: Logs show correct messages and no errors

**Step 1: Run simulation with DeepSeek in PROD mode**

Run:
```bash
# Ensure API keys are set
export OPENAI_API_KEY="your-deepseek-key"
export OPENAI_API_BASE="https://api.deepseek.com/v1"
export DEPLOYMENT_MODE=PROD

# Run short simulation (1 day)
python main.py configs/default_config.json
```

**Step 2: Verify expected behaviors**

Check logs for:

1. **Model initialization:**
   - ✅ Should show: "🤖 Using deepseek/deepseek-chat-v3.1 via ChatDeepSeek (PROD mode)"
   - ❌ Should NOT show: "via ChatOpenAI"

2. **Tool calls execution:**
   - ✅ Should show: "[DEBUG] Extracted X tool messages from response"
   - ❌ Should NOT show: "⚠️ Attempt 1 failed" with Pydantic validation errors
   - Note: If retries occur for other reasons (network, rate limits), that's OK

3. **Trading completion:**
   - ✅ Should show: "✅ Trading completed" (if trades occurred)
   - ❌ Should NOT show: "📊 No trading, maintaining positions" (if trades occurred)

**Step 3: Check database for trade records**

Run:
```bash
sqlite3 data/jobs.db "SELECT job_id, date, model, status FROM trading_days ORDER BY created_at DESC LIMIT 5;"
```

Expected: Recent records show `status='completed'` for DeepSeek runs

**Step 4: Verify position tracking**

Run:
```bash
sqlite3 data/jobs.db "SELECT trading_day_id, action_type, symbol, quantity FROM actions WHERE trading_day_id IN (SELECT id FROM trading_days ORDER BY created_at DESC LIMIT 1);"
```

Expected: Shows buy/sell actions if AI made trades

**Step 5: Run test suite**

Run full test suite to ensure no regressions:

```bash
./venv/bin/python -m pytest tests/ -v --cov=. --cov-report=term-missing
```

Expected: All tests PASS, coverage >= 85%

**Step 6: Final commit**

```bash
git add -A
git commit -m "chore: verify end-to-end functionality after fixes

Confirmed:
- DeepSeek models use ChatDeepSeek (no validation errors)
- Trading completion shows correct message
- Database tracking works correctly
- All tests pass with good coverage"
```

---

## Summary of Changes

### Files Modified:
1. `api/runtime_manager.py` - IF_TRADE initialization fix
2. `requirements.txt` - Added langchain-deepseek dependency
3. `agent/base_agent/base_agent.py` - Integrated model factory
4. `tests/unit/test_runtime_manager.py` - Updated test expectations
5. `CLAUDE.md` - Architecture and troubleshooting updates
6. `CHANGELOG.md` - Version 0.4.2 release notes

### Files Created:
1. `agent/model_factory.py` - Provider-specific model creation
2. `tests/unit/test_model_factory.py` - Model factory tests
3. `tests/integration/test_deepseek_tool_calls.py` - DeepSeek integration tests

### Testing Strategy:
- Unit tests for IF_TRADE initialization
- Unit tests for model factory provider routing
- Integration tests for DeepSeek tool calls
- End-to-end verification with real simulation
- Full test suite regression check

### Verification Commands:
```bash
# Quick test (unit tests only)
bash scripts/quick_test.sh

# Full test suite
bash scripts/run_tests.sh

# End-to-end simulation
DEPLOYMENT_MODE=PROD python main.py configs/default_config.json
```

---

## Notes for Engineer

**Key Architectural Changes:**
- Factory pattern separates provider-specific logic from agent core
- Native integrations preferred over compatibility layers
- IF_TRADE semantics: True = trades expected, tools set to False after execution

**Why These Fixes Work:**
1. **IF_TRADE**: Design always intended True initialization, False was a typo
2. **DeepSeek**: Native ChatDeepSeek handles tool_calls parsing correctly, eliminating sporadic OpenAI compatibility layer bugs

**Testing Philosophy:**
- @superpowers:test-driven-development - Write test first, watch it fail, implement, verify pass
- @superpowers:verification-before-completion - Never claim "it works" without running verification
- Each commit should leave the codebase in a working state

**If You Get Stuck:**
- Check logs for exact error messages
- Run pytest with `-vv` for verbose output
- Use `git diff` to verify changes match plan
- @superpowers:systematic-debugging - Never guess, always investigate root cause
