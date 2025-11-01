"""Configuration merging and validation for AI-Trader."""

import json
import sys
from pathlib import Path
from typing import Dict, Any, Optional


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
