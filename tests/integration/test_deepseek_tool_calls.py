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
