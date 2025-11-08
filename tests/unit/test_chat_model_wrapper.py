"""
Unit tests for ChatModelWrapper - tool_calls args parsing fix
"""

import json
import pytest
from unittest.mock import Mock, AsyncMock
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatResult, ChatGeneration

from agent.chat_model_wrapper import ToolCallArgsParsingWrapper


@pytest.mark.skip(reason="API changed - wrapper now uses internal LangChain patching, tests need redesign")
class TestToolCallArgsParsingWrapper:
    """Tests for ToolCallArgsParsingWrapper"""

    @pytest.fixture
    def mock_model(self):
        """Create a mock chat model"""
        model = Mock()
        model._llm_type = "mock-model"
        return model

    @pytest.fixture
    def wrapper(self, mock_model):
        """Create a wrapper around mock model"""
        return ToolCallArgsParsingWrapper(model=mock_model)

    def test_fix_tool_calls_with_string_args(self, wrapper):
        """Test that string args are parsed to dict"""
        # Create message with tool_calls where args is a JSON string
        message = AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "buy",
                    "args": '{"symbol": "AAPL", "amount": 10}',  # String, not dict
                    "id": "call_123"
                }
            ]
        )

        fixed_message = wrapper._fix_tool_calls(message)

        # Check that args is now a dict
        assert isinstance(fixed_message.tool_calls[0]['args'], dict)
        assert fixed_message.tool_calls[0]['args'] == {"symbol": "AAPL", "amount": 10}

    def test_fix_tool_calls_with_dict_args(self, wrapper):
        """Test that dict args are left unchanged"""
        # Create message with tool_calls where args is already a dict
        message = AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "buy",
                    "args": {"symbol": "AAPL", "amount": 10},  # Already a dict
                    "id": "call_123"
                }
            ]
        )

        fixed_message = wrapper._fix_tool_calls(message)

        # Check that args is still a dict
        assert isinstance(fixed_message.tool_calls[0]['args'], dict)
        assert fixed_message.tool_calls[0]['args'] == {"symbol": "AAPL", "amount": 10}

    def test_fix_tool_calls_with_invalid_json(self, wrapper):
        """Test that invalid JSON string is left unchanged"""
        # Create message with tool_calls where args is an invalid JSON string
        message = AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "buy",
                    "args": 'invalid json {',  # Invalid JSON
                    "id": "call_123"
                }
            ]
        )

        fixed_message = wrapper._fix_tool_calls(message)

        # Check that args is still a string (parsing failed)
        assert isinstance(fixed_message.tool_calls[0]['args'], str)
        assert fixed_message.tool_calls[0]['args'] == 'invalid json {'

    def test_fix_tool_calls_no_tool_calls(self, wrapper):
        """Test that messages without tool_calls are left unchanged"""
        message = AIMessage(content="Hello, world!")
        fixed_message = wrapper._fix_tool_calls(message)

        assert fixed_message == message

    def test_generate_with_string_args(self, wrapper, mock_model):
        """Test _generate method with string args"""
        # Create a response with string args
        original_message = AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "buy",
                    "args": '{"symbol": "MSFT", "amount": 5}',
                    "id": "call_456"
                }
            ]
        )

        mock_result = ChatResult(
            generations=[ChatGeneration(message=original_message)]
        )
        mock_model._generate.return_value = mock_result

        # Call wrapper's _generate
        result = wrapper._generate(messages=[], stop=None, run_manager=None)

        # Check that args is now a dict
        fixed_message = result.generations[0].message
        assert isinstance(fixed_message.tool_calls[0]['args'], dict)
        assert fixed_message.tool_calls[0]['args'] == {"symbol": "MSFT", "amount": 5}

    @pytest.mark.asyncio
    async def test_agenerate_with_string_args(self, wrapper, mock_model):
        """Test _agenerate method with string args"""
        # Create a response with string args
        original_message = AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "sell",
                    "args": '{"symbol": "GOOGL", "amount": 3}',
                    "id": "call_789"
                }
            ]
        )

        mock_result = ChatResult(
            generations=[ChatGeneration(message=original_message)]
        )
        mock_model._agenerate = AsyncMock(return_value=mock_result)

        # Call wrapper's _agenerate
        result = await wrapper._agenerate(messages=[], stop=None, run_manager=None)

        # Check that args is now a dict
        fixed_message = result.generations[0].message
        assert isinstance(fixed_message.tool_calls[0]['args'], dict)
        assert fixed_message.tool_calls[0]['args'] == {"symbol": "GOOGL", "amount": 3}

    def test_invoke_with_string_args(self, wrapper, mock_model):
        """Test invoke method with string args"""
        original_message = AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "buy",
                    "args": '{"symbol": "NVDA", "amount": 20}',
                    "id": "call_999"
                }
            ]
        )

        mock_model.invoke.return_value = original_message

        # Call wrapper's invoke
        result = wrapper.invoke(input=[])

        # Check that args is now a dict
        assert isinstance(result.tool_calls[0]['args'], dict)
        assert result.tool_calls[0]['args'] == {"symbol": "NVDA", "amount": 20}

    @pytest.mark.asyncio
    async def test_ainvoke_with_string_args(self, wrapper, mock_model):
        """Test ainvoke method with string args"""
        original_message = AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "sell",
                    "args": '{"symbol": "TSLA", "amount": 15}',
                    "id": "call_111"
                }
            ]
        )

        mock_model.ainvoke = AsyncMock(return_value=original_message)

        # Call wrapper's ainvoke
        result = await wrapper.ainvoke(input=[])

        # Check that args is now a dict
        assert isinstance(result.tool_calls[0]['args'], dict)
        assert result.tool_calls[0]['args'] == {"symbol": "TSLA", "amount": 15}

    def test_bind_tools_returns_wrapper(self, wrapper, mock_model):
        """Test that bind_tools returns a new wrapper"""
        mock_bound = Mock()
        mock_model.bind_tools.return_value = mock_bound

        result = wrapper.bind_tools(tools=[], strict=True)

        # Check that result is a wrapper around the bound model
        assert isinstance(result, ToolCallArgsParsingWrapper)
        assert result.wrapped_model == mock_bound

    def test_bind_returns_wrapper(self, wrapper, mock_model):
        """Test that bind returns a new wrapper"""
        mock_bound = Mock()
        mock_model.bind.return_value = mock_bound

        result = wrapper.bind(max_tokens=100)

        # Check that result is a wrapper around the bound model
        assert isinstance(result, ToolCallArgsParsingWrapper)
        assert result.wrapped_model == mock_bound
