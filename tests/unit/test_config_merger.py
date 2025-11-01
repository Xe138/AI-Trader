import pytest
import json
import tempfile
from pathlib import Path
from tools.config_merger import load_config, ConfigValidationError


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
