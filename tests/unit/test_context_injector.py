"""Test ContextInjector position tracking functionality."""

import pytest
from agent.context_injector import ContextInjector


@pytest.fixture
def injector():
    """Create a ContextInjector instance for testing."""
    return ContextInjector(
        signature="test-model",
        today_date="2025-01-15",
        job_id="test-job-123",
        trading_day_id=1
    )


class MockRequest:
    """Mock MCP tool request."""
    def __init__(self, name, args=None):
        self.name = name
        self.args = args or {}


async def mock_handler_success(request):
    """Mock handler that returns a successful position update."""
    # Simulate a successful trade returning updated position
    if request.name == "sell":
        return {
            "CASH": 1100.0,
            "AAPL": 7,
            "MSFT": 5
        }
    elif request.name == "buy":
        return {
            "CASH": 50.0,
            "AAPL": 7,
            "MSFT": 12
        }
    return {}


async def mock_handler_error(request):
    """Mock handler that returns an error."""
    return {"error": "Insufficient cash"}


@pytest.mark.asyncio
async def test_context_injector_initializes_with_no_position(injector):
    """Test that ContextInjector starts with no position state."""
    assert injector._current_position is None


@pytest.mark.asyncio
async def test_context_injector_reset_position(injector):
    """Test that reset_position() clears position state."""
    # Set some position state
    injector._current_position = {"CASH": 5000.0, "AAPL": 10}

    # Reset
    injector.reset_position()

    assert injector._current_position is None


@pytest.mark.asyncio
async def test_context_injector_injects_parameters(injector):
    """Test that context parameters are injected into buy/sell requests."""
    request = MockRequest("buy", {"symbol": "AAPL", "amount": 10})

    # Mock handler that just returns the request args
    async def handler(req):
        return req.args

    result = await injector(request, handler)

    # Verify context was injected
    assert result["signature"] == "test-model"
    assert result["today_date"] == "2025-01-15"
    assert result["job_id"] == "test-job-123"
    assert result["trading_day_id"] == 1


@pytest.mark.asyncio
async def test_context_injector_tracks_position_after_successful_trade(injector):
    """Test that position state is updated after successful trades."""
    assert injector._current_position is None

    # Execute a sell trade
    request = MockRequest("sell", {"symbol": "AAPL", "amount": 3})
    result = await injector(request, mock_handler_success)

    # Verify position was updated
    assert injector._current_position is not None
    assert injector._current_position["CASH"] == 1100.0
    assert injector._current_position["AAPL"] == 7
    assert injector._current_position["MSFT"] == 5


@pytest.mark.asyncio
async def test_context_injector_injects_current_position_on_subsequent_trades(injector):
    """Test that current position is injected into subsequent trade requests."""
    # First trade - establish position
    request1 = MockRequest("sell", {"symbol": "AAPL", "amount": 3})
    await injector(request1, mock_handler_success)

    # Second trade - should receive current position
    request2 = MockRequest("buy", {"symbol": "MSFT", "amount": 7})

    async def verify_injection_handler(req):
        # Verify that _current_position was injected
        assert "_current_position" in req.args
        assert req.args["_current_position"]["CASH"] == 1100.0
        assert req.args["_current_position"]["AAPL"] == 7
        return mock_handler_success(req)

    await injector(request2, verify_injection_handler)


@pytest.mark.asyncio
async def test_context_injector_does_not_update_position_on_error(injector):
    """Test that position state is NOT updated when trade fails."""
    # First successful trade
    request1 = MockRequest("sell", {"symbol": "AAPL", "amount": 3})
    await injector(request1, mock_handler_success)

    original_position = injector._current_position.copy()

    # Second trade that fails
    request2 = MockRequest("buy", {"symbol": "MSFT", "amount": 100})
    result = await injector(request2, mock_handler_error)

    # Verify position was NOT updated
    assert injector._current_position == original_position
    assert "error" in result


@pytest.mark.asyncio
async def test_context_injector_does_not_inject_position_for_non_trade_tools(injector):
    """Test that position is not injected for non-buy/sell tools."""
    # Set up position state
    injector._current_position = {"CASH": 5000.0, "AAPL": 10}

    # Call a non-trade tool
    request = MockRequest("search", {"query": "market news"})

    async def verify_no_injection_handler(req):
        assert "_current_position" not in req.args
        return {"results": []}

    await injector(request, verify_no_injection_handler)


@pytest.mark.asyncio
async def test_context_injector_full_trading_session_simulation(injector):
    """Test full trading session with multiple trades and position tracking."""
    # Reset position at start of day
    injector.reset_position()
    assert injector._current_position is None

    # Trade 1: Sell AAPL
    request1 = MockRequest("sell", {"symbol": "AAPL", "amount": 3})

    async def handler1(req):
        # First trade should NOT have injected position
        assert req.args.get("_current_position") is None
        return {"CASH": 1100.0, "AAPL": 7}

    result1 = await injector(request1, handler1)
    assert injector._current_position == {"CASH": 1100.0, "AAPL": 7}

    # Trade 2: Buy MSFT (should use position from trade 1)
    request2 = MockRequest("buy", {"symbol": "MSFT", "amount": 7})

    async def handler2(req):
        # Second trade SHOULD have injected position from trade 1
        assert req.args["_current_position"]["CASH"] == 1100.0
        assert req.args["_current_position"]["AAPL"] == 7
        return {"CASH": 50.0, "AAPL": 7, "MSFT": 7}

    result2 = await injector(request2, handler2)
    assert injector._current_position == {"CASH": 50.0, "AAPL": 7, "MSFT": 7}

    # Trade 3: Failed trade (should not update position)
    request3 = MockRequest("buy", {"symbol": "GOOGL", "amount": 100})

    async def handler3(req):
        return {"error": "Insufficient cash", "cash_available": 50.0}

    result3 = await injector(request3, handler3)
    # Position should remain unchanged after failed trade
    assert injector._current_position == {"CASH": 50.0, "AAPL": 7, "MSFT": 7}
