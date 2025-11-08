"""Unit tests for tools/general_tools.py"""
import pytest
import os
import json
import tempfile
from pathlib import Path
from tools.general_tools import (
    get_config_value,
    write_config_value,
    extract_conversation,
    extract_tool_messages,
    extract_first_tool_message_content
)


@pytest.fixture
def temp_runtime_env(tmp_path):
    """Create temporary runtime environment file."""
    env_file = tmp_path / "runtime_env.json"
    original_path = os.environ.get("RUNTIME_ENV_PATH")

    os.environ["RUNTIME_ENV_PATH"] = str(env_file)

    yield env_file

    # Cleanup
    if original_path:
        os.environ["RUNTIME_ENV_PATH"] = original_path
    else:
        os.environ.pop("RUNTIME_ENV_PATH", None)


@pytest.mark.unit
class TestConfigManagement:
    """Test configuration value reading and writing."""

    def test_get_config_value_from_env(self):
        """Should read from environment variables."""
        os.environ["TEST_KEY"] = "test_value"
        result = get_config_value("TEST_KEY")
        assert result == "test_value"
        os.environ.pop("TEST_KEY")

    def test_get_config_value_default(self):
        """Should return default when key not found."""
        result = get_config_value("NONEXISTENT_KEY", "default_value")
        assert result == "default_value"

    def test_get_config_value_from_runtime_env(self, temp_runtime_env):
        """Should read from runtime env file."""
        temp_runtime_env.write_text('{"RUNTIME_KEY": "runtime_value"}')
        result = get_config_value("RUNTIME_KEY")
        assert result == "runtime_value"

    def test_get_config_value_runtime_overrides_env(self, temp_runtime_env):
        """Runtime env should override environment variables."""
        os.environ["OVERRIDE_KEY"] = "env_value"
        temp_runtime_env.write_text('{"OVERRIDE_KEY": "runtime_value"}')

        result = get_config_value("OVERRIDE_KEY")
        assert result == "runtime_value"

        os.environ.pop("OVERRIDE_KEY")

    def test_write_config_value_creates_file(self, temp_runtime_env):
        """Should create runtime env file if it doesn't exist."""
        write_config_value("NEW_KEY", "new_value")

        assert temp_runtime_env.exists()
        data = json.loads(temp_runtime_env.read_text())
        assert data["NEW_KEY"] == "new_value"

    def test_write_config_value_updates_existing(self, temp_runtime_env):
        """Should update existing values in runtime env."""
        temp_runtime_env.write_text('{"EXISTING": "old"}')

        write_config_value("EXISTING", "new")
        write_config_value("ANOTHER", "value")

        data = json.loads(temp_runtime_env.read_text())
        assert data["EXISTING"] == "new"
        assert data["ANOTHER"] == "value"

    def test_write_config_value_no_path_set(self, capsys):
        """Should warn when RUNTIME_ENV_PATH not set."""
        os.environ.pop("RUNTIME_ENV_PATH", None)

        write_config_value("TEST", "value")

        captured = capsys.readouterr()
        assert "WARNING" in captured.out
        assert "RUNTIME_ENV_PATH not set" in captured.out


@pytest.mark.unit
class TestExtractConversation:
    """Test conversation extraction functions."""

    def test_extract_conversation_final_with_stop(self):
        """Should extract final message with finish_reason='stop'."""
        conversation = {
            "messages": [
                {"content": "Hello", "response_metadata": {"finish_reason": "stop"}},
                {"content": "World", "response_metadata": {"finish_reason": "stop"}}
            ]
        }

        result = extract_conversation(conversation, "final")
        assert result == "World"

    def test_extract_conversation_final_fallback(self):
        """Should fallback to last non-tool message."""
        conversation = {
            "messages": [
                {"content": "First message"},
                {"content": "Second message"},
                {"content": "", "additional_kwargs": {"tool_calls": [{"name": "tool"}]}}
            ]
        }

        result = extract_conversation(conversation, "final")
        assert result == "Second message"

    def test_extract_conversation_final_no_messages(self):
        """Should return None when no suitable messages."""
        conversation = {"messages": []}

        result = extract_conversation(conversation, "final")
        assert result is None

    def test_extract_conversation_final_only_tool_calls(self):
        """Should return None when only tool calls exist."""
        conversation = {
            "messages": [
                {"content": "tool result", "tool_call_id": "123"}
            ]
        }

        result = extract_conversation(conversation, "final")
        assert result is None

    def test_extract_conversation_all(self):
        """Should return all messages."""
        messages = [
            {"content": "Message 1"},
            {"content": "Message 2"}
        ]
        conversation = {"messages": messages}

        result = extract_conversation(conversation, "all")
        assert result == messages

    def test_extract_conversation_invalid_type(self):
        """Should raise ValueError for invalid output_type."""
        conversation = {"messages": []}

        with pytest.raises(ValueError, match="output_type must be 'final' or 'all'"):
            extract_conversation(conversation, "invalid")

    def test_extract_conversation_missing_messages(self):
        """Should handle missing messages gracefully."""
        conversation = {}

        result = extract_conversation(conversation, "all")
        assert result == []

        result = extract_conversation(conversation, "final")
        assert result is None


@pytest.mark.unit
class TestExtractToolMessages:
    """Test tool message extraction."""

    def test_extract_tool_messages_with_tool_call_id(self):
        """Should extract messages with tool_call_id."""
        conversation = {
            "messages": [
                {"content": "Regular message"},
                {"content": "Tool result", "tool_call_id": "call_123"},
                {"content": "Another regular"}
            ]
        }

        result = extract_tool_messages(conversation)
        assert len(result) == 1
        assert result[0]["tool_call_id"] == "call_123"

    def test_extract_tool_messages_with_name(self):
        """Should extract messages with tool name."""
        conversation = {
            "messages": [
                {"content": "Tool output", "name": "get_price"},
                {"content": "AI response", "response_metadata": {"finish_reason": "stop"}}
            ]
        }

        result = extract_tool_messages(conversation)
        assert len(result) == 1
        assert result[0]["name"] == "get_price"

    def test_extract_tool_messages_none_found(self):
        """Should return empty list when no tool messages."""
        conversation = {
            "messages": [
                {"content": "Message 1"},
                {"content": "Message 2"}
            ]
        }

        result = extract_tool_messages(conversation)
        assert result == []

    def test_extract_first_tool_message_content(self):
        """Should extract content from first tool message."""
        conversation = {
            "messages": [
                {"content": "Regular"},
                {"content": "First tool", "tool_call_id": "1"},
                {"content": "Second tool", "tool_call_id": "2"}
            ]
        }

        result = extract_first_tool_message_content(conversation)
        assert result == "First tool"

    def test_extract_first_tool_message_content_none(self):
        """Should return None when no tool messages."""
        conversation = {"messages": [{"content": "Regular"}]}

        result = extract_first_tool_message_content(conversation)
        assert result is None

    def test_extract_tool_messages_object_based(self):
        """Should work with object-based messages."""
        class Message:
            def __init__(self, content, tool_call_id=None):
                self.content = content
                self.tool_call_id = tool_call_id

        conversation = {
            "messages": [
                Message("Regular"),
                Message("Tool result", tool_call_id="abc123")
            ]
        }

        result = extract_tool_messages(conversation)
        assert len(result) == 1
        assert result[0].tool_call_id == "abc123"


@pytest.mark.unit
class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_get_config_value_none_default(self):
        """Should handle None as default value."""
        result = get_config_value("MISSING_KEY", None)
        assert result is None

    def test_extract_conversation_whitespace_only(self):
        """Should skip whitespace-only content."""
        conversation = {
            "messages": [
                {"content": "   ", "response_metadata": {"finish_reason": "stop"}},
                {"content": "Valid content"}
            ]
        }

        result = extract_conversation(conversation, "final")
        assert result == "Valid content"

    def test_write_config_value_with_special_chars(self, temp_runtime_env):
        """Should handle special characters in values."""
        write_config_value("SPECIAL", "value with 日本語 and émojis 🎉")

        data = json.loads(temp_runtime_env.read_text())
        assert data["SPECIAL"] == "value with 日本語 and émojis 🎉"

    def test_write_config_value_invalid_path(self, capsys):
        """Should handle write errors gracefully."""
        os.environ["RUNTIME_ENV_PATH"] = "/invalid/nonexistent/path/config.json"

        write_config_value("TEST", "value")

        captured = capsys.readouterr()
        assert "Error writing config" in captured.out

        # Cleanup
        os.environ.pop("RUNTIME_ENV_PATH", None)

    def test_extract_conversation_with_object_messages(self):
        """Should work with object-based messages (not just dicts)."""
        class Message:
            def __init__(self, content, response_metadata=None):
                self.content = content
                self.response_metadata = response_metadata or {}

        class ResponseMetadata:
            def __init__(self, finish_reason):
                self.finish_reason = finish_reason

        conversation = {
            "messages": [
                Message("First", ResponseMetadata("stop")),
                Message("Second", ResponseMetadata("stop"))
            ]
        }

        result = extract_conversation(conversation, "final")
        assert result == "Second"

    def test_extract_first_tool_message_content_with_object(self):
        """Should extract content from object-based tool messages."""
        class ToolMessage:
            def __init__(self, content):
                self.content = content
                self.tool_call_id = "test123"

        conversation = {
            "messages": [
                ToolMessage("Tool output")
            ]
        }

        result = extract_first_tool_message_content(conversation)
        assert result == "Tool output"
