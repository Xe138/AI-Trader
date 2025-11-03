# Database-Only Position Tracking Design

**Date:** 2025-02-11
**Status:** Approved
**Version:** 1.0

## Problem Statement

Two critical issues prevent simulations from running:

1. **ContextInjector receives None values**: The ContextInjector shows `{'signature': None, 'today_date': None, 'job_id': None, 'session_id': None}` when injecting parameters into trade tool calls, causing trade validation to fail.

2. **File-based position tracking still in use**: System prompt builder and no-trade handler attempt to read/write position.jsonl files that no longer exist after SQLite migration.

## Root Cause Analysis

### Issue 1: ContextInjector Initialization Timing

**Problem Chain:**
- `BaseAgent.__init__()` creates `ContextInjector` with `self.init_date`
- `init_date` is the START of simulation date range (e.g., "2025-10-13"), not current trading day ("2025-10-01")
- Runtime config contains correct values (`TODAY_DATE="2025-10-01"`, `SIGNATURE="gpt-5"`, `JOB_ID="dc488e87..."`), but BaseAgent doesn't use them during initialization
- ContextInjector is created before the trading session, so it doesn't know the correct date

**Evidence:**
```
ai-trader-app  | [ContextInjector] Tool: buy, Args after injection: {'symbol': 'MSFT', 'amount': 1, 'signature': None, 'today_date': None, 'job_id': None, 'session_id': None}
```

### Issue 2: Mixed Storage Architecture

**Problem Chain:**
- Trade tools (tool_trade.py) query/write to SQLite database
- System prompt builder calls `get_today_init_position()` which reads position.jsonl files
- No-trade handler calls `add_no_trade_record()` which writes to position.jsonl files
- Files don't exist because we migrated to database-only storage

**Evidence:**
```
FileNotFoundError: [Errno 2] No such file or directory: '/app/data/agent_data/gpt-5/position/position.jsonl'
```

## Design Solution

### Architecture Principles

1. **Database-only position storage**: All position queries and writes go through SQLite
2. **Lazy context injection**: Create ContextInjector after runtime config is written and session is created
3. **Real-time database queries**: System prompt builder queries database directly, no file caching
4. **Clean initialization order**: Config → Database → Agent → Context → Session

### Component Changes

#### 1. ContextInjector Lifecycle Refactor

**BaseAgent Changes:**

Remove ContextInjector creation from `__init__()`:
```python
# OLD (in __init__)
self.context_injector = ContextInjector(
    signature=self.signature,
    today_date=self.init_date,  # WRONG: uses start date
    job_id=job_id
)
self.client = MultiServerMCPClient(
    self.mcp_config,
    tool_interceptors=[self.context_injector]
)

# NEW (in __init__)
self.context_injector = None
self.client = MultiServerMCPClient(
    self.mcp_config,
    tool_interceptors=[]  # Empty initially
)
```

Add new method `set_context()`:
```python
def set_context(self, context_injector: ContextInjector) -> None:
    """Inject ContextInjector after initialization.

    Args:
        context_injector: Configured ContextInjector instance
    """
    self.context_injector = context_injector
    self.client.add_interceptor(context_injector)
```

**ModelDayExecutor Changes:**

Create and inject ContextInjector after agent initialization:
```python
async def execute_async(self) -> Dict[str, Any]:
    # ... create session, initialize position ...

    # Set RUNTIME_ENV_PATH
    os.environ["RUNTIME_ENV_PATH"] = self.runtime_config_path

    # Initialize agent (without context)
    agent = await self._initialize_agent()

    # Create context injector with correct values
    context_injector = ContextInjector(
        signature=self.model_sig,
        today_date=self.date,  # CORRECT: current trading day
        job_id=self.job_id,
        session_id=session_id
    )

    # Inject context into agent
    agent.set_context(context_injector)

    # Run trading session
    session_result = await agent.run_trading_session(self.date)
```

#### 2. Database Position Query Functions

**New Functions (tools/price_tools.py):**

```python
def get_today_init_position_from_db(
    today_date: str,
    modelname: str,
    job_id: str
) -> Dict[str, float]:
    """
    Query yesterday's position from database.

    Args:
        today_date: Current trading date (YYYY-MM-DD)
        modelname: Model signature
        job_id: Job UUID

    Returns:
        Position dict: {"AAPL": 50, "MSFT": 30, "CASH": 5000.0}
        If no position exists: {"CASH": 10000.0} (initial cash)
    """
    from tools.deployment_config import get_db_path
    from api.database import get_db_connection

    db_path = get_db_path()
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    try:
        # Get most recent position before today
        cursor.execute("""
            SELECT p.id, p.cash
            FROM positions p
            WHERE p.job_id = ? AND p.model = ? AND p.date < ?
            ORDER BY p.date DESC, p.action_id DESC
            LIMIT 1
        """, (job_id, modelname, today_date))

        row = cursor.fetchone()

        if not row:
            # First day - return initial cash
            return {"CASH": 10000.0}  # TODO: Read from config

        position_id, cash = row
        position_dict = {"CASH": cash}

        # Get holdings for this position
        cursor.execute("""
            SELECT symbol, quantity
            FROM holdings
            WHERE position_id = ?
        """, (position_id,))

        for symbol, quantity in cursor.fetchall():
            position_dict[symbol] = quantity

        return position_dict

    finally:
        conn.close()


def add_no_trade_record_to_db(
    today_date: str,
    modelname: str,
    job_id: str,
    session_id: int
) -> None:
    """
    Create no-trade position record in database.

    Args:
        today_date: Current trading date (YYYY-MM-DD)
        modelname: Model signature
        job_id: Job UUID
        session_id: Trading session ID
    """
    from tools.deployment_config import get_db_path
    from api.database import get_db_connection
    from agent_tools.tool_trade import get_current_position_from_db
    from datetime import datetime

    db_path = get_db_path()
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    try:
        # Get current position
        current_position, next_action_id = get_current_position_from_db(
            job_id, modelname, today_date
        )

        # Calculate portfolio value
        # (Reuse logic from tool_trade.py)
        cash = current_position.get("CASH", 0.0)
        portfolio_value = cash

        # Add stock values
        for symbol, qty in current_position.items():
            if symbol != "CASH":
                try:
                    from tools.price_tools import get_open_prices
                    price = get_open_prices(today_date, [symbol])[f'{symbol}_price']
                    portfolio_value += qty * price
                except KeyError:
                    pass

        # Get previous value for P&L
        cursor.execute("""
            SELECT portfolio_value
            FROM positions
            WHERE job_id = ? AND model = ? AND date < ?
            ORDER BY date DESC, action_id DESC
            LIMIT 1
        """, (job_id, modelname, today_date))

        row = cursor.fetchone()
        previous_value = row[0] if row else 10000.0

        daily_profit = portfolio_value - previous_value
        daily_return_pct = (daily_profit / previous_value * 100) if previous_value > 0 else 0

        # Insert position record
        created_at = datetime.utcnow().isoformat() + "Z"

        cursor.execute("""
            INSERT INTO positions (
                job_id, date, model, action_id, action_type,
                cash, portfolio_value, daily_profit, daily_return_pct,
                session_id, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job_id, today_date, modelname, next_action_id, "no_trade",
            cash, portfolio_value, daily_profit, daily_return_pct,
            session_id, created_at
        ))

        position_id = cursor.lastrowid

        # Insert holdings (unchanged from previous position)
        for symbol, qty in current_position.items():
            if symbol != "CASH":
                cursor.execute("""
                    INSERT INTO holdings (position_id, symbol, quantity)
                    VALUES (?, ?, ?)
                """, (position_id, symbol, qty))

        conn.commit()

    except Exception as e:
        conn.rollback()
        raise
    finally:
        conn.close()
```

#### 3. System Prompt Builder Updates

**Modified Function (prompts/agent_prompt.py):**

```python
def get_agent_system_prompt(today_date: str, signature: str) -> str:
    """Build system prompt with database position queries."""
    from tools.general_tools import get_config_value

    print(f"signature: {signature}")
    print(f"today_date: {today_date}")

    # Get job_id from runtime config
    job_id = get_config_value("JOB_ID")
    if not job_id:
        raise ValueError("JOB_ID not found in runtime config")

    # Query database for yesterday's position
    today_init_position = get_today_init_position_from_db(
        today_date, signature, job_id
    )

    # Get prices (unchanged)
    yesterday_buy_prices, yesterday_sell_prices = get_yesterday_open_and_close_price(
        today_date, all_nasdaq_100_symbols
    )
    today_buy_price = get_open_prices(today_date, all_nasdaq_100_symbols)
    yesterday_profit = get_yesterday_profit(
        today_date, yesterday_buy_prices, yesterday_sell_prices, today_init_position
    )

    return agent_system_prompt.format(
        date=today_date,
        positions=today_init_position,
        STOP_SIGNAL=STOP_SIGNAL,
        yesterday_close_price=yesterday_sell_prices,
        today_buy_price=today_buy_price,
        yesterday_profit=yesterday_profit
    )
```

#### 4. No-Trade Handler Updates

**Modified Method (agent/base_agent/base_agent.py):**

```python
async def _handle_trading_result(self, today_date: str) -> None:
    """Handle trading results with database writes."""
    from tools.general_tools import get_config_value
    from tools.price_tools import add_no_trade_record_to_db

    if_trade = get_config_value("IF_TRADE")

    if if_trade:
        write_config_value("IF_TRADE", False)
        print("✅ Trading completed")
    else:
        print("📊 No trading, maintaining positions")

        # Get context from runtime config
        job_id = get_config_value("JOB_ID")
        session_id = self.context_injector.session_id if self.context_injector else None

        if not job_id or not session_id:
            raise ValueError("Missing JOB_ID or session_id for no-trade record")

        # Write no-trade record to database
        add_no_trade_record_to_db(
            today_date,
            self.signature,
            job_id,
            session_id
        )

        write_config_value("IF_TRADE", False)
```

### Data Flow Summary

**Complete Execution Sequence:**

1. `ModelDayExecutor.__init__()`:
   - Create runtime config file with TODAY_DATE, SIGNATURE, JOB_ID

2. `ModelDayExecutor.execute_async()`:
   - Create trading_sessions record → get session_id
   - Initialize starting position (if first day)
   - Set RUNTIME_ENV_PATH environment variable
   - Initialize agent (without ContextInjector)
   - Create ContextInjector(date, model_sig, job_id, session_id)
   - Call agent.set_context(context_injector)
   - Run trading session

3. `BaseAgent.run_trading_session()`:
   - Build system prompt → queries database for yesterday's position
   - AI agent analyzes and decides
   - Calls buy/sell tools → ContextInjector injects parameters
   - Trade tools write to database
   - If no trade: add_no_trade_record_to_db()

4. Position Query Flow:
   - System prompt needs yesterday's position
   - `get_today_init_position_from_db(today_date, signature, job_id)`
   - Query: `SELECT positions + holdings WHERE job_id=? AND model=? AND date<? ORDER BY date DESC, action_id DESC LIMIT 1`
   - Reconstruct position dict from results
   - Return to system prompt builder

### Testing Strategy

**Critical Test Cases:**

1. **First Trading Day**
   - No previous position in database
   - Returns `{"CASH": 10000.0}`
   - System prompt shows available cash
   - Initial position created with action_id=0

2. **Subsequent Trading Days**
   - Query finds previous position
   - System prompt shows yesterday's holdings
   - Action_id increments properly

3. **No-Trade Days**
   - Agent outputs `<FINISH_SIGNAL>` without trading
   - `add_no_trade_record_to_db()` creates record
   - Holdings unchanged
   - Portfolio value calculated

4. **ContextInjector Values**
   - All parameters non-None
   - Debug log shows correct injection
   - Trade tools validate successfully

**Edge Cases:**

- Multiple models, same job (different signatures)
- Date gaps (weekends) - query finds Friday on Monday
- Mid-simulation restart - resumes from last position
- Empty holdings (only CASH)

**Validation Points:**

- Log ContextInjector values at injection
- Log database query results
- Verify initial position created
- Check session_id links positions

## Implementation Checklist

### Phase 1: ContextInjector Refactor
- [ ] Remove ContextInjector creation from BaseAgent.__init__()
- [ ] Add BaseAgent.set_context() method
- [ ] Update ModelDayExecutor to create and inject ContextInjector
- [ ] Add debug logging for injected values

### Phase 2: Database Position Functions
- [ ] Implement get_today_init_position_from_db()
- [ ] Implement add_no_trade_record_to_db()
- [ ] Add database error handling
- [ ] Add logging for query results

### Phase 3: Integration
- [ ] Update get_agent_system_prompt() to use database queries
- [ ] Update _handle_trading_result() to use database writes
- [ ] Remove/deprecate old file-based functions
- [ ] Test first trading day scenario
- [ ] Test subsequent trading days
- [ ] Test no-trade scenario

### Phase 4: Validation
- [ ] Run full simulation and verify ContextInjector logs
- [ ] Verify initial cash appears in system prompt
- [ ] Verify trades execute successfully
- [ ] Verify no-trade records created
- [ ] Check database for correct position records

## Rollback Plan

If issues arise:
1. Revert ContextInjector changes (keep in __init__)
2. Temporarily pass correct date via environment variable
3. Keep file-based functions as fallback
4. Debug database queries in isolation

## Success Criteria

1. ContextInjector logs show all non-None values
2. System prompt displays initial $10,000 cash
3. Trade tools successfully execute buy/sell operations
4. No FileNotFoundError exceptions
5. Database contains correct position records
6. AI agent can complete full trading day

## Notes

- File-based functions marked as deprecated but not removed (backward compatibility)
- Database queries use deployment_config for automatic prod/dev resolution
- Initial cash value should eventually be read from config, not hardcoded
- Consider adding database connection pooling for performance
