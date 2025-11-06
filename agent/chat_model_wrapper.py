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

        original_create_chat_result = self.wrapped_model._create_chat_result

        @wraps(original_create_chat_result)
        def patched_create_chat_result(response: Any, generation_info: Optional[Dict] = None):
            """Patched version with diagnostic logging and args parsing"""
            response_dict = response if isinstance(response, dict) else response.model_dump()

            # DIAGNOSTIC: Log response structure for debugging
            print(f"\n[DIAGNOSTIC] Response structure:")
            print(f"  Response keys: {list(response_dict.keys())}")

            if 'choices' in response_dict and response_dict['choices']:
                choice = response_dict['choices'][0]
                print(f"  Choice keys: {list(choice.keys())}")

                if 'message' in choice:
                    message = choice['message']
                    print(f"  Message keys: {list(message.keys())}")

                    if 'tool_calls' in message and message['tool_calls']:
                        print(f"  tool_calls count: {len(message['tool_calls'])}")
                        for i, tc in enumerate(message['tool_calls'][:2]):  # Show first 2
                            print(f"  tool_calls[{i}] keys: {list(tc.keys())}")
                            if 'function' in tc:
                                print(f"    function keys: {list(tc['function'].keys())}")
                                if 'arguments' in tc['function']:
                                    args = tc['function']['arguments']
                                    print(f"    arguments type: {type(args).__name__}")
                                    print(f"    arguments value (first 100 chars): {str(args)[:100]}")

            # Fix tool_calls: Normalize to OpenAI format if needed
            if 'choices' in response_dict:
                for choice in response_dict['choices']:
                    if 'message' not in choice:
                        continue

                    message = choice['message']

                    # Fix tool_calls: Ensure standard OpenAI format
                    if 'tool_calls' in message and message['tool_calls']:
                        print(f"[DIAGNOSTIC] Processing {len(message['tool_calls'])} tool_calls...")
                        for idx, tool_call in enumerate(message['tool_calls']):
                            # Check if this is non-standard format (has 'args' directly)
                            if 'args' in tool_call and 'function' not in tool_call:
                                print(f"[DIAGNOSTIC] tool_calls[{idx}] has non-standard format (direct args)")
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
                                print(f"[DIAGNOSTIC] Converted tool_calls[{idx}] to standard OpenAI format")

                    # Fix invalid_tool_calls: dict args -> string
                    if 'invalid_tool_calls' in message and message['invalid_tool_calls']:
                        print(f"[DIAGNOSTIC] Checking invalid_tool_calls for dict-to-string conversion...")
                        for idx, invalid_call in enumerate(message['invalid_tool_calls']):
                            if 'args' in invalid_call:
                                args = invalid_call['args']
                                # Convert dict arguments to JSON string
                                if isinstance(args, dict):
                                    try:
                                        invalid_call['args'] = json.dumps(args)
                                        print(f"[DIAGNOSTIC] Converted invalid_tool_calls[{idx}].args from dict to string")
                                    except (TypeError, ValueError) as e:
                                        print(f"[DIAGNOSTIC] Failed to serialize invalid_tool_calls[{idx}].args: {e}")
                                        # Keep as-is if serialization fails

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
        """Proxy all attributes/methods to the wrapped model"""
        return getattr(self.wrapped_model, name)

    def bind_tools(self, tools: Any, **kwargs):
        """Bind tools to the wrapped model"""
        return self.wrapped_model.bind_tools(tools, **kwargs)

    def bind(self, **kwargs):
        """Bind settings to the wrapped model"""
        return self.wrapped_model.bind(**kwargs)
