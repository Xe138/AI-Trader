"""
Chat model wrapper to fix tool_calls args parsing issues.

Some AI providers (like DeepSeek) return tool_calls.args as JSON strings instead
of dictionaries, causing Pydantic validation errors. This wrapper monkey-patches
the model to fix args before AIMessage construction.
"""

import json
from typing import Any, List, Optional, Dict
from functools import wraps
from langchain_core.messages import AIMessage, BaseMessage


class ToolCallArgsParsingWrapper:
    """
    Wrapper around ChatOpenAI that fixes tool_calls args parsing.

    This fixes the Pydantic validation error:
    "Input should be a valid dictionary [type=dict_type, input_value='...', input_type=str]"

    Works by monkey-patching _create_chat_result to parse string args before
    AIMessage construction.
    """

    def __init__(self, model: Any, **kwargs):
        """
        Initialize wrapper around a chat model.

        Args:
            model: The chat model to wrap (should be ChatOpenAI instance)
            **kwargs: Additional parameters (ignored, for compatibility)
        """
        self.wrapped_model = model
        self._patch_model()

    def _patch_model(self):
        """Monkey-patch the model's _create_chat_result to fix tool_calls args"""
        if not hasattr(self.wrapped_model, '_create_chat_result'):
            # Model doesn't have this method (e.g., MockChatModel), skip patching
            return

        original_create_chat_result = self.wrapped_model._create_chat_result

        @wraps(original_create_chat_result)
        def patched_create_chat_result(response: Any, generation_info: Optional[Dict] = None):
            """Patched version that fixes tool_calls args before AIMessage construction"""
            # Fix tool_calls in the response dict before passing to original method
            response_dict = response if isinstance(response, dict) else response.model_dump()

            if 'choices' in response_dict:
                for choice in response_dict['choices']:
                    if 'message' not in choice:
                        continue

                    message = choice['message']

                    # Fix regular tool_calls: string args -> dict
                    if 'tool_calls' in message and message['tool_calls']:
                        for tool_call in message['tool_calls']:
                            if 'function' in tool_call and 'arguments' in tool_call['function']:
                                args = tool_call['function']['arguments']
                                # Parse string arguments to dict
                                if isinstance(args, str):
                                    try:
                                        tool_call['function']['arguments'] = json.loads(args)
                                    except json.JSONDecodeError:
                                        # Keep as string if parsing fails
                                        pass

                    # Fix invalid_tool_calls: dict args -> string
                    if 'invalid_tool_calls' in message and message['invalid_tool_calls']:
                        for invalid_call in message['invalid_tool_calls']:
                            if 'args' in invalid_call:
                                args = invalid_call['args']
                                # Convert dict arguments to JSON string
                                if isinstance(args, dict):
                                    try:
                                        invalid_call['args'] = json.dumps(args)
                                    except (TypeError, ValueError):
                                        # Keep as-is if serialization fails
                                        pass

            # Call original method with fixed response
            return original_create_chat_result(response_dict, generation_info)

        # Replace the method
        self.wrapped_model._create_chat_result = patched_create_chat_result

    @property
    def _llm_type(self) -> str:
        """Return identifier for this LLM type"""
        if hasattr(self.wrapped_model, '_llm_type'):
            return f"wrapped-{self.wrapped_model._llm_type}"
        return "wrapped-chat-model"

    def __getattr__(self, name: str):
        """Proxy all other attributes/methods to the wrapped model"""
        return getattr(self.wrapped_model, name)

    def bind_tools(self, tools: Any, **kwargs):
        """
        Bind tools to the wrapped model.

        Since we patch the model in-place, we can just delegate to the wrapped model.
        """
        return self.wrapped_model.bind_tools(tools, **kwargs)

    def bind(self, **kwargs):
        """
        Bind settings to the wrapped model.

        Since we patch the model in-place, we can just delegate to the wrapped model.
        """
        return self.wrapped_model.bind(**kwargs)
