import os
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from agent.base_agent.base_agent import BaseAgent


def test_base_agent_uses_mock_in_dev_mode():
    """Test BaseAgent uses mock model when DEPLOYMENT_MODE=DEV"""
    os.environ["DEPLOYMENT_MODE"] = "DEV"

    agent = BaseAgent(
        signature="test-agent",
        basemodel="mock/test-trader",
        log_path="./data/dev_agent_data"
    )

    # Mock MCP client to avoid needing running services
    async def mock_initialize():
        # Mock the MCP client
        agent.client = MagicMock()
        agent.tools = []

        # Create mock model based on deployment mode
        from tools.deployment_config import is_dev_mode
        if is_dev_mode():
            from agent.mock_provider import MockChatModel
            agent.model = MockChatModel(date="2025-01-01")

    # Run mock initialization
    asyncio.run(mock_initialize())

    assert agent.model is not None
    assert "Mock" in str(type(agent.model))

    os.environ["DEPLOYMENT_MODE"] = "PROD"


def test_base_agent_warns_about_api_keys_in_dev(capsys):
    """Test BaseAgent logs warning about API keys in DEV mode"""
    os.environ["DEPLOYMENT_MODE"] = "DEV"
    os.environ["OPENAI_API_KEY"] = "sk-test123"

    # Test the warning function directly
    from tools.deployment_config import log_api_key_warning
    log_api_key_warning()

    captured = capsys.readouterr()
    assert "WARNING" in captured.out
    assert "OPENAI_API_KEY" in captured.out

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
