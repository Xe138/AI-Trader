import pytest
import json
import tempfile
from pathlib import Path
from tools.config_merger import load_config, ConfigValidationError, merge_configs, validate_config


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


def test_validate_config_valid():
    """Test validation passes for valid config"""
    config = {
        "agent_type": "BaseAgent",
        "models": [
            {"name": "test", "basemodel": "openai/gpt-4", "signature": "test", "enabled": True}
        ],
        "agent_config": {
            "max_steps": 30,
            "max_retries": 3,
            "initial_cash": 10000.0
        },
        "log_config": {"log_path": "./data"}
    }

    validate_config(config)  # Should not raise


def test_validate_config_missing_required_field():
    """Test validation fails for missing required field"""
    config = {"agent_type": "BaseAgent"}  # Missing models, agent_config, log_config

    with pytest.raises(ConfigValidationError, match="Missing required field"):
        validate_config(config)


def test_validate_config_no_enabled_models():
    """Test validation fails when no models are enabled"""
    config = {
        "agent_type": "BaseAgent",
        "models": [
            {"name": "test", "basemodel": "openai/gpt-4", "signature": "test", "enabled": False}
        ],
        "agent_config": {"max_steps": 30, "max_retries": 3, "initial_cash": 10000.0},
        "log_config": {"log_path": "./data"}
    }

    with pytest.raises(ConfigValidationError, match="At least one model must be enabled"):
        validate_config(config)


def test_validate_config_duplicate_signatures():
    """Test validation fails for duplicate model signatures"""
    config = {
        "agent_type": "BaseAgent",
        "models": [
            {"name": "test1", "basemodel": "openai/gpt-4", "signature": "same", "enabled": True},
            {"name": "test2", "basemodel": "openai/gpt-5", "signature": "same", "enabled": True}
        ],
        "agent_config": {"max_steps": 30, "max_retries": 3, "initial_cash": 10000.0},
        "log_config": {"log_path": "./data"}
    }

    with pytest.raises(ConfigValidationError, match="Duplicate model signature"):
        validate_config(config)


def test_validate_config_invalid_max_steps():
    """Test validation fails for invalid max_steps"""
    config = {
        "agent_type": "BaseAgent",
        "models": [{"name": "test", "basemodel": "openai/gpt-4", "signature": "test", "enabled": True}],
        "agent_config": {"max_steps": 0, "max_retries": 3, "initial_cash": 10000.0},
        "log_config": {"log_path": "./data"}
    }

    with pytest.raises(ConfigValidationError, match="max_steps must be > 0"):
        validate_config(config)


def test_validate_config_invalid_date_format():
    """Test validation fails for invalid date format"""
    config = {
        "agent_type": "BaseAgent",
        "date_range": {"init_date": "2025-13-01", "end_date": "2025-12-31"},  # Invalid month
        "models": [{"name": "test", "basemodel": "openai/gpt-4", "signature": "test", "enabled": True}],
        "agent_config": {"max_steps": 30, "max_retries": 3, "initial_cash": 10000.0},
        "log_config": {"log_path": "./data"}
    }

    with pytest.raises(ConfigValidationError, match="Invalid date format"):
        validate_config(config)


def test_validate_config_end_before_init():
    """Test validation fails when end_date before init_date"""
    config = {
        "agent_type": "BaseAgent",
        "date_range": {"init_date": "2025-12-31", "end_date": "2025-01-01"},
        "models": [{"name": "test", "basemodel": "openai/gpt-4", "signature": "test", "enabled": True}],
        "agent_config": {"max_steps": 30, "max_retries": 3, "initial_cash": 10000.0},
        "log_config": {"log_path": "./data"}
    }

    with pytest.raises(ConfigValidationError, match="init_date must be <= end_date"):
        validate_config(config)
