"""Integration tests for config override system."""

import pytest
import json
import subprocess
import tempfile
from pathlib import Path


@pytest.fixture
def test_configs(tmp_path):
    """Create test config files."""
    # Default config
    default_config = {
        "agent_type": "BaseAgent",
        "date_range": {"init_date": "2025-10-01", "end_date": "2025-10-21"},
        "models": [
            {"name": "default-model", "basemodel": "openai/gpt-4", "signature": "default", "enabled": True}
        ],
        "agent_config": {"max_steps": 30, "max_retries": 3, "base_delay": 1.0, "initial_cash": 10000.0},
        "log_config": {"log_path": "./data/agent_data"}
    }

    configs_dir = tmp_path / "configs"
    configs_dir.mkdir()

    default_path = configs_dir / "default_config.json"
    with open(default_path, 'w') as f:
        json.dump(default_config, f, indent=2)

    return configs_dir, default_config


def test_config_override_models_only(test_configs):
    """Test overriding only the models section."""
    configs_dir, default_config = test_configs

    # Custom config - only override models
    custom_config = {
        "models": [
            {"name": "gpt-5", "basemodel": "openai/gpt-5", "signature": "gpt-5", "enabled": True}
        ]
    }

    user_configs_dir = configs_dir.parent / "user-configs"
    user_configs_dir.mkdir()

    custom_path = user_configs_dir / "config.json"
    with open(custom_path, 'w') as f:
        json.dump(custom_config, f, indent=2)

    # Run merge
    result = subprocess.run(
        [
            "python", "-c",
            f"import sys; sys.path.insert(0, '.'); "
            f"from tools.config_merger import DEFAULT_CONFIG_PATH, CUSTOM_CONFIG_PATH, OUTPUT_CONFIG_PATH, merge_and_validate; "
            f"import tools.config_merger; "
            f"tools.config_merger.DEFAULT_CONFIG_PATH = '{configs_dir}/default_config.json'; "
            f"tools.config_merger.CUSTOM_CONFIG_PATH = '{custom_path}'; "
            f"tools.config_merger.OUTPUT_CONFIG_PATH = '{configs_dir.parent}/runtime.json'; "
            f"merge_and_validate()"
        ],
        capture_output=True,
        text=True,
        cwd="/home/bballou/AI-Trader/.worktrees/async-price-download"
    )

    assert result.returncode == 0, f"Merge failed: {result.stderr}"

    # Verify merged config
    runtime_path = configs_dir.parent / "runtime.json"
    with open(runtime_path, 'r') as f:
        merged = json.load(f)

    # Models should be overridden
    assert merged["models"] == custom_config["models"]

    # Other sections should be from default
    assert merged["agent_config"] == default_config["agent_config"]
    assert merged["date_range"] == default_config["date_range"]


def test_config_validation_fails_gracefully(test_configs):
    """Test that invalid config causes exit with clear error."""
    configs_dir, _ = test_configs

    # Invalid custom config (no enabled models)
    custom_config = {
        "models": [
            {"name": "test", "basemodel": "openai/gpt-4", "signature": "test", "enabled": False}
        ]
    }

    user_configs_dir = configs_dir.parent / "user-configs"
    user_configs_dir.mkdir()

    custom_path = user_configs_dir / "config.json"
    with open(custom_path, 'w') as f:
        json.dump(custom_config, f, indent=2)

    # Run merge (should fail)
    result = subprocess.run(
        [
            "python", "-c",
            f"import sys; sys.path.insert(0, '.'); "
            f"from tools.config_merger import merge_and_validate; "
            f"import tools.config_merger; "
            f"tools.config_merger.DEFAULT_CONFIG_PATH = '{configs_dir}/default_config.json'; "
            f"tools.config_merger.CUSTOM_CONFIG_PATH = '{custom_path}'; "
            f"tools.config_merger.OUTPUT_CONFIG_PATH = '{configs_dir.parent}/runtime.json'; "
            f"merge_and_validate()"
        ],
        capture_output=True,
        text=True,
        cwd="/home/bballou/AI-Trader/.worktrees/async-price-download"
    )

    assert result.returncode == 1
    assert "CONFIG VALIDATION FAILED" in result.stderr
    assert "At least one model must be enabled" in result.stderr
