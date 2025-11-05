"""Test trade tools write to new schema (actions table)."""

import pytest
import sqlite3
from agent_tools.tool_trade import _buy_impl, _sell_impl
from api.database import Database
from tools.deployment_config import get_db_path


@pytest.fixture
def test_db():
    """Create test database with new schema."""
    db_path = ":memory:"
    db = Database(db_path)

    # Create jobs table (prerequisite)
    db.connection.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            job_id TEXT PRIMARY KEY,
            config_path TEXT NOT NULL,
            status TEXT NOT NULL,
            date_range TEXT NOT NULL,
            models TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    db.connection.execute("""
        INSERT INTO jobs (job_id, config_path, status, date_range, models, created_at)
        VALUES ('test-job-123', 'test_config.json', 'running', '2025-01-15', '["test-model"]', '2025-01-15T10:00:00Z')
    """)

    # Create trading_days record
    trading_day_id = db.create_trading_day(
        job_id='test-job-123',
        model='test-model',
        date='2025-01-15',
        starting_cash=10000.0,
        starting_portfolio_value=10000.0,
        daily_profit=0.0,
        daily_return_pct=0.0,
        ending_cash=10000.0,
        ending_portfolio_value=10000.0,
        days_since_last_trading=0
    )

    db.connection.commit()

    yield db, trading_day_id

    db.connection.close()


def test_buy_writes_to_actions_table(test_db, monkeypatch):
    """Test buy() writes action record to actions table."""
    db, trading_day_id = test_db

    # Create a mock connection wrapper that doesn't actually close
    class MockConnection:
        def __init__(self, real_conn):
            self.real_conn = real_conn

        def cursor(self):
            return self.real_conn.cursor()

        def execute(self, *args, **kwargs):
            return self.real_conn.execute(*args, **kwargs)

        def commit(self):
            return self.real_conn.commit()

        def rollback(self):
            return self.real_conn.rollback()

        def close(self):
            pass  # Don't actually close the connection

    mock_conn = MockConnection(db.connection)

    # Mock get_db_connection to return our mock connection
    monkeypatch.setattr('agent_tools.tool_trade.get_db_connection',
                       lambda x: mock_conn)

    # Mock get_current_position_from_db to return starting position
    monkeypatch.setattr('agent_tools.tool_trade.get_current_position_from_db',
                       lambda job_id, sig, date: ({'CASH': 10000.0}, 0))

    # Mock runtime config
    monkeypatch.setenv('RUNTIME_ENV_PATH', '/tmp/test_runtime.json')

    # Create mock runtime config file
    import json
    with open('/tmp/test_runtime.json', 'w') as f:
        json.dump({
            'TODAY_DATE': '2025-01-15',
            'SIGNATURE': 'test-model',
            'JOB_ID': 'test-job-123',
            'TRADING_DAY_ID': trading_day_id
        }, f)

    # Mock price data
    monkeypatch.setattr('agent_tools.tool_trade.get_open_prices',
                       lambda date, symbols: {'AAPL_price': 150.0})

    # Execute buy
    result = _buy_impl(
        symbol='AAPL',
        amount=10,
        signature='test-model',
        today_date='2025-01-15',
        job_id='test-job-123',
        trading_day_id=trading_day_id
    )

    # Check if there was an error
    if 'error' in result:
        print(f"Buy failed with error: {result}")

    # Verify action record created
    cursor = db.connection.execute("""
        SELECT action_type, symbol, quantity, price, trading_day_id
        FROM actions
        WHERE trading_day_id = ?
    """, (trading_day_id,))

    row = cursor.fetchone()
    assert row is not None, "Action record should exist"
    assert row[0] == 'buy'
    assert row[1] == 'AAPL'
    assert row[2] == 10
    assert row[3] == 150.0
    assert row[4] == trading_day_id

    # Verify NO write to old positions table
    cursor = db.connection.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='positions'
    """)
    assert cursor.fetchone() is None, "Old positions table should not exist"


def test_buy_with_none_trading_day_id_reads_from_config(test_db, monkeypatch):
    """Test buy() with trading_day_id=None fallback reads from runtime config."""
    db, trading_day_id = test_db

    # Create a mock connection wrapper that doesn't actually close
    class MockConnection:
        def __init__(self, real_conn):
            self.real_conn = real_conn

        def cursor(self):
            return self.real_conn.cursor()

        def execute(self, *args, **kwargs):
            return self.real_conn.execute(*args, **kwargs)

        def commit(self):
            return self.real_conn.commit()

        def rollback(self):
            return self.real_conn.rollback()

        def close(self):
            pass  # Don't actually close the connection

    mock_conn = MockConnection(db.connection)

    # Mock get_db_connection to return our mock connection
    monkeypatch.setattr('agent_tools.tool_trade.get_db_connection',
                       lambda x: mock_conn)

    # Mock get_current_position_from_db to return starting position
    monkeypatch.setattr('agent_tools.tool_trade.get_current_position_from_db',
                       lambda job_id, sig, date: ({'CASH': 10000.0}, 0))

    # Mock runtime config
    monkeypatch.setenv('RUNTIME_ENV_PATH', '/tmp/test_runtime_fallback.json')

    # Create mock runtime config file with TRADING_DAY_ID
    import json
    with open('/tmp/test_runtime_fallback.json', 'w') as f:
        json.dump({
            'TODAY_DATE': '2025-01-15',
            'SIGNATURE': 'test-model',
            'JOB_ID': 'test-job-123',
            'TRADING_DAY_ID': trading_day_id
        }, f)

    # Mock price data
    monkeypatch.setattr('agent_tools.tool_trade.get_open_prices',
                       lambda date, symbols: {'AAPL_price': 150.0})

    # Execute buy with trading_day_id=None to force config lookup
    result = _buy_impl(
        symbol='AAPL',
        amount=10,
        signature='test-model',
        today_date='2025-01-15',
        job_id='test-job-123',
        trading_day_id=None  # Force fallback to runtime config
    )

    # Check if there was an error
    if 'error' in result:
        print(f"Buy failed with error: {result}")

    # Verify action record created with correct trading_day_id from config
    cursor = db.connection.execute("""
        SELECT action_type, symbol, quantity, price, trading_day_id
        FROM actions
        WHERE trading_day_id = ?
    """, (trading_day_id,))

    row = cursor.fetchone()
    assert row is not None, "Action record should exist when reading trading_day_id from config"
    assert row[0] == 'buy'
    assert row[1] == 'AAPL'
    assert row[2] == 10
    assert row[3] == 150.0
    assert row[4] == trading_day_id, "trading_day_id should match the value from runtime config"


def test_sell_writes_to_actions_table(test_db, monkeypatch):
    """Test sell() writes action record to actions table."""
    db, trading_day_id = test_db

    # Setup: Create starting holdings
    db.create_holding(trading_day_id, 'AAPL', 10)
    db.connection.commit()

    # Create a mock connection wrapper that doesn't actually close
    class MockConnection:
        def __init__(self, real_conn):
            self.real_conn = real_conn

        def cursor(self):
            return self.real_conn.cursor()

        def execute(self, *args, **kwargs):
            return self.real_conn.execute(*args, **kwargs)

        def commit(self):
            return self.real_conn.commit()

        def rollback(self):
            return self.real_conn.rollback()

        def close(self):
            pass  # Don't actually close the connection

    mock_conn = MockConnection(db.connection)

    # Mock dependencies
    monkeypatch.setattr('agent_tools.tool_trade.get_db_connection',
                       lambda x: mock_conn)

    # Mock get_current_position_from_db to return position with AAPL shares
    monkeypatch.setattr('agent_tools.tool_trade.get_current_position_from_db',
                       lambda job_id, sig, date: ({'CASH': 10000.0, 'AAPL': 10}, 0))

    monkeypatch.setenv('RUNTIME_ENV_PATH', '/tmp/test_runtime.json')

    import json
    with open('/tmp/test_runtime.json', 'w') as f:
        json.dump({
            'TODAY_DATE': '2025-01-15',
            'SIGNATURE': 'test-model',
            'JOB_ID': 'test-job-123',
            'TRADING_DAY_ID': trading_day_id
        }, f)

    monkeypatch.setattr('agent_tools.tool_trade.get_open_prices',
                       lambda date, symbols: {'AAPL_price': 160.0})

    # Execute sell
    result = _sell_impl(
        symbol='AAPL',
        amount=5,
        signature='test-model',
        today_date='2025-01-15',
        job_id='test-job-123',
        trading_day_id=trading_day_id
    )

    # Verify action record created
    cursor = db.connection.execute("""
        SELECT action_type, symbol, quantity, price
        FROM actions
        WHERE trading_day_id = ? AND action_type = 'sell'
    """, (trading_day_id,))

    row = cursor.fetchone()
    assert row is not None
    assert row[0] == 'sell'
    assert row[1] == 'AAPL'
    assert row[2] == 5
    assert row[3] == 160.0


def test_intraday_position_tracking_sell_then_buy(test_db, monkeypatch):
    """Test that sell proceeds are immediately available for subsequent buys."""
    db, trading_day_id = test_db

    # Setup: Create starting position with AAPL shares and limited cash
    db.create_holding(trading_day_id, 'AAPL', 10)
    db.connection.commit()

    # Create a mock connection wrapper
    class MockConnection:
        def __init__(self, real_conn):
            self.real_conn = real_conn

        def cursor(self):
            return self.real_conn.cursor()

        def commit(self):
            return self.real_conn.commit()

        def rollback(self):
            return self.real_conn.rollback()

        def close(self):
            pass

    mock_conn = MockConnection(db.connection)
    monkeypatch.setattr('agent_tools.tool_trade.get_db_connection',
                       lambda x: mock_conn)

    # Mock get_current_position_from_db to return starting position
    monkeypatch.setattr('agent_tools.tool_trade.get_current_position_from_db',
                       lambda job_id, sig, date: ({'CASH': 500.0, 'AAPL': 10}, 0))

    monkeypatch.setenv('RUNTIME_ENV_PATH', '/tmp/test_runtime_intraday.json')

    import json
    with open('/tmp/test_runtime_intraday.json', 'w') as f:
        json.dump({
            'TODAY_DATE': '2025-01-15',
            'SIGNATURE': 'test-model',
            'JOB_ID': 'test-job-123',
            'TRADING_DAY_ID': trading_day_id
        }, f)

    # Mock prices: AAPL sells for 200, MSFT costs 150
    def mock_get_prices(date, symbols):
        if 'AAPL' in symbols:
            return {'AAPL_price': 200.0}
        elif 'MSFT' in symbols:
            return {'MSFT_price': 150.0}
        return {}

    monkeypatch.setattr('agent_tools.tool_trade.get_open_prices', mock_get_prices)

    # Step 1: Sell 3 shares of AAPL for 600.0
    # Starting cash: 500.0, proceeds: 600.0, new cash: 1100.0
    result_sell = _sell_impl(
        symbol='AAPL',
        amount=3,
        signature='test-model',
        today_date='2025-01-15',
        job_id='test-job-123',
        trading_day_id=trading_day_id,
        _current_position=None  # Use database position (starting position)
    )

    assert 'error' not in result_sell, f"Sell should succeed: {result_sell}"
    assert result_sell['CASH'] == 1100.0, "Cash should be 500 + (3 * 200) = 1100"
    assert result_sell['AAPL'] == 7, "AAPL shares should be 10 - 3 = 7"

    # Step 2: Buy 7 shares of MSFT for 1050.0 using the position from the sell
    # This should work because we pass the updated position from step 1
    result_buy = _buy_impl(
        symbol='MSFT',
        amount=7,
        signature='test-model',
        today_date='2025-01-15',
        job_id='test-job-123',
        trading_day_id=trading_day_id,
        _current_position=result_sell  # Use position from sell
    )

    assert 'error' not in result_buy, f"Buy should succeed with sell proceeds: {result_buy}"
    assert result_buy['CASH'] == 50.0, "Cash should be 1100 - (7 * 150) = 50"
    assert result_buy['MSFT'] == 7, "MSFT shares should be 7"
    assert result_buy['AAPL'] == 7, "AAPL shares should still be 7"

    # Verify both actions were recorded
    cursor = db.connection.execute("""
        SELECT action_type, symbol, quantity, price
        FROM actions
        WHERE trading_day_id = ?
        ORDER BY created_at
    """, (trading_day_id,))

    actions = cursor.fetchall()
    assert len(actions) == 2, "Should have 2 actions (sell + buy)"
    assert actions[0][0] == 'sell' and actions[0][1] == 'AAPL'
    assert actions[1][0] == 'buy' and actions[1][1] == 'MSFT'


def test_intraday_tracking_without_position_injection_fails(test_db, monkeypatch):
    """Test that without position injection, sell proceeds are NOT available for subsequent buys."""
    db, trading_day_id = test_db

    # Setup: Create starting position with AAPL shares and limited cash
    db.create_holding(trading_day_id, 'AAPL', 10)
    db.connection.commit()

    # Create a mock connection wrapper
    class MockConnection:
        def __init__(self, real_conn):
            self.real_conn = real_conn

        def cursor(self):
            return self.real_conn.cursor()

        def commit(self):
            return self.real_conn.commit()

        def rollback(self):
            return self.real_conn.rollback()

        def close(self):
            pass

    mock_conn = MockConnection(db.connection)
    monkeypatch.setattr('agent_tools.tool_trade.get_db_connection',
                       lambda x: mock_conn)

    # Mock get_current_position_from_db to ALWAYS return starting position
    # (simulating the old buggy behavior)
    monkeypatch.setattr('agent_tools.tool_trade.get_current_position_from_db',
                       lambda job_id, sig, date: ({'CASH': 500.0, 'AAPL': 10}, 0))

    monkeypatch.setenv('RUNTIME_ENV_PATH', '/tmp/test_runtime_no_injection.json')

    import json
    with open('/tmp/test_runtime_no_injection.json', 'w') as f:
        json.dump({
            'TODAY_DATE': '2025-01-15',
            'SIGNATURE': 'test-model',
            'JOB_ID': 'test-job-123',
            'TRADING_DAY_ID': trading_day_id
        }, f)

    # Mock prices
    def mock_get_prices(date, symbols):
        if 'AAPL' in symbols:
            return {'AAPL_price': 200.0}
        elif 'MSFT' in symbols:
            return {'MSFT_price': 150.0}
        return {}

    monkeypatch.setattr('agent_tools.tool_trade.get_open_prices', mock_get_prices)

    # Step 1: Sell 3 shares of AAPL
    result_sell = _sell_impl(
        symbol='AAPL',
        amount=3,
        signature='test-model',
        today_date='2025-01-15',
        job_id='test-job-123',
        trading_day_id=trading_day_id,
        _current_position=None  # Don't inject position (old behavior)
    )

    assert 'error' not in result_sell, "Sell should succeed"

    # Step 2: Try to buy 7 shares of MSFT WITHOUT passing updated position
    # This should FAIL because it will query the database and get the original 500.0 cash
    result_buy = _buy_impl(
        symbol='MSFT',
        amount=7,
        signature='test-model',
        today_date='2025-01-15',
        job_id='test-job-123',
        trading_day_id=trading_day_id,
        _current_position=None  # Don't inject position (old behavior)
    )

    # This should fail with insufficient cash
    assert 'error' in result_buy, "Buy should fail without position injection"
    assert result_buy['error'] == 'Insufficient cash', f"Expected insufficient cash error, got: {result_buy}"
    assert result_buy['cash_available'] == 500.0, "Should see original cash, not updated cash"
