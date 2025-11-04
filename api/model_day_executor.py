"""
Single model-day execution engine.

This module provides:
- Isolated execution of one model for one trading day
- Runtime config management per execution
- Result persistence to SQLite (positions, holdings, reasoning)
- Automatic status updates via JobManager
- Cleanup of temporary resources
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
            2. Create trading session
            3. Initialize and run trading agent
            4. Store reasoning logs with summaries
            5. Update session summary
            6. Write results to SQLite
            7. Update job_detail status to 'completed' or 'failed'
            8. Cleanup runtime config

        SQLite writes:
            - trading_sessions: Session metadata and summary
            - reasoning_logs: Conversation history with summaries
            - positions: Trading position record (linked to session)
            - holdings: Portfolio holdings breakdown
            - tool_usage: Tool usage statistics (if available)
        """
        conn = None
        try:
            # Update status to running
            self.job_manager.update_job_detail_status(
                self.job_id,
                self.date,
                self.model_sig,
                "running"
            )

            # Create trading session at start
            conn = get_db_connection(self.db_path)
            cursor = conn.cursor()
            session_id = self._create_trading_session(cursor)
            conn.commit()

            # Initialize starting position if this is first day
            self._initialize_starting_position(cursor, session_id)
            conn.commit()

            # Set environment variable for agent to use isolated config
            os.environ["RUNTIME_ENV_PATH"] = self.runtime_config_path

            # Initialize agent (without context)
            agent = await self._initialize_agent()

            # Create and inject context with correct values
            from agent.context_injector import ContextInjector
            context_injector = ContextInjector(
                signature=self.model_sig,
                today_date=self.date,  # Current trading day
                job_id=self.job_id,
                session_id=session_id
            )
            logger.info(f"[DEBUG] ModelDayExecutor: Created ContextInjector with signature={self.model_sig}, date={self.date}, job_id={self.job_id}, session_id={session_id}")
            logger.info(f"[DEBUG] ModelDayExecutor: Calling await agent.set_context()")
            await agent.set_context(context_injector)
            logger.info(f"[DEBUG] ModelDayExecutor: set_context() completed")

            # Run trading session
            logger.info(f"Running trading session for {self.model_sig} on {self.date}")
            session_result = await agent.run_trading_session(self.date)

            # Get conversation history
            conversation = agent.get_conversation_history()

            # Store reasoning logs with summaries
            await self._store_reasoning_logs(cursor, session_id, conversation, agent)

            # Update session summary
            await self._update_session_summary(cursor, session_id, conversation, agent)

            # Commit and close connection
            conn.commit()
            conn.close()
            conn = None  # Mark as closed

            # Note: Positions are written by trade tools (buy/sell) or no_trade_record
            # No need to write positions here - that was creating duplicate/corrupt records

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
                "session_id": session_id,
                "session_result": session_result
            }

        except Exception as e:
            error_msg = f"Execution failed: {str(e)}"
            logger.error(f"{self.model_sig} on {self.date}: {error_msg}", exc_info=True)

            if conn:
                conn.rollback()

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
            if conn:
                conn.close()
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

    def _create_trading_session(self, cursor) -> int:
        """
        Create trading session record.

        Args:
            cursor: Database cursor

        Returns:
            session_id (int)
        """
        from datetime import datetime

        started_at = datetime.utcnow().isoformat() + "Z"

        cursor.execute("""
            INSERT INTO trading_sessions (
                job_id, date, model, started_at
            )
            VALUES (?, ?, ?, ?)
        """, (self.job_id, self.date, self.model_sig, started_at))

        return cursor.lastrowid

    def _initialize_starting_position(self, cursor, session_id: int) -> None:
        """
        Initialize starting position if no prior positions exist for this job+model.

        Creates action_id=0 position with initial_cash and zero stock holdings.

        Args:
            cursor: Database cursor
            session_id: Trading session ID
        """
        # Check if any positions exist for this job+model
        cursor.execute("""
            SELECT COUNT(*) FROM positions
            WHERE job_id = ? AND model = ?
        """, (self.job_id, self.model_sig))

        if cursor.fetchone()[0] > 0:
            # Positions already exist, no initialization needed
            return

        # Load config to get initial_cash
        import json
        with open(self.config_path, 'r') as f:
            config = json.load(f)

        agent_config = config.get("agent_config", {})
        initial_cash = agent_config.get("initial_cash", 10000.0)

        # Create initial position record
        from datetime import datetime
        created_at = datetime.utcnow().isoformat() + "Z"

        cursor.execute("""
            INSERT INTO positions (
                job_id, date, model, action_id, action_type,
                cash, portfolio_value, session_id, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            self.job_id, self.date, self.model_sig, 0, "no_trade",
            initial_cash, initial_cash, session_id, created_at
        ))

        logger.info(f"Initialized starting position for {self.model_sig} with ${initial_cash}")

    async def _store_reasoning_logs(
        self,
        cursor,
        session_id: int,
        conversation: List[Dict[str, Any]],
        agent: Any
    ) -> None:
        """
        Store reasoning logs with AI-generated summaries.

        Args:
            cursor: Database cursor
            session_id: Trading session ID
            conversation: List of messages from agent
            agent: BaseAgent instance for summary generation
        """
        for idx, message in enumerate(conversation):
            summary = None

            # Generate summary for assistant messages
            if message["role"] == "assistant":
                summary = await agent.generate_summary(message["content"])

            cursor.execute("""
                INSERT INTO reasoning_logs (
                    session_id, message_index, role, content,
                    summary, tool_name, tool_input, timestamp
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                session_id,
                idx,
                message["role"],
                message["content"],
                summary,
                message.get("tool_name"),
                message.get("tool_input"),
                message["timestamp"]
            ))

    async def _update_session_summary(
        self,
        cursor,
        session_id: int,
        conversation: List[Dict[str, Any]],
        agent: Any
    ) -> None:
        """
        Update session with overall summary.

        Args:
            cursor: Database cursor
            session_id: Trading session ID
            conversation: List of messages from agent
            agent: BaseAgent instance for summary generation
        """
        from datetime import datetime

        # Concatenate all assistant messages
        assistant_messages = [
            msg["content"]
            for msg in conversation
            if msg["role"] == "assistant"
        ]

        combined_content = "\n\n".join(assistant_messages)

        # Generate session summary (longer: 500 chars)
        session_summary = await agent.generate_summary(combined_content, max_length=500)

        completed_at = datetime.utcnow().isoformat() + "Z"

        cursor.execute("""
            UPDATE trading_sessions
            SET session_summary = ?,
                completed_at = ?,
                total_messages = ?
            WHERE id = ?
        """, (session_summary, completed_at, len(conversation), session_id))
