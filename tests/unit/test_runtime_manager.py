"""
Unit tests for api/runtime_manager.py - Runtime config isolation.

Coverage target: 85%+

Tests verify:
- Isolated runtime config file creation
- Config path uniqueness per model-day
- Cleanup operations
- File lifecycle management
"""

import pytest
import os
import json
from pathlib import Path
import tempfile


@pytest.mark.unit
class TestRuntimeConfigCreation:
    """Test runtime config file creation."""

    def test_create_runtime_config(self):
        """Should create unique runtime config file."""
        from api.runtime_manager import RuntimeConfigManager

        with tempfile.TemporaryDirectory() as temp_dir:
            manager = RuntimeConfigManager(data_dir=temp_dir)

            config_path = manager.create_runtime_config(
                job_id="test-job-123",
                model_sig="gpt-5",
                date="2025-01-16"
            )

            # Verify file exists
            assert os.path.exists(config_path)

            # Verify file is in correct location
            assert temp_dir in config_path

            # Verify filename contains identifiers
            assert "gpt-5" in config_path
            assert "2025-01-16" in config_path

    def test_create_runtime_config_contents(self):
        """Should initialize config with correct values."""
        from api.runtime_manager import RuntimeConfigManager

        with tempfile.TemporaryDirectory() as temp_dir:
            manager = RuntimeConfigManager(data_dir=temp_dir)

            config_path = manager.create_runtime_config(
                job_id="test-job-123",
                model_sig="gpt-5",
                date="2025-01-16"
            )

            # Read and verify contents
            with open(config_path, 'r') as f:
                config = json.load(f)

            assert config["TODAY_DATE"] == "2025-01-16"
            assert config["SIGNATURE"] == "gpt-5"
            assert config["IF_TRADE"] is False
            assert config["JOB_ID"] == "test-job-123"

    def test_create_runtime_config_unique_paths(self):
        """Should create unique paths for different model-days."""
        from api.runtime_manager import RuntimeConfigManager

        with tempfile.TemporaryDirectory() as temp_dir:
            manager = RuntimeConfigManager(data_dir=temp_dir)

            path1 = manager.create_runtime_config("job1", "gpt-5", "2025-01-16")
            path2 = manager.create_runtime_config("job1", "claude", "2025-01-16")
            path3 = manager.create_runtime_config("job1", "gpt-5", "2025-01-17")

            # All paths should be different
            assert path1 != path2
            assert path1 != path3
            assert path2 != path3

            # All files should exist
            assert os.path.exists(path1)
            assert os.path.exists(path2)
            assert os.path.exists(path3)

    def test_create_runtime_config_creates_directory(self):
        """Should create data directory in __init__ if it doesn't exist."""
        from api.runtime_manager import RuntimeConfigManager

        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = os.path.join(temp_dir, "data")

            # Directory shouldn't exist yet
            assert not os.path.exists(data_dir)

            # Manager creates directory in __init__
            manager = RuntimeConfigManager(data_dir=data_dir)

            # Directory should be created by __init__
            assert os.path.exists(data_dir)

            config_path = manager.create_runtime_config("job1", "gpt-5", "2025-01-16")

            # Config file should exist
            assert os.path.exists(config_path)


@pytest.mark.unit
class TestRuntimeConfigCleanup:
    """Test runtime config cleanup operations."""

    def test_cleanup_runtime_config(self):
        """Should delete runtime config file."""
        from api.runtime_manager import RuntimeConfigManager

        with tempfile.TemporaryDirectory() as temp_dir:
            manager = RuntimeConfigManager(data_dir=temp_dir)

            config_path = manager.create_runtime_config("job1", "gpt-5", "2025-01-16")
            assert os.path.exists(config_path)

            # Cleanup
            manager.cleanup_runtime_config(config_path)

            # File should be deleted
            assert not os.path.exists(config_path)

    def test_cleanup_nonexistent_file(self):
        """Should handle cleanup of nonexistent file gracefully."""
        from api.runtime_manager import RuntimeConfigManager

        with tempfile.TemporaryDirectory() as temp_dir:
            manager = RuntimeConfigManager(data_dir=temp_dir)

            # Should not raise error
            manager.cleanup_runtime_config("/nonexistent/path.json")

    def test_cleanup_all_runtime_configs(self):
        """Should cleanup all runtime config files."""
        from api.runtime_manager import RuntimeConfigManager

        with tempfile.TemporaryDirectory() as temp_dir:
            manager = RuntimeConfigManager(data_dir=temp_dir)

            # Create multiple configs
            path1 = manager.create_runtime_config("job1", "gpt-5", "2025-01-16")
            path2 = manager.create_runtime_config("job1", "claude", "2025-01-16")
            path3 = manager.create_runtime_config("job2", "gpt-5", "2025-01-17")

            # Also create a non-runtime file (should not be deleted)
            other_file = os.path.join(temp_dir, "other.json")
            with open(other_file, 'w') as f:
                json.dump({"test": "data"}, f)

            # Cleanup all
            count = manager.cleanup_all_runtime_configs()

            # Runtime configs should be deleted
            assert not os.path.exists(path1)
            assert not os.path.exists(path2)
            assert not os.path.exists(path3)

            # Other file should still exist
            assert os.path.exists(other_file)

            # Should return count of deleted files
            assert count == 3

    def test_cleanup_all_empty_directory(self):
        """Should handle cleanup when no runtime configs exist."""
        from api.runtime_manager import RuntimeConfigManager

        with tempfile.TemporaryDirectory() as temp_dir:
            manager = RuntimeConfigManager(data_dir=temp_dir)

            count = manager.cleanup_all_runtime_configs()

            # Should return 0
            assert count == 0


@pytest.mark.unit
class TestRuntimeConfigManager:
    """Test RuntimeConfigManager initialization."""

    def test_init_with_default_path(self):
        """Should initialize with default data directory."""
        from api.runtime_manager import RuntimeConfigManager

        manager = RuntimeConfigManager()

        assert manager.data_dir == Path("data")

    def test_init_with_custom_path(self):
        """Should initialize with custom data directory."""
        from api.runtime_manager import RuntimeConfigManager

        with tempfile.TemporaryDirectory() as temp_dir:
            custom_path = os.path.join(temp_dir, "custom", "path")
            manager = RuntimeConfigManager(data_dir=custom_path)

            assert manager.data_dir == Path(custom_path)
            assert os.path.exists(custom_path)  # Should create the directory


# Coverage target: 85%+ for api/runtime_manager.py
