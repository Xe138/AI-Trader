"""
Single model-day execution engine.

This module provides:
- Isolated execution of one model for one trading day
- Runtime config management per execution
- Result persistence to SQLite (trading_days, actions, holdings)
- Automatic status updates via JobManager
- Cleanup of temporary resources

NOTE: Uses new trading_days schema exclusively.
All data persistence is handled by BaseAgent.
"""

import logging
import os
import asyncio
from typing import Dict, Any, Optional, List, TYPE_CHECKING
from pathlib import Path

from api.runtime_manager import RuntimeConfigManager
from api.job_manager import JobManager
from api.database import get_db_connection

# Lazy import to avoid loading heavy dependencies during testing
if TYPE_CHECKING:
    from agent.base_agent.base_agent import BaseAgent

logger = logging.getLogger(__name__)


class ModelDayExecutor:
    """
    Executes a single model for a single trading day.

    Responsibilities:
        - Create isolated runtime config
        - Initialize and run trading agent
        - Persist results to SQLite
        - Update job status
        - Cleanup resources

    Lifecycle:
        1. __init__() → Create runtime config
        2. execute() → Run agent, write results, update status
        3. cleanup → Delete runtime config
    """

    def __init__(
        self,
        job_id: str,
        date: str,
        model_sig: str,
        config_path: str,
        db_path: str = "data/jobs.db",
        data_dir: str = "data"
    ):
        """
        Initialize ModelDayExecutor.

        Args:
            job_id: Job UUID
            date: Trading date (YYYY-MM-DD)
            model_sig: Model signature
            config_path: Path to configuration file
            db_path: Path to SQLite database
            data_dir: Data directory for runtime configs
        """
        self.job_id = job_id
        self.date = date
        self.model_sig = model_sig
        self.config_path = config_path
        self.db_path = db_path
        self.data_dir = data_dir

        # Create isolated runtime config
        self.runtime_manager = RuntimeConfigManager(data_dir=data_dir)
        self.runtime_config_path = self.runtime_manager.create_runtime_config(
            job_id=job_id,
            model_sig=model_sig,
            date=date
        )

        self.job_manager = JobManager(db_path=db_path)

        logger.info(f"Initialized executor for {model_sig} on {date} (job: {job_id})")

    async def execute_async(self) -> Dict[str, Any]:
        """
        Execute trading session and persist results (async version).

        Returns:
            Result dict with success status and metadata

        Process:
            1. Update job_detail status to 'running'
            2. Create trading_day record with P&L metrics
            3. Initialize and run trading agent
            4. Agent writes actions and updates trading_day
            5. Update job_detail status to 'completed' or 'failed'
            6. Cleanup runtime config

        SQLite writes:
            - trading_days: Complete day record with P&L, reasoning, holdings
            - actions: Trade execution ledger
            - holdings: Ending positions snapshot
        """
        try:
            # Update status to running
            self.job_manager.update_job_detail_status(
                self.job_id,
                self.date,
                self.model_sig,
                "running"
            )


            # Set environment variable for agent to use isolated config
            os.environ["RUNTIME_ENV_PATH"] = self.runtime_config_path

            # Initialize agent (without context)
            agent = await self._initialize_agent()

            # Create and inject context with correct values
            from agent.context_injector import ContextInjector
            from tools.general_tools import get_config_value
            trading_day_id = get_config_value('TRADING_DAY_ID')  # Get from runtime config

            context_injector = ContextInjector(
                signature=self.model_sig,
                today_date=self.date,  # Current trading day
                job_id=self.job_id,
                session_id=0,  # Deprecated, kept for compatibility
                trading_day_id=trading_day_id
            )
            logger.info(f"[DEBUG] ModelDayExecutor: Created ContextInjector with signature={self.model_sig}, date={self.date}, job_id={self.job_id}, trading_day_id={trading_day_id}")
            logger.info(f"[DEBUG] ModelDayExecutor: Calling await agent.set_context()")
            await agent.set_context(context_injector)
            logger.info(f"[DEBUG] ModelDayExecutor: set_context() completed")

            # Run trading session
            logger.info(f"Running trading session for {self.model_sig} on {self.date}")
            session_result = await agent.run_trading_session(self.date)

            # Note: All data persistence is handled by BaseAgent:
            # - trading_days record created with P&L metrics
            # - actions recorded during trading
            # - holdings snapshot saved at end of day
            # - reasoning stored in trading_days.reasoning_full

            # Update status to completed
            self.job_manager.update_job_detail_status(
                self.job_id,
                self.date,
                self.model_sig,
                "completed"
            )

            logger.info(f"Successfully completed {self.model_sig} on {self.date}")

            return {
                "success": True,
                "job_id": self.job_id,
                "date": self.date,
                "model": self.model_sig,
                "session_result": session_result
            }

        except Exception as e:
            error_msg = f"Execution failed: {str(e)}"
            logger.error(f"{self.model_sig} on {self.date}: {error_msg}", exc_info=True)

            # Update status to failed
            self.job_manager.update_job_detail_status(
                self.job_id,
                self.date,
                self.model_sig,
                "failed",
                error=error_msg
            )

            return {
                "success": False,
                "job_id": self.job_id,
                "date": self.date,
                "model": self.model_sig,
                "error": error_msg
            }

        finally:
            # Always cleanup runtime config
            self.runtime_manager.cleanup_runtime_config(self.runtime_config_path)

    def execute_sync(self) -> Dict[str, Any]:
        """Synchronous wrapper for execute_async()."""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        return loop.run_until_complete(self.execute_async())

    def execute(self) -> Dict[str, Any]:
        """Execute model-day simulation (sync entry point)."""
        return self.execute_sync()

    async def _initialize_agent(self):
        """
        Initialize trading agent with config.

        Returns:
            Configured BaseAgent instance
        """
        # Lazy import to avoid loading heavy dependencies during testing
        from agent.base_agent.base_agent import BaseAgent

        # Load config
        import json
        with open(self.config_path, 'r') as f:
            config = json.load(f)

        # Find model config
        model_config = None
        for model in config.get("models", []):
            if model.get("signature") == self.model_sig:
                model_config = model
                break

        if not model_config:
            raise ValueError(f"Model {self.model_sig} not found in config")

        # Get agent config
        agent_config = config.get("agent_config", {})
        log_config = config.get("log_config", {})

        # Initialize agent with properly mapped parameters
        agent = BaseAgent(
            signature=self.model_sig,
            basemodel=model_config.get("basemodel"),
            stock_symbols=agent_config.get("stock_symbols"),
            mcp_config=agent_config.get("mcp_config"),
            log_path=log_config.get("log_path"),
            max_steps=agent_config.get("max_steps", 10),
            max_retries=agent_config.get("max_retries", 3),
            base_delay=agent_config.get("base_delay", 0.5),
            openai_base_url=model_config.get("openai_base_url"),
            openai_api_key=model_config.get("openai_api_key"),
            initial_cash=agent_config.get("initial_cash", 10000.0),
            init_date=config.get("date_range", {}).get("init_date", "2025-10-13")
        )

        # Note: In API mode, we don't call register_agent() because:
        # - Position data is stored in SQLite database, not files
        # - Database initialization is handled by JobManager
        # - File-based position tracking is only for standalone/CLI mode

        # Initialize MCP client and AI model
        await agent.initialize()

        return agent




