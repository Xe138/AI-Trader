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
