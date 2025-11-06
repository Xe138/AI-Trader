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
            """Patched parse_tool_call to log what it returns"""
            result = original_parse_tool_call(raw_tool_call, partial=partial, strict=strict, return_id=return_id)
            if result:
                args_type = type(result.get('args', None)).__name__
                print(f"[DIAGNOSTIC] parse_tool_call returned: args type = {args_type}")
                if args_type == 'str':
                    print(f"[DIAGNOSTIC] ⚠️ BUG FOUND! parse_tool_call returned STRING args: {result['args']}")
            return result

        # Replace in base.py's namespace (where _convert_dict_to_message uses it)
        langchain_base.parse_tool_call = patched_parse_tool_call

        original_create_chat_result = self.wrapped_model._create_chat_result

        @wraps(original_create_chat_result)
        def patched_create_chat_result(response: Any, generation_info: Optional[Dict] = None):
            """Patched version with diagnostic logging and args parsing"""
            import traceback
            response_dict = response if isinstance(response, dict) else response.model_dump()

            # DIAGNOSTIC: Log response structure for debugging
            print(f"\n[DIAGNOSTIC] _create_chat_result called")
            print(f"  Response type: {type(response)}")
            print(f"  Call stack:")
            for line in traceback.format_stack()[-5:-1]:  # Show last 4 stack frames
                print(f"    {line.strip()}")
            print(f"\n[DIAGNOSTIC] Response structure:")
            print(f"  Response keys: {list(response_dict.keys())}")

            if 'choices' in response_dict and response_dict['choices']:
                choice = response_dict['choices'][0]
                print(f"  Choice keys: {list(choice.keys())}")

                if 'message' in choice:
                    message = choice['message']
                    print(f"  Message keys: {list(message.keys())}")

                    # Check for raw tool_calls in message (before parse_tool_call processing)
                    if 'tool_calls' in message:
                        tool_calls_value = message['tool_calls']
                        print(f"  message['tool_calls'] type: {type(tool_calls_value)}")

                        if tool_calls_value:
                            print(f"  tool_calls count: {len(tool_calls_value)}")
                            for i, tc in enumerate(tool_calls_value):  # Show ALL
                                print(f"  tool_calls[{i}] type: {type(tc)}")
                                print(f"  tool_calls[{i}] keys: {list(tc.keys()) if isinstance(tc, dict) else 'N/A'}")
                                if isinstance(tc, dict):
                                    if 'function' in tc:
                                        print(f"    function keys: {list(tc['function'].keys())}")
                                        if 'arguments' in tc['function']:
                                            args = tc['function']['arguments']
                                            print(f"    function.arguments type: {type(args).__name__}")
                                            print(f"    function.arguments value: {str(args)[:100]}")
                                    if 'args' in tc:
                                        print(f"    ALSO HAS 'args' KEY: type={type(tc['args']).__name__}")
                                        print(f"    args value: {str(tc['args'])[:100]}")

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
            print(f"[DIAGNOSTIC] Calling original_create_chat_result...")
            result = original_create_chat_result(response_dict, generation_info)
            print(f"[DIAGNOSTIC] original_create_chat_result returned successfully")
            print(f"[DIAGNOSTIC] Result type: {type(result)}")
            if hasattr(result, 'generations') and result.generations:
                gen = result.generations[0]
                if hasattr(gen, 'message') and hasattr(gen.message, 'tool_calls'):
                    print(f"[DIAGNOSTIC] Result has {len(gen.message.tool_calls)} tool_calls")
                    if gen.message.tool_calls:
                        tc = gen.message.tool_calls[0]
                        print(f"[DIAGNOSTIC] tool_calls[0]['args'] type in result: {type(tc['args'])}")
            return result

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
