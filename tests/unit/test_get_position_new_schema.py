"""Test get_current_position_from_db queries new schema."""

import pytest
from agent_tools.tool_trade import get_current_position_from_db
from api.database import Database


def test_get_position_from_new_schema():
    """Test position retrieval from trading_days + holdings (previous day)."""

    # Create test database
    db = Database(":memory:")

    # Create prerequisite: jobs record
    db.connection.execute("""
        INSERT INTO jobs (job_id, config_path, status, date_range, models, created_at)
        VALUES ('test-job-123', 'test_config.json', 'running', '2025-01-14 to 2025-01-16', 'test-model', '2025-01-14T10:00:00Z')
    """)
    db.connection.commit()

    # Create trading_day with holdings for 2025-01-15
    trading_day_id = db.create_trading_day(
        job_id='test-job-123',
        model='test-model',
        date='2025-01-15',
        starting_cash=10000.0,
        starting_portfolio_value=10000.0,
        daily_profit=0.0,
        daily_return_pct=0.0,
        ending_cash=8000.0,
        ending_portfolio_value=9500.0,
        days_since_last_trading=0
    )

    # Add ending holdings for 2025-01-15
    db.create_holding(trading_day_id, 'AAPL', 10)
    db.create_holding(trading_day_id, 'MSFT', 5)

    db.connection.commit()

    # Mock get_db_connection to return our test db
    import agent_tools.tool_trade as trade_module
    original_get_db_connection = trade_module.get_db_connection

    def mock_get_db_connection(path):
        return db.connection

    trade_module.get_db_connection = mock_get_db_connection

    try:
        # Query position for NEXT day (2025-01-16)
        # Should retrieve previous day's (2025-01-15) ending position
        position, action_id = get_current_position_from_db(
            job_id='test-job-123',
            model='test-model',
            date='2025-01-16'  # Query for day AFTER the trading_day record
        )

        # Verify we got the previous day's ending position
        assert position['AAPL'] == 10, f"Expected 10 AAPL but got {position.get('AAPL', 0)}"
        assert position['MSFT'] == 5, f"Expected 5 MSFT but got {position.get('MSFT', 0)}"
        assert position['CASH'] == 8000.0, f"Expected cash $8000 but got ${position['CASH']}"
        assert action_id == 2, f"Expected 2 holdings but got {action_id}"
    finally:
        # Restore original function
        trade_module.get_db_connection = original_get_db_connection
        db.connection.close()


def test_get_position_first_day():
    """Test position retrieval on first day (no prior data)."""

    db = Database(":memory:")

    # Mock get_db_connection to return our test db
    import agent_tools.tool_trade as trade_module
    original_get_db_connection = trade_module.get_db_connection

    def mock_get_db_connection(path):
        return db.connection

    trade_module.get_db_connection = mock_get_db_connection

    try:
        # Query position (no data exists)
        position, action_id = get_current_position_from_db(
            job_id='test-job-123',
            model='test-model',
            date='2025-01-15'
        )

        # Should return initial position
        assert position['CASH'] == 10000.0  # Default initial cash
        assert action_id == 0
    finally:
        # Restore original function
        trade_module.get_db_connection = original_get_db_connection
        db.connection.close()


def test_get_position_retrieves_previous_day_not_current():
    """Test that get_current_position_from_db queries PREVIOUS day's ending, not current day.

    This is the critical fix: when querying for day 2's starting position,
    it should return day 1's ending position, NOT day 2's (incomplete) position.
    """

    db = Database(":memory:")

    # Create prerequisite: jobs record
    db.connection.execute("""
        INSERT INTO jobs (job_id, config_path, status, date_range, models, created_at)
        VALUES ('test-job-123', 'test_config.json', 'running', '2025-10-01 to 2025-10-03', 'gpt-5', '2025-10-01T10:00:00Z')
    """)
    db.connection.commit()

    # Day 1: Create complete trading day with holdings
    day1_id = db.create_trading_day(
        job_id='test-job-123',
        model='gpt-5',
        date='2025-10-02',
        starting_cash=10000.0,
        starting_portfolio_value=10000.0,
        daily_profit=0.0,
        daily_return_pct=0.0,
        ending_cash=2500.0,  # After buying stocks
        ending_portfolio_value=10000.0,
        days_since_last_trading=1
    )

    # Day 1 ending holdings (7 AMZN, 5 GOOGL, 6 MU, 3 QCOM, 4 MSFT, 1 CRWD, 10 NVDA, 3 AVGO)
    db.create_holding(day1_id, 'AMZN', 7)
    db.create_holding(day1_id, 'GOOGL', 5)
    db.create_holding(day1_id, 'MU', 6)
    db.create_holding(day1_id, 'QCOM', 3)
    db.create_holding(day1_id, 'MSFT', 4)
    db.create_holding(day1_id, 'CRWD', 1)
    db.create_holding(day1_id, 'NVDA', 10)
    db.create_holding(day1_id, 'AVGO', 3)

    # Day 2: Create incomplete trading day (just started, no holdings yet)
    day2_id = db.create_trading_day(
        job_id='test-job-123',
        model='gpt-5',
        date='2025-10-03',
        starting_cash=2500.0,  # From day 1 ending
        starting_portfolio_value=10000.0,
        daily_profit=0.0,
        daily_return_pct=0.0,
        ending_cash=2500.0,  # Not finalized yet
        ending_portfolio_value=10000.0,  # Not finalized yet
        days_since_last_trading=1
    )
    # NOTE: No holdings created for day 2 yet (trading in progress)

    db.connection.commit()

    # Mock get_db_connection to return our test db
    import agent_tools.tool_trade as trade_module
    original_get_db_connection = trade_module.get_db_connection

    def mock_get_db_connection(path):
        return db.connection

    trade_module.get_db_connection = mock_get_db_connection

    try:
        # Query starting position for day 2 (2025-10-03)
        # This should return day 1's ending position, NOT day 2's incomplete position
        position, action_id = get_current_position_from_db(
            job_id='test-job-123',
            model='gpt-5',
            date='2025-10-03'
        )

        # Verify we got day 1's ending position (8 holdings)
        assert position['CASH'] == 2500.0, f"Expected cash $2500 but got ${position['CASH']}"
        assert position['AMZN'] == 7, f"Expected 7 AMZN but got {position.get('AMZN', 0)}"
        assert position['GOOGL'] == 5, f"Expected 5 GOOGL but got {position.get('GOOGL', 0)}"
        assert position['MU'] == 6, f"Expected 6 MU but got {position.get('MU', 0)}"
        assert position['QCOM'] == 3, f"Expected 3 QCOM but got {position.get('QCOM', 0)}"
        assert position['MSFT'] == 4, f"Expected 4 MSFT but got {position.get('MSFT', 0)}"
        assert position['CRWD'] == 1, f"Expected 1 CRWD but got {position.get('CRWD', 0)}"
        assert position['NVDA'] == 10, f"Expected 10 NVDA but got {position.get('NVDA', 0)}"
        assert position['AVGO'] == 3, f"Expected 3 AVGO but got {position.get('AVGO', 0)}"
        assert action_id == 8, f"Expected 8 holdings but got {action_id}"

        # Verify total holdings count (should NOT include day 2's empty holdings)
        assert len(position) == 9, f"Expected 9 items (8 stocks + CASH) but got {len(position)}"

    finally:
        # Restore original function
        trade_module.get_db_connection = original_get_db_connection
        db.connection.close()
