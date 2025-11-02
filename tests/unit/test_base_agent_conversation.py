"""Tests for BaseAgent conversation history tracking."""

import pytest
from agent.base_agent.base_agent import BaseAgent


def test_conversation_history_initialized_empty():
    """Conversation history should start empty."""
    agent = BaseAgent(
        signature="test-agent",
        basemodel="test-model"
    )
    assert agent.conversation_history == []
    assert agent.get_conversation_history() == []


def test_capture_message_user():
    """Should capture user message."""
    agent = BaseAgent(
        signature="test-agent",
        basemodel="test-model"
    )
    agent._capture_message("user", "Test prompt")

    history = agent.get_conversation_history()
    assert len(history) == 1
    assert history[0]["role"] == "user"
    assert history[0]["content"] == "Test prompt"
    assert "timestamp" in history[0]


def test_capture_message_assistant():
    """Should capture assistant message."""
    agent = BaseAgent(
        signature="test-agent",
        basemodel="test-model"
    )
    agent._capture_message("assistant", "Test response")

    history = agent.get_conversation_history()
    assert len(history) == 1
    assert history[0]["role"] == "assistant"
    assert history[0]["content"] == "Test response"


def test_capture_message_tool():
    """Should capture tool message with tool info."""
    agent = BaseAgent(
        signature="test-agent",
        basemodel="test-model"
    )
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
    agent = BaseAgent(
        signature="test-agent",
        basemodel="test-model"
    )
    agent._capture_message("user", "Test")
    assert len(agent.get_conversation_history()) == 1

    agent.clear_conversation_history()
    assert len(agent.get_conversation_history()) == 0


def test_get_conversation_history_returns_copy():
    """Should return a copy to prevent external modification."""
    agent = BaseAgent(
        signature="test-agent",
        basemodel="test-model"
    )
    agent._capture_message("user", "Test")

    history1 = agent.get_conversation_history()
    history2 = agent.get_conversation_history()

    # Modify one copy
    history1.append({"role": "user", "content": "Extra"})

    # Other copy should be unaffected
    assert len(history2) == 1
    assert len(agent.conversation_history) == 1
