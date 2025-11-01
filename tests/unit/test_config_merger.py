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


import os
from tools.config_merger import merge_and_validate


def test_merge_and_validate_success(tmp_path, monkeypatch):
    """Test successful merge and validation"""
    # Create default config
    default_config = {
        "agent_type": "BaseAgent",
        "models": [{"name": "default", "basemodel": "openai/gpt-4", "signature": "default", "enabled": True}],
        "agent_config": {"max_steps": 30, "max_retries": 3, "initial_cash": 10000.0},
        "log_config": {"log_path": "./data"}
    }

    default_path = tmp_path / "default_config.json"
    with open(default_path, 'w') as f:
        json.dump(default_config, f)

    # Create custom config (only overrides models)
    custom_config = {
        "models": [{"name": "custom", "basemodel": "openai/gpt-5", "signature": "custom", "enabled": True}]
    }

    custom_path = tmp_path / "config.json"
    with open(custom_path, 'w') as f:
        json.dump(custom_config, f)

    output_path = tmp_path / "runtime_config.json"

    # Mock file paths
    monkeypatch.setattr("tools.config_merger.DEFAULT_CONFIG_PATH", str(default_path))
    monkeypatch.setattr("tools.config_merger.CUSTOM_CONFIG_PATH", str(custom_path))
    monkeypatch.setattr("tools.config_merger.OUTPUT_CONFIG_PATH", str(output_path))

    # Run merge and validate
    merge_and_validate()

    # Verify output file was created
    assert output_path.exists()

    # Verify merged content
    with open(output_path, 'r') as f:
        result = json.load(f)

    assert result["models"] == [{"name": "custom", "basemodel": "openai/gpt-5", "signature": "custom", "enabled": True}]
    assert result["agent_config"] == {"max_steps": 30, "max_retries": 3, "initial_cash": 10000.0}


def test_merge_and_validate_no_custom_config(tmp_path, monkeypatch):
    """Test when no custom config exists (uses default only)"""
    default_config = {
        "agent_type": "BaseAgent",
        "models": [{"name": "default", "basemodel": "openai/gpt-4", "signature": "default", "enabled": True}],
        "agent_config": {"max_steps": 30, "max_retries": 3, "initial_cash": 10000.0},
        "log_config": {"log_path": "./data"}
    }

    default_path = tmp_path / "default_config.json"
    with open(default_path, 'w') as f:
        json.dump(default_config, f)

    custom_path = tmp_path / "config.json"  # Does not exist
    output_path = tmp_path / "runtime_config.json"

    monkeypatch.setattr("tools.config_merger.DEFAULT_CONFIG_PATH", str(default_path))
    monkeypatch.setattr("tools.config_merger.CUSTOM_CONFIG_PATH", str(custom_path))
    monkeypatch.setattr("tools.config_merger.OUTPUT_CONFIG_PATH", str(output_path))

    merge_and_validate()

    # Verify output matches default
    with open(output_path, 'r') as f:
        result = json.load(f)

    assert result == default_config


def test_merge_and_validate_validation_fails(tmp_path, monkeypatch, capsys):
    """Test validation failure exits with error"""
    default_config = {
        "agent_type": "BaseAgent",
        "models": [{"name": "default", "basemodel": "openai/gpt-4", "signature": "default", "enabled": True}],
        "agent_config": {"max_steps": 30, "max_retries": 3, "initial_cash": 10000.0},
        "log_config": {"log_path": "./data"}
    }

    default_path = tmp_path / "default_config.json"
    with open(default_path, 'w') as f:
        json.dump(default_config, f)

    # Custom config with no enabled models
    custom_config = {
        "models": [{"name": "custom", "basemodel": "openai/gpt-5", "signature": "custom", "enabled": False}]
    }

    custom_path = tmp_path / "config.json"
    with open(custom_path, 'w') as f:
        json.dump(custom_config, f)

    output_path = tmp_path / "runtime_config.json"

    monkeypatch.setattr("tools.config_merger.DEFAULT_CONFIG_PATH", str(default_path))
    monkeypatch.setattr("tools.config_merger.CUSTOM_CONFIG_PATH", str(custom_path))
    monkeypatch.setattr("tools.config_merger.OUTPUT_CONFIG_PATH", str(output_path))

    # Should exit with error
    with pytest.raises(SystemExit) as exc_info:
        merge_and_validate()

    assert exc_info.value.code == 1

    # Check error output (should be in stderr, not stdout)
    captured = capsys.readouterr()
    assert "CONFIG VALIDATION FAILED" in captured.err
    assert "At least one model must be enabled" in captured.err
