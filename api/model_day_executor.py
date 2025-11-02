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

    def execute(self) -> Dict[str, Any]:
        """
        Execute trading session and persist results.

        Returns:
            Result dict with success status and metadata

        Process:
            1. Update job_detail status to 'running'
            2. Initialize and run trading agent
            3. Write results to SQLite
            4. Update job_detail status to 'completed' or 'failed'
            5. Cleanup runtime config

        SQLite writes:
            - positions: Trading position record
            - holdings: Portfolio holdings breakdown
            - reasoning_logs: AI reasoning steps (if available)
            - tool_usage: Tool usage statistics (if available)
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

            # Initialize agent
            agent = self._initialize_agent()

            # Run trading session
            logger.info(f"Running trading session for {self.model_sig} on {self.date}")
            session_result = agent.run_trading_session(self.date)

            # Persist results to SQLite
            self._write_results_to_db(agent, session_result)

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

    def _initialize_agent(self):
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

        # Register agent (creates initial position if needed)
        agent.register_agent()

        return agent

    def _write_results_to_db(self, agent, session_result: Dict[str, Any]) -> None:
        """
        Write execution results to SQLite.

        Args:
            agent: Trading agent instance
            session_result: Result from run_trading_session()

        Writes to:
            - positions: Position record with action and P&L
            - holdings: Current portfolio holdings
            - reasoning_logs: AI reasoning steps (if available)
            - tool_usage: Tool usage stats (if available)
        """
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        try:
            # Get current positions and trade info
            positions = agent.get_positions() if hasattr(agent, 'get_positions') else {}
            last_trade = agent.get_last_trade() if hasattr(agent, 'get_last_trade') else None

            # Calculate portfolio value
            current_prices = agent.get_current_prices() if hasattr(agent, 'get_current_prices') else {}
            total_value = self._calculate_portfolio_value(positions, current_prices)

            # Get previous value for P&L calculation
            cursor.execute("""
                SELECT portfolio_value
                FROM positions
                WHERE job_id = ? AND model = ? AND date < ?
                ORDER BY date DESC
                LIMIT 1
            """, (self.job_id, self.model_sig, self.date))

            row = cursor.fetchone()
            previous_value = row[0] if row else 10000.0  # Initial portfolio value

            daily_profit = total_value - previous_value
            daily_return_pct = (daily_profit / previous_value * 100) if previous_value > 0 else 0

            # Determine action_id (sequence number for this model)
            cursor.execute("""
                SELECT COALESCE(MAX(action_id), 0) + 1
                FROM positions
                WHERE job_id = ? AND model = ?
            """, (self.job_id, self.model_sig))

            action_id = cursor.fetchone()[0]

            # Insert position record
            action_type = last_trade.get("action") if last_trade else "no_trade"
            symbol = last_trade.get("symbol") if last_trade else None
            amount = last_trade.get("amount") if last_trade else None
            price = last_trade.get("price") if last_trade else None
            cash = positions.get("CASH", 0.0)

            from datetime import datetime
            created_at = datetime.utcnow().isoformat() + "Z"

            cursor.execute("""
                INSERT INTO positions (
                    job_id, date, model, action_id, action_type, symbol,
                    amount, price, cash, portfolio_value, daily_profit, daily_return_pct, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                self.job_id, self.date, self.model_sig, action_id, action_type,
                symbol, amount, price, cash, total_value,
                daily_profit, daily_return_pct, created_at
            ))

            position_id = cursor.lastrowid

            # Insert holdings
            for symbol, quantity in positions.items():
                cursor.execute("""
                    INSERT INTO holdings (position_id, symbol, quantity)
                    VALUES (?, ?, ?)
                """, (position_id, symbol, float(quantity)))

            # Insert reasoning logs (if available)
            if hasattr(agent, 'get_reasoning_steps'):
                reasoning_steps = agent.get_reasoning_steps()
                for step in reasoning_steps:
                    cursor.execute("""
                        INSERT INTO reasoning_logs (
                            job_id, date, model, step_number, timestamp, content
                        )
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        self.job_id, self.date, self.model_sig,
                        step.get("step"), created_at, step.get("reasoning")
                    ))

            # Insert tool usage (if available)
            if hasattr(agent, 'get_tool_usage') and hasattr(agent, 'get_tool_usage'):
                tool_usage = agent.get_tool_usage()
                for tool_name, count in tool_usage.items():
                    cursor.execute("""
                        INSERT INTO tool_usage (
                            job_id, date, model, tool_name, call_count
                        )
                        VALUES (?, ?, ?, ?, ?)
                    """, (self.job_id, self.date, self.model_sig, tool_name, count))

            conn.commit()
            logger.debug(f"Wrote results to DB for {self.model_sig} on {self.date}")

        finally:
            conn.close()

    def _calculate_portfolio_value(
        self,
        positions: Dict[str, float],
        current_prices: Dict[str, float]
    ) -> float:
        """
        Calculate total portfolio value.

        Args:
            positions: Current holdings (symbol: quantity)
            current_prices: Current market prices (symbol: price)

        Returns:
            Total portfolio value in dollars
        """
        total = 0.0

        for symbol, quantity in positions.items():
            if symbol == "CASH":
                total += quantity
            else:
                price = current_prices.get(symbol, 0.0)
                total += quantity * price

        return total
