import pytest
import json
import tempfile
from pathlib import Path
from tools.config_merger import load_config, ConfigValidationError, merge_configs


def test_load_config_valid_json():
    """Test loading a valid JSON config file"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump({"key": "value"}, f)
        temp_path = f.name

    try:
        result = load_config(temp_path)
        assert result == {"key": "value"}
    finally:
        Path(temp_path).unlink()


def test_load_config_file_not_found():
    """Test loading non-existent config file"""
    with pytest.raises(ConfigValidationError, match="not found"):
        load_config("/nonexistent/path.json")


def test_load_config_invalid_json():
    """Test loading malformed JSON"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        f.write("{invalid json")
        temp_path = f.name

    try:
        with pytest.raises(ConfigValidationError, match="Invalid JSON"):
            load_config(temp_path)
    finally:
        Path(temp_path).unlink()


def test_merge_configs_empty_custom():
    """Test merge with no custom config"""
    default = {"a": 1, "b": 2}
    custom = {}
    result = merge_configs(default, custom)
    assert result == {"a": 1, "b": 2}


def test_merge_configs_override_section():
    """Test custom config overrides entire sections"""
    default = {
        "models": [{"name": "default-model", "enabled": True}],
        "agent_config": {"max_steps": 30}
    }
    custom = {
        "models": [{"name": "custom-model", "enabled": False}]
    }
    result = merge_configs(default, custom)

    assert result["models"] == [{"name": "custom-model", "enabled": False}]
    assert result["agent_config"] == {"max_steps": 30}


def test_merge_configs_add_new_section():
    """Test custom config adds new sections"""
    default = {"a": 1}
    custom = {"b": 2}
    result = merge_configs(default, custom)
    assert result == {"a": 1, "b": 2}


def test_merge_configs_does_not_mutate_inputs():
    """Test merge doesn't modify original dicts"""
    default = {"a": 1}
    custom = {"a": 2}
    result = merge_configs(default, custom)

    assert default["a"] == 1  # Original unchanged
    assert result["a"] == 2
