"""Configuration merging and validation for AI-Trader."""

import json
import sys
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime


class ConfigValidationError(Exception):
    """Raised when config validation fails."""
    pass


def load_config(path: str) -> Dict[str, Any]:
    """
    Load and parse JSON config file.

    Args:
        path: Path to JSON config file

    Returns:
        Parsed config dictionary

    Raises:
        ConfigValidationError: If file not found or invalid JSON
    """
    config_path = Path(path)

    if not config_path.exists():
        raise ConfigValidationError(f"Config file not found: {path}")

    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise ConfigValidationError(f"Invalid JSON in {path}: {e}")


def merge_configs(default: Dict[str, Any], custom: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge custom config into default config (root-level override).

    Custom config sections completely replace default sections.
    Does not mutate input dictionaries.

    Args:
        default: Default configuration dict
        custom: Custom configuration dict (overrides)

    Returns:
        Merged configuration dict
    """
    merged = dict(default)  # Shallow copy

    for key, value in custom.items():
        merged[key] = value

    return merged


def validate_config(config: Dict[str, Any]) -> None:
    """
    Validate configuration structure and values.

    Args:
        config: Configuration dictionary to validate

    Raises:
        ConfigValidationError: If validation fails with detailed message
    """
    # Required top-level fields
    required_fields = ["agent_type", "models", "agent_config", "log_config"]
    for field in required_fields:
        if field not in config:
            raise ConfigValidationError(f"Missing required field: '{field}'")

    # Validate models
    models = config["models"]
    if not isinstance(models, list) or len(models) == 0:
        raise ConfigValidationError("'models' must be a non-empty array")

    # Check at least one enabled model
    enabled_models = [m for m in models if m.get("enabled", False)]
    if not enabled_models:
        raise ConfigValidationError("At least one model must be enabled")

    # Check required model fields
    for i, model in enumerate(models):
        required_model_fields = ["name", "basemodel", "signature", "enabled"]
        for field in required_model_fields:
            if field not in model:
                raise ConfigValidationError(
                    f"Model {i} missing required field: '{field}'"
                )

    # Check for duplicate signatures
    signatures = [m["signature"] for m in models]
    if len(signatures) != len(set(signatures)):
        duplicates = [s for s in signatures if signatures.count(s) > 1]
        raise ConfigValidationError(
            f"Duplicate model signature: {duplicates[0]}"
        )

    # Validate agent_config
    agent_config = config["agent_config"]

    if "max_steps" in agent_config:
        if agent_config["max_steps"] <= 0:
            raise ConfigValidationError("max_steps must be > 0")

    if "max_retries" in agent_config:
        if agent_config["max_retries"] < 0:
            raise ConfigValidationError("max_retries must be >= 0")

    if "initial_cash" in agent_config:
        if agent_config["initial_cash"] <= 0:
            raise ConfigValidationError("initial_cash must be > 0")

    # Validate date_range if present (optional)
    if "date_range" in config:
        date_range = config["date_range"]

        if "init_date" in date_range:
            try:
                init_dt = datetime.strptime(date_range["init_date"], "%Y-%m-%d")
            except ValueError:
                raise ConfigValidationError(
                    f"Invalid date format for init_date: {date_range['init_date']}. "
                    "Expected YYYY-MM-DD"
                )

        if "end_date" in date_range:
            try:
                end_dt = datetime.strptime(date_range["end_date"], "%Y-%m-%d")
            except ValueError:
                raise ConfigValidationError(
                    f"Invalid date format for end_date: {date_range['end_date']}. "
                    "Expected YYYY-MM-DD"
                )

        # Check init <= end
        if "init_date" in date_range and "end_date" in date_range:
            if init_dt > end_dt:
                raise ConfigValidationError(
                    f"init_date must be <= end_date (got {date_range['init_date']} > {date_range['end_date']})"
                )
