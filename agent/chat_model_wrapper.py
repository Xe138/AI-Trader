"""
Chat model wrapper - Passthrough wrapper for ChatOpenAI models.

Originally created to fix DeepSeek tool_calls arg parsing issues, but investigation
revealed DeepSeek already returns the correct format (arguments as JSON strings).

This wrapper is now a simple passthrough that proxies all calls to the underlying model.
Kept for backward compatibility and potential future use.
"""

from typing import Any


class ToolCallArgsParsingWrapper:
    """
    Passthrough wrapper around ChatOpenAI models.

    After systematic debugging, determined that DeepSeek returns tool_calls.arguments
    as JSON strings (correct format), so no parsing/conversion is needed.

    This wrapper simply proxies all calls to the wrapped model.
    """

    def __init__(self, model: Any, **kwargs):
        """
        Initialize wrapper around a chat model.

        Args:
            model: The chat model to wrap
            **kwargs: Additional parameters (ignored, for compatibility)
        """
        self.wrapped_model = model

    @property
    def _llm_type(self) -> str:
        """Return identifier for this LLM type"""
        if hasattr(self.wrapped_model, '_llm_type'):
            return f"wrapped-{self.wrapped_model._llm_type}"
        return "wrapped-chat-model"

    def __getattr__(self, name: str):
        """Proxy all attributes/methods to the wrapped model"""
        return getattr(self.wrapped_model, name)

    def bind_tools(self, tools: Any, **kwargs):
        """Bind tools to the wrapped model"""
        return self.wrapped_model.bind_tools(tools, **kwargs)

    def bind(self, **kwargs):
        """Bind settings to the wrapped model"""
        return self.wrapped_model.bind(**kwargs)
