"""Test get_current_position_from_db queries new schema."""

import pytest
from agent_tools.tool_trade import get_current_position_from_db
from api.database import Database


def test_get_position_from_new_schema():
    """Test position retrieval from trading_days + holdings."""

    # Create test database
    db = Database(":memory:")

    # Create prerequisite: jobs record
    db.connection.execute("""
        INSERT INTO jobs (job_id, config_path, status, date_range, models, created_at)
        VALUES ('test-job-123', 'test_config.json', 'running', '2025-01-15 to 2025-01-15', 'test-model', '2025-01-15T10:00:00Z')
    """)
    db.connection.commit()

    # Create trading_day with holdings
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

    # Add ending holdings
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
        # Query position
        position, action_id = get_current_position_from_db(
            job_id='test-job-123',
            model='test-model',
            date='2025-01-15'
        )

        # Verify
        assert position['AAPL'] == 10
        assert position['MSFT'] == 5
        assert position['CASH'] == 8000.0
        assert action_id == 2  # 2 holdings = 2 actions
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
