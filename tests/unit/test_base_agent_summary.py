"""Tests for BaseAgent summary generation."""

import pytest
from agent.base_agent.base_agent import BaseAgent
from agent.mock_provider.mock_langchain_model import MockChatModel


@pytest.mark.asyncio
async def test_generate_summary_basic():
    """Should generate summary from content."""
    agent = BaseAgent(
        signature="test-agent",
        basemodel="test-model"
    )

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
    agent = BaseAgent(
        signature="test-agent",
        basemodel="test-model"
    )
    agent.model = MockChatModel(model="test", signature="test")

    content = "Bought AAPL 10 shares based on strong earnings."
    summary = agent.generate_summary_sync(content)

    assert isinstance(summary, str)
    assert len(summary) > 0


@pytest.mark.asyncio
async def test_generate_summary_truncates_long_content():
    """Should truncate very long content before summarizing."""
    agent = BaseAgent(
        signature="test-agent",
        basemodel="test-model"
    )
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
    agent = BaseAgent(
        signature="test-agent",
        basemodel="test-model"
    )

    # No model set - will fail
    agent.model = None

    content = "Test content"
    summary = await agent.generate_summary(content)

    # Should return truncated original on error (with ... appended)
    assert summary == "Test content..."
