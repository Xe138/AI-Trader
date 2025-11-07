"""
Chat model wrapper to fix tool_calls args parsing issues.

DeepSeek and other providers return tool_calls.args as JSON strings, which need
to be parsed to dicts before AIMessage construction.
"""

import json
from typing import Any, Optional, Dict
from functools import wraps


class ToolCallArgsParsingWrapper:
    """
    Wrapper that adds diagnostic logging and fixes tool_calls args if needed.
    """

    def __init__(self, model: Any, **kwargs):
        """
        Initialize wrapper around a chat model.

        Args:
            model: The chat model to wrap
            **kwargs: Additional parameters (ignored, for compatibility)
        """
        self.wrapped_model = model
        self._patch_model()

    def _patch_model(self):
        """Monkey-patch the model's _create_chat_result to add diagnostics"""
        if not hasattr(self.wrapped_model, '_create_chat_result'):
            # Model doesn't have this method (e.g., MockChatModel), skip patching
            return

        # CRITICAL: Patch parse_tool_call in base.py's namespace (not in openai_tools module!)
        from langchain_openai.chat_models import base as langchain_base
        original_parse_tool_call = langchain_base.parse_tool_call

        def patched_parse_tool_call(raw_tool_call, *, partial=False, strict=False, return_id=True):
            """Patched parse_tool_call to fix string args bug"""
            result = original_parse_tool_call(raw_tool_call, partial=partial, strict=strict, return_id=return_id)
            if result and isinstance(result.get('args'), str):
                # FIX: parse_tool_call sometimes returns string args instead of dict
                # This is a known LangChain bug - parse the string to dict
                try:
                    result['args'] = json.loads(result['args'])
                except (json.JSONDecodeError, TypeError):
                    # Leave as string if we can't parse it - will fail validation
                    # but at least we tried
                    pass
            return result

        # Replace in base.py's namespace (where _convert_dict_to_message uses it)
        langchain_base.parse_tool_call = patched_parse_tool_call

        original_create_chat_result = self.wrapped_model._create_chat_result

        @wraps(original_create_chat_result)
        def patched_create_chat_result(response: Any, generation_info: Optional[Dict] = None):
            """Patched version that normalizes non-standard tool_call formats"""
            response_dict = response if isinstance(response, dict) else response.model_dump()

            # Normalize tool_calls to OpenAI standard format if needed
            if 'choices' in response_dict:
                for choice in response_dict['choices']:
                    if 'message' not in choice:
                        continue

                    message = choice['message']

                    # Fix tool_calls: Convert non-standard {name, args, id} to {function: {name, arguments}, id}
                    if 'tool_calls' in message and message['tool_calls']:
                        for tool_call in message['tool_calls']:
                            # Check if this is non-standard format (has 'args' directly)
                            if 'args' in tool_call and 'function' not in tool_call:
                                # Convert to standard OpenAI format
                                args = tool_call['args']
                                tool_call['function'] = {
                                    'name': tool_call.get('name', ''),
                                    'arguments': args if isinstance(args, str) else json.dumps(args)
                                }
                                # Remove non-standard fields
                                if 'name' in tool_call:
                                    del tool_call['name']
                                if 'args' in tool_call:
                                    del tool_call['args']

                    # Fix invalid_tool_calls: Ensure args is JSON string (not dict)
                    if 'invalid_tool_calls' in message and message['invalid_tool_calls']:
                        for invalid_call in message['invalid_tool_calls']:
                            if 'args' in invalid_call and isinstance(invalid_call['args'], dict):
                                try:
                                    invalid_call['args'] = json.dumps(invalid_call['args'])
                                except (TypeError, ValueError):
                                    # Keep as-is if serialization fails
                                    pass

            # Call original method with normalized response
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
        """Proxy all attributes/methods to the wrapped model"""
        return getattr(self.wrapped_model, name)

    def bind_tools(self, tools: Any, **kwargs):
        """Bind tools to the wrapped model"""
        return self.wrapped_model.bind_tools(tools, **kwargs)

    def bind(self, **kwargs):
        """Bind settings to the wrapped model"""
        return self.wrapped_model.bind(**kwargs)
