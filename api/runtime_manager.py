"""
Runtime configuration manager for isolated model-day execution.

This module provides:
- Isolated runtime config file creation per model-day
- Prevention of state collisions between concurrent executions
- Automatic cleanup of temporary config files
"""

import os
import json
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class RuntimeConfigManager:
    """
    Manages isolated runtime configuration files for concurrent model execution.

    Problem:
        Multiple models running concurrently need separate runtime_env.json files
        to avoid race conditions on TODAY_DATE, SIGNATURE, IF_TRADE values.

    Solution:
        Create temporary runtime config file per model-day execution:
        - /app/data/runtime_env_{job_id}_{model}_{date}.json

    Lifecycle:
        1. create_runtime_config() → Creates temp file
        2. Executor sets RUNTIME_ENV_PATH env var
        3. Agent uses isolated config via get_config_value/write_config_value
        4. cleanup_runtime_config() → Deletes temp file
    """

    def __init__(self, data_dir: str = "data"):
        """
        Initialize RuntimeConfigManager.

        Args:
            data_dir: Directory for runtime config files (default: "data")
        """
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def create_runtime_config(
        self,
        job_id: str,
        model_sig: str,
        date: str,
        trading_day_id: int = None
    ) -> str:
        """
        Create isolated runtime config file for this execution.

        Args:
            job_id: Job UUID
            model_sig: Model signature
            date: Trading date (YYYY-MM-DD)
            trading_day_id: Trading day record ID (optional, can be set later)

        Returns:
            Path to created runtime config file

        Example:
            config_path = manager.create_runtime_config(
                "abc123...",
                "gpt-5",
                "2025-01-16"
            )
            # Returns: "data/runtime_env_abc123_gpt-5_2025-01-16.json"
        """
        # Generate unique filename (use first 8 chars of job_id for brevity)
        job_id_short = job_id[:8] if len(job_id) > 8 else job_id
        filename = f"runtime_env_{job_id_short}_{model_sig}_{date}.json"
        config_path = self.data_dir / filename

        # Initialize with default values
        initial_config = {
            "TODAY_DATE": date,
            "SIGNATURE": model_sig,
            "IF_TRADE": True,  # FIX: Trades are expected by default
            "JOB_ID": job_id,
            "TRADING_DAY_ID": trading_day_id
        }

        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(initial_config, f, indent=4)

        logger.debug(f"Created runtime config: {config_path}")
        return str(config_path)

    def cleanup_runtime_config(self, config_path: str) -> None:
        """
        Delete runtime config file after execution.

        Args:
            config_path: Path to runtime config file

        Note:
            Silently ignores if file doesn't exist (already cleaned up)
        """
        try:
            if os.path.exists(config_path):
                os.unlink(config_path)
                logger.debug(f"Cleaned up runtime config: {config_path}")
        except Exception as e:
            logger.warning(f"Failed to cleanup runtime config {config_path}: {e}")

    def cleanup_all_runtime_configs(self) -> int:
        """
        Cleanup all runtime config files (for maintenance/startup).

        Returns:
            Number of files deleted

        Use case:
            - On API startup to clean stale configs from previous runs
            - Periodic maintenance
        """
        count = 0
        for config_file in self.data_dir.glob("runtime_env_*.json"):
            try:
                config_file.unlink()
                count += 1
                logger.debug(f"Deleted stale runtime config: {config_file}")
            except Exception as e:
                logger.warning(f"Failed to delete {config_file}: {e}")

        if count > 0:
            logger.info(f"Cleaned up {count} stale runtime config files")

        return count
