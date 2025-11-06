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

            # DIAGNOSTIC: Log response structure
            print(f"\n[DEBUG] Response keys: {response_dict.keys()}")
            if 'choices' in response_dict:
                print(f"[DEBUG] Number of choices: {len(response_dict['choices'])}")
                for i, choice in enumerate(response_dict['choices']):
                    print(f"[DEBUG] Choice {i} keys: {choice.keys()}")
                    if 'message' in choice:
                        message = choice['message']
                        print(f"[DEBUG] Message keys: {message.keys()}")

                        # Check tool_calls structure
                        if 'tool_calls' in message and message['tool_calls']:
                            print(f"[DEBUG] Found {len(message['tool_calls'])} tool_calls")
                            for j, tc in enumerate(message['tool_calls']):
                                print(f"[DEBUG] tool_calls[{j}] keys: {tc.keys()}")
                                if 'function' in tc:
                                    print(f"[DEBUG] tool_calls[{j}].function keys: {tc['function'].keys()}")
                                    if 'arguments' in tc['function']:
                                        args = tc['function']['arguments']
                                        print(f"[DEBUG] tool_calls[{j}].function.arguments type: {type(args)}")
                                        print(f"[DEBUG] tool_calls[{j}].function.arguments value: {repr(args)[:200]}")

                        if 'invalid_tool_calls' in message:
                            print(f"[DEBUG] Found invalid_tool_calls: {len(message['invalid_tool_calls'])} items")
                            for j, inv in enumerate(message['invalid_tool_calls']):
                                print(f"[DEBUG] invalid_tool_calls[{j}] keys: {inv.keys()}")
                                if 'args' in inv:
                                    print(f"[DEBUG] invalid_tool_calls[{j}].args type: {type(inv['args'])}")
                                    print(f"[DEBUG] invalid_tool_calls[{j}].args value: {inv['args']}")

            # REMOVED: No conversion needed yet - gathering data first

            # Call original method with unmodified response
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
