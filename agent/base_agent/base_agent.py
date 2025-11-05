"""
BaseAgent class - Base class for trading agents
Encapsulates core functionality including MCP tool management, AI agent creation, and trading execution
"""

import os
import json
import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from pathlib import Path

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from dotenv import load_dotenv

# Import project tools
import sys
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from tools.general_tools import extract_conversation, extract_tool_messages, get_config_value, write_config_value
from tools.price_tools import add_no_trade_record
from prompts.agent_prompt import get_agent_system_prompt, STOP_SIGNAL
from tools.deployment_config import (
    is_dev_mode,
    get_data_path,
    log_api_key_warning,
    get_deployment_mode
)
from agent.context_injector import ContextInjector
from agent.pnl_calculator import DailyPnLCalculator
from agent.reasoning_summarizer import ReasoningSummarizer

# Load environment variables
load_dotenv()


class BaseAgent:
    """
    Base class for trading agents
    
    Main functionalities:
    1. MCP tool management and connection
    2. AI agent creation and configuration
    3. Trading execution and decision loops
    4. Logging and management
    5. Position and configuration management
    """
    
    # Default NASDAQ 100 stock symbols
    DEFAULT_STOCK_SYMBOLS = [
        "NVDA", "MSFT", "AAPL", "GOOG", "GOOGL", "AMZN", "META", "AVGO", "TSLA",
        "NFLX", "PLTR", "COST", "ASML", "AMD", "CSCO", "AZN", "TMUS", "MU", "LIN",
        "PEP", "SHOP", "APP", "INTU", "AMAT", "LRCX", "PDD", "QCOM", "ARM", "INTC",
        "BKNG", "AMGN", "TXN", "ISRG", "GILD", "KLAC", "PANW", "ADBE", "HON",
        "CRWD", "CEG", "ADI", "ADP", "DASH", "CMCSA", "VRTX", "MELI", "SBUX",
        "CDNS", "ORLY", "SNPS", "MSTR", "MDLZ", "ABNB", "MRVL", "CTAS", "TRI",
        "MAR", "MNST", "CSX", "ADSK", "PYPL", "FTNT", "AEP", "WDAY", "REGN", "ROP",
        "NXPI", "DDOG", "AXON", "ROST", "IDXX", "EA", "PCAR", "FAST", "EXC", "TTWO",
        "XEL", "ZS", "PAYX", "WBD", "BKR", "CPRT", "CCEP", "FANG", "TEAM", "CHTR",
        "KDP", "MCHP", "GEHC", "VRSK", "CTSH", "CSGP", "KHC", "ODFL", "DXCM", "TTD",
        "ON", "BIIB", "LULU", "CDW", "GFS"
    ]
    
    def __init__(
        self,
        signature: str,
        basemodel: str,
        stock_symbols: Optional[List[str]] = None,
        mcp_config: Optional[Dict[str, Dict[str, Any]]] = None,
        log_path: Optional[str] = None,
        max_steps: int = 10,
        max_retries: int = 3,
        base_delay: float = 0.5,
        openai_base_url: Optional[str] = None,
        openai_api_key: Optional[str] = None,
        initial_cash: float = 10000.0,
        init_date: str = "2025-10-13"
    ):
        """
        Initialize BaseAgent

        Args:
            signature: Agent signature/name
            basemodel: Base model name
            stock_symbols: List of stock symbols, defaults to NASDAQ 100
            mcp_config: MCP tool configuration, including port and URL information
            log_path: Data path for position files (JSONL logging removed, kept for backward compatibility)
            max_steps: Maximum reasoning steps
            max_retries: Maximum retry attempts
            base_delay: Base delay time for retries
            openai_base_url: OpenAI API base URL
            openai_api_key: OpenAI API key
            initial_cash: Initial cash amount
            init_date: Initialization date
        """
        self.signature = signature
        self.basemodel = basemodel
        self.stock_symbols = stock_symbols or self.DEFAULT_STOCK_SYMBOLS
        self.max_steps = max_steps
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.initial_cash = initial_cash
        self.init_date = init_date

        # Set MCP configuration
        self.mcp_config = mcp_config or self._get_default_mcp_config()

        # Set data path (apply deployment mode path resolution)
        # Note: Used for position files only; JSONL logging has been removed
        self.base_log_path = get_data_path(log_path or "./data/agent_data")
        
        # Set OpenAI configuration
        if openai_base_url==None:
            self.openai_base_url = os.getenv("OPENAI_API_BASE")
        else:
            self.openai_base_url = openai_base_url
        if openai_api_key==None:
            self.openai_api_key = os.getenv("OPENAI_API_KEY")
        else:
            self.openai_api_key = openai_api_key
        
        # Initialize components
        self.client: Optional[MultiServerMCPClient] = None
        self.tools: Optional[List] = None
        self.model: Optional[ChatOpenAI] = None
        self.agent: Optional[Any] = None

        # Context injector for MCP tools
        self.context_injector: Optional[ContextInjector] = None
        
        # Data paths
        self.data_path = os.path.join(self.base_log_path, self.signature)
        self.position_file = os.path.join(self.data_path, "position", "position.jsonl")

        # Conversation history for reasoning logs
        self.conversation_history: List[Dict[str, Any]] = []

        # P&L calculator
        self.pnl_calculator = DailyPnLCalculator(initial_cash=initial_cash)
        
    def _get_default_mcp_config(self) -> Dict[str, Dict[str, Any]]:
        """Get default MCP configuration"""
        return {
            "math": {
                "transport": "streamable_http",
                "url": f"http://localhost:{os.getenv('MATH_HTTP_PORT', '8000')}/mcp",
            },
            "stock_local": {
                "transport": "streamable_http",
                "url": f"http://localhost:{os.getenv('GETPRICE_HTTP_PORT', '8003')}/mcp",
            },
            "search": {
                "transport": "streamable_http",
                "url": f"http://localhost:{os.getenv('SEARCH_HTTP_PORT', '8001')}/mcp",
            },
            "trade": {
                "transport": "streamable_http",
                "url": f"http://localhost:{os.getenv('TRADE_HTTP_PORT', '8002')}/mcp",
            },
        }
    
    async def initialize(self) -> None:
        """Initialize MCP client and AI model"""
        print(f"🚀 Initializing agent: {self.signature}")
        print(f"🔧 Deployment mode: {get_deployment_mode()}")

        # Log API key warning if in dev mode
        log_api_key_warning()

        # Validate OpenAI configuration (only in PROD mode)
        if not is_dev_mode():
            if not self.openai_api_key:
                raise ValueError("❌ OpenAI API key not set. Please configure OPENAI_API_KEY in environment or config file.")
            if not self.openai_base_url:
                print("⚠️  OpenAI base URL not set, using default")

        try:
            # Context injector will be set later via set_context() method
            self.context_injector = None

            # Create MCP client without interceptors initially
            self.client = MultiServerMCPClient(
                self.mcp_config,
                tool_interceptors=[]
            )

            # Get tools
            raw_tools = await self.client.get_tools()
            if not raw_tools:
                print("⚠️  Warning: No MCP tools loaded. MCP services may not be running.")
                print(f"   MCP configuration: {self.mcp_config}")
                self.tools = []
            else:
                print(f"✅ Loaded {len(raw_tools)} MCP tools")
                self.tools = raw_tools
        except Exception as e:
            raise RuntimeError(
                f"❌ Failed to initialize MCP client: {e}\n"
                f"   Please ensure MCP services are running at the configured ports.\n"
                f"   Run: python agent_tools/start_mcp_services.py"
            )

        try:
            # Create AI model (mock in DEV mode, real in PROD mode)
            if is_dev_mode():
                from agent.mock_provider import MockChatModel
                self.model = MockChatModel(date="2025-01-01")  # Date will be updated per session
                print(f"🤖 Using MockChatModel (DEV mode)")
            else:
                self.model = ChatOpenAI(
                    model=self.basemodel,
                    base_url=self.openai_base_url,
                    api_key=self.openai_api_key,
                    max_retries=3,
                    timeout=30
                )
                print(f"🤖 Using {self.basemodel} (PROD mode)")
        except Exception as e:
            raise RuntimeError(f"❌ Failed to initialize AI model: {e}")

        # Note: agent will be created in run_trading_session() based on specific date
        # because system_prompt needs the current date and price information

        print(f"✅ Agent {self.signature} initialization completed")

    async def set_context(self, context_injector: "ContextInjector") -> None:
        """
        Inject ContextInjector after initialization.

        This allows the ContextInjector to be created with the correct
        trading day date and session_id after the agent is initialized.

        Args:
            context_injector: Configured ContextInjector instance with
                            correct signature, today_date, job_id, session_id
        """
        print(f"[DEBUG] set_context() ENTRY: Received context_injector with signature={context_injector.signature}, date={context_injector.today_date}, job_id={context_injector.job_id}, session_id={context_injector.session_id}")

        self.context_injector = context_injector
        print(f"[DEBUG] set_context(): Set self.context_injector, id={id(self.context_injector)}")

        # Recreate MCP client with the interceptor
        # Note: We need to recreate because MultiServerMCPClient doesn't have add_interceptor()
        print(f"[DEBUG] set_context(): Creating new MCP client with interceptor, id={id(context_injector)}")
        self.client = MultiServerMCPClient(
            self.mcp_config,
            tool_interceptors=[context_injector]
        )
        print(f"[DEBUG] set_context(): MCP client created")

        # CRITICAL: Reload tools from new client so they use the interceptor
        print(f"[DEBUG] set_context(): Reloading tools...")
        self.tools = await self.client.get_tools()
        print(f"[DEBUG] set_context(): Tools reloaded, count={len(self.tools)}")

        print(f"✅ Context injected: signature={context_injector.signature}, "
              f"date={context_injector.today_date}, job_id={context_injector.job_id}, "
              f"session_id={context_injector.session_id}")

    def _get_current_prices(self, today_date: str) -> Dict[str, float]:
        """
        Get current market prices for all symbols on given date.

        Args:
            today_date: Trading date in YYYY-MM-DD format

        Returns:
            Dict mapping symbol to current price (buy price)
        """
        from tools.price_tools import get_open_prices

        # Get buy prices for today (these are the current market prices)
        price_dict = get_open_prices(today_date, self.stock_symbols)

        # Convert from {AAPL_price: 150.0} to {AAPL: 150.0}
        current_prices = {}
        for key, value in price_dict.items():
            if value is not None and key.endswith("_price"):
                symbol = key.replace("_price", "")
                current_prices[symbol] = value

        return current_prices

    def _get_current_portfolio_state(self, today_date: str, job_id: str) -> tuple[Dict[str, int], float]:
        """
        Get current portfolio state from database.

        Args:
            today_date: Current trading date
            job_id: Job ID for this trading session

        Returns:
            Tuple of (holdings dict, cash balance)
        """
        from agent_tools.tool_trade import get_current_position_from_db

        try:
            # Get position from database
            position_dict, _ = get_current_position_from_db(job_id, self.signature, today_date)

            # Extract holdings (exclude CASH)
            holdings = {
                symbol: int(qty)
                for symbol, qty in position_dict.items()
                if symbol != "CASH" and qty > 0
            }

            # Extract cash
            cash = float(position_dict.get("CASH", self.initial_cash))

            return holdings, cash

        except Exception as e:
            # If no position found (first trading day), return initial state
            print(f"⚠️ Could not get position from database: {e}")
            return {}, self.initial_cash

    def _calculate_portfolio_value(
        self,
        holdings: Dict[str, int],
        prices: Dict[str, float],
        cash: float
    ) -> float:
        """
        Calculate total portfolio value.

        Args:
            holdings: Dict mapping symbol to quantity
            prices: Dict mapping symbol to price
            cash: Cash balance

        Returns:
            Total portfolio value
        """
        total_value = cash

        for symbol, quantity in holdings.items():
            if symbol in prices:
                total_value += quantity * prices[symbol]
            else:
                print(f"⚠️  Warning: No price data for {symbol}, excluding from value calculation")

        return total_value

    def _capture_message(self, role: str, content: str, tool_name: str = None, tool_input: str = None) -> None:
        """
        Capture a message in conversation history.

        Args:
            role: Message role ('user', 'assistant', 'tool')
            content: Message content
            tool_name: Tool name for tool messages
            tool_input: Tool input for tool messages
        """
        from datetime import datetime, timezone

        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        }

        if tool_name:
            message["tool_name"] = tool_name
        if tool_input:
            message["tool_input"] = tool_input

        self.conversation_history.append(message)

    def get_conversation_history(self) -> List[Dict[str, Any]]:
        """
        Get the complete conversation history for this trading session.

        Returns:
            List of message dictionaries with role, content, timestamp
        """
        return self.conversation_history.copy()

    def clear_conversation_history(self) -> None:
        """Clear conversation history (called at start of each trading day)."""
        self.conversation_history = []

    async def generate_summary(self, content: str, max_length: int = 200) -> str:
        """
        Generate a concise summary of reasoning content.

        Uses the same AI model to summarize its own reasoning.

        Args:
            content: Full reasoning content to summarize
            max_length: Approximate character limit for summary

        Returns:
            1-2 sentence summary of key decisions and reasoning
        """
        # Truncate content to avoid token limits (keep first 2000 chars)
        truncated = content[:2000] if len(content) > 2000 else content

        prompt = f"""Summarize the following trading decision in 1-2 sentences (max {max_length} characters), focusing on the key reasoning and actions taken:

{truncated}

Summary:"""

        try:
            # Use ainvoke for async call
            response = await self.model.ainvoke(prompt)

            # Extract content from response
            if hasattr(response, 'content'):
                summary = response.content.strip()
            elif isinstance(response, dict) and 'content' in response:
                summary = response['content'].strip()
            else:
                summary = str(response).strip()

            # Truncate if too long
            if len(summary) > max_length:
                summary = summary[:max_length-3] + "..."

            return summary

        except Exception as e:
            # If summary generation fails, return truncated original
            return truncated[:max_length-3] + "..."

    def generate_summary_sync(self, content: str, max_length: int = 200) -> str:
        """
        Synchronous wrapper for generate_summary.

        Args:
            content: Full reasoning content to summarize
            max_length: Approximate character limit for summary

        Returns:
            Summary string
        """
        import asyncio

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        return loop.run_until_complete(self.generate_summary(content, max_length))

    async def _ainvoke_with_retry(self, message: List[Dict[str, str]]) -> Any:
        """Agent invocation with retry"""
        for attempt in range(1, self.max_retries + 1):
            try:
                return await self.agent.ainvoke(
                    {"messages": message}, 
                    {"recursion_limit": 100}
                )
            except Exception as e:
                if attempt == self.max_retries:
                    raise e
                print(f"⚠️ Attempt {attempt} failed, retrying after {self.base_delay * attempt} seconds...")
                print(f"Error details: {e}")
                await asyncio.sleep(self.base_delay * attempt)
    
    async def run_trading_session(self, today_date: str) -> None:
        """
        Run single day trading session with P&L calculation and database integration.

        Args:
            today_date: Trading date in YYYY-MM-DD format
        """
        from api.database import Database

        print(f"📈 Starting trading session: {today_date}")
        session_start = time.time()

        # Update context injector with current trading date
        if self.context_injector:
            self.context_injector.today_date = today_date

        # Clear conversation history for new trading day
        self.clear_conversation_history()

        # Update mock model date if in dev mode
        if is_dev_mode():
            self.model.date = today_date

        # Get job_id from context injector
        job_id = self.context_injector.job_id if self.context_injector else get_config_value("JOB_ID")
        if not job_id:
            raise ValueError("job_id not available - ensure context_injector is set or JOB_ID is in config")

        # Initialize database
        db = Database()

        # 1. Get previous trading day data
        previous_day = db.get_previous_trading_day(
            job_id=job_id,
            model=self.signature,
            current_date=today_date
        )

        # Add holdings to previous_day dict if exists
        if previous_day:
            previous_day_id = previous_day["id"]
            previous_day["holdings"] = db.get_ending_holdings(previous_day_id)

        # 2. Load today's buy prices (current market prices for P&L calculation)
        current_prices = self._get_current_prices(today_date)

        # 3. Calculate daily P&L
        pnl_metrics = self.pnl_calculator.calculate(
            previous_day=previous_day,
            current_date=today_date,
            current_prices=current_prices
        )

        # 4. Determine starting cash (from previous day or initial cash)
        starting_cash = previous_day["ending_cash"] if previous_day else self.initial_cash

        # 5. Create trading_day record (will be updated after session)
        trading_day_id = db.create_trading_day(
            job_id=job_id,
            model=self.signature,
            date=today_date,
            starting_cash=starting_cash,
            starting_portfolio_value=pnl_metrics["starting_portfolio_value"],
            daily_profit=pnl_metrics["daily_profit"],
            daily_return_pct=pnl_metrics["daily_return_pct"],
            ending_cash=starting_cash,  # Will update after trading
            ending_portfolio_value=pnl_metrics["starting_portfolio_value"],  # Will update
            days_since_last_trading=pnl_metrics["days_since_last_trading"]
        )

        # Write trading_day_id to runtime config for trade tools
        from tools.general_tools import write_config_value
        write_config_value('TRADING_DAY_ID', trading_day_id)

        # 6. Run AI trading session
        action_count = 0

        # Get system prompt
        system_prompt = get_agent_system_prompt(today_date, self.signature)

        # Update agent with system prompt
        self.agent = create_agent(
            self.model,
            tools=self.tools,
            system_prompt=system_prompt,
        )

        # Capture user prompt
        user_prompt = f"Please analyze and update today's ({today_date}) positions."
        self._capture_message("user", user_prompt)

        # Initial user query
        user_query = [{"role": "user", "content": user_prompt}]
        message = user_query.copy()

        # Trading loop
        current_step = 0
        while current_step < self.max_steps:
            current_step += 1
            print(f"🔄 Step {current_step}/{self.max_steps}")

            try:
                # Call agent
                response = await self._ainvoke_with_retry(message)

                # Extract agent response
                agent_response = extract_conversation(response, "final")

                # Capture assistant response
                self._capture_message("assistant", agent_response)

                # Check stop signal
                if STOP_SIGNAL in agent_response:
                    print("✅ Received stop signal, trading session ended")
                    print(agent_response)
                    break

                # Extract tool messages and count trade actions
                tool_msgs = extract_tool_messages(response)
                for tool_msg in tool_msgs:
                    tool_name = getattr(tool_msg, 'name', None) or tool_msg.get('name') if isinstance(tool_msg, dict) else None
                    if tool_name in ['buy', 'sell']:
                        action_count += 1

                tool_response = '\n'.join([msg.content for msg in tool_msgs])

                # Prepare new messages
                new_messages = [
                    {"role": "assistant", "content": agent_response},
                    {"role": "user", "content": f'Tool results: {tool_response}'}
                ]

                # Add new messages
                message.extend(new_messages)

            except Exception as e:
                print(f"❌ Trading session error: {str(e)}")
                print(f"Error details: {e}")
                raise

        session_duration = time.time() - session_start

        # 7. Generate reasoning summary
        summarizer = ReasoningSummarizer(model=self.model)
        summary = await summarizer.generate_summary(self.conversation_history)

        # 8. Get current portfolio state from database
        current_holdings, current_cash = self._get_current_portfolio_state(today_date, job_id)

        # 9. Save final holdings to database
        for symbol, quantity in current_holdings.items():
            if quantity > 0:
                db.create_holding(
                    trading_day_id=trading_day_id,
                    symbol=symbol,
                    quantity=quantity
                )

        # 10. Calculate final portfolio value
        final_value = self._calculate_portfolio_value(current_holdings, current_prices, current_cash)

        # 11. Update trading_day with completion data
        db.connection.execute(
            """
            UPDATE trading_days
            SET
                ending_cash = ?,
                ending_portfolio_value = ?,
                reasoning_summary = ?,
                reasoning_full = ?,
                total_actions = ?,
                session_duration_seconds = ?,
                completed_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                current_cash,
                final_value,
                summary,
                json.dumps(self.conversation_history),
                action_count,
                session_duration,
                trading_day_id
            )
        )
        db.connection.commit()

        print(f"✅ Trading session completed in {session_duration:.2f}s")
        print(f"💰 Final portfolio value: ${final_value:.2f}")
        print(f"📊 Daily P&L: ${pnl_metrics['daily_profit']:.2f} ({pnl_metrics['daily_return_pct']:.2f}%)")

        # Handle trading results (maintains backward compatibility with JSONL)
        await self._handle_trading_result(today_date)
    
    async def _handle_trading_result(self, today_date: str) -> None:
        """Handle trading results with database writes."""
        if_trade = get_config_value("IF_TRADE")

        if if_trade:
            write_config_value("IF_TRADE", False)
            print("✅ Trading completed")
        else:
            print("📊 No trading, maintaining positions")
            write_config_value("IF_TRADE", False)

        # Note: In new schema, trading_day record is created at session start
        # and updated at session end, so no separate no-trade record needed
    
    def register_agent(self) -> None:
        """Register new agent, create initial positions"""
        # Check if position.jsonl file already exists
        if os.path.exists(self.position_file):
            print(f"⚠️ Position file {self.position_file} already exists, skipping registration")
            return
        
        # Ensure directory structure exists
        position_dir = os.path.join(self.data_path, "position")
        if not os.path.exists(position_dir):
            os.makedirs(position_dir)
            print(f"📁 Created position directory: {position_dir}")
        
        # Create initial positions
        init_position = {symbol: 0 for symbol in self.stock_symbols}
        init_position['CASH'] = self.initial_cash
        
        with open(self.position_file, "w") as f:  # Use "w" mode to ensure creating new file
            f.write(json.dumps({
                "date": self.init_date, 
                "id": 0, 
                "positions": init_position
            }) + "\n")
        
        print(f"✅ Agent {self.signature} registration completed")
        print(f"📁 Position file: {self.position_file}")
        print(f"💰 Initial cash: ${self.initial_cash}")
        print(f"📊 Number of stocks: {len(self.stock_symbols)}")
    
    def get_trading_dates(self, init_date: str, end_date: str) -> List[str]:
        """
        Get trading date list
        
        Args:
            init_date: Start date
            end_date: End date
            
        Returns:
            List of trading dates
        """
        dates = []
        max_date = None
        
        if not os.path.exists(self.position_file):
            self.register_agent()
            max_date = init_date
        else:
            # Read existing position file, find latest date
            with open(self.position_file, "r") as f:
                for line in f:
                    doc = json.loads(line)
                    current_date = doc['date']
                    if max_date is None:
                        max_date = current_date
                    else:
                        current_date_obj = datetime.strptime(current_date, "%Y-%m-%d")
                        max_date_obj = datetime.strptime(max_date, "%Y-%m-%d")
                        if current_date_obj > max_date_obj:
                            max_date = current_date
        
        # Check if new dates need to be processed
        max_date_obj = datetime.strptime(max_date, "%Y-%m-%d")
        end_date_obj = datetime.strptime(end_date, "%Y-%m-%d")
        
        if end_date_obj <= max_date_obj:
            return []
        
        # Generate trading date list
        trading_dates = []
        current_date = max_date_obj + timedelta(days=1)
        
        while current_date <= end_date_obj:
            if current_date.weekday() < 5:  # Weekdays
                trading_dates.append(current_date.strftime("%Y-%m-%d"))
            current_date += timedelta(days=1)
        
        return trading_dates
    
    async def run_with_retry(self, today_date: str) -> None:
        """Run method with retry"""
        for attempt in range(1, self.max_retries + 1):
            try:
                print(f"🔄 Attempting to run {self.signature} - {today_date} (Attempt {attempt})")
                await self.run_trading_session(today_date)
                print(f"✅ {self.signature} - {today_date} run successful")
                return
            except Exception as e:
                print(f"❌ Attempt {attempt} failed: {str(e)}")
                if attempt == self.max_retries:
                    print(f"💥 {self.signature} - {today_date} all retries failed")
                    raise
                else:
                    wait_time = self.base_delay * attempt
                    print(f"⏳ Waiting {wait_time} seconds before retry...")
                    await asyncio.sleep(wait_time)
    
    async def run_date_range(self, init_date: str, end_date: str) -> None:
        """
        Run all trading days in date range
        
        Args:
            init_date: Start date
            end_date: End date
        """
        print(f"📅 Running date range: {init_date} to {end_date}")
        
        # Get trading date list
        trading_dates = self.get_trading_dates(init_date, end_date)
        
        if not trading_dates:
            print(f"ℹ️ No trading days to process")
            return
        
        print(f"📊 Trading days to process: {trading_dates}")
        
        # Process each trading day
        for date in trading_dates:
            print(f"🔄 Processing {self.signature} - Date: {date}")
            
            # Set configuration
            write_config_value("TODAY_DATE", date)
            write_config_value("SIGNATURE", self.signature)
            
            try:
                await self.run_with_retry(date)
            except Exception as e:
                print(f"❌ Error processing {self.signature} - Date: {date}")
                print(e)
                raise
        
        print(f"✅ {self.signature} processing completed")
    
    def get_position_summary(self) -> Dict[str, Any]:
        """Get position summary"""
        if not os.path.exists(self.position_file):
            return {"error": "Position file does not exist"}
        
        positions = []
        with open(self.position_file, "r") as f:
            for line in f:
                positions.append(json.loads(line))
        
        if not positions:
            return {"error": "No position records"}
        
        latest_position = positions[-1]
        return {
            "signature": self.signature,
            "latest_date": latest_position.get("date"),
            "positions": latest_position.get("positions", {}),
            "total_records": len(positions)
        }
    
    def __str__(self) -> str:
        return f"BaseAgent(signature='{self.signature}', basemodel='{self.basemodel}', stocks={len(self.stock_symbols)})"
    
    def __repr__(self) -> str:
        return self.__str__()
