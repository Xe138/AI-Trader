import pytest
import asyncio
from agent.mock_provider.mock_ai_provider import MockAIProvider
from agent.mock_provider.mock_langchain_model import MockChatModel


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
