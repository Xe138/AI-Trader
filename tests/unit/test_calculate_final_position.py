"""Test _calculate_final_position_from_actions method."""

import pytest
from unittest.mock import patch
from agent.base_agent.base_agent import BaseAgent
from api.database import Database


@pytest.fixture
def test_db():
    """Create test database with schema."""
    db = Database(":memory:")

    # Create jobs record
    db.connection.execute("""
        INSERT INTO jobs (job_id, config_path, status, date_range, models, created_at)
        VALUES ('test-job', 'test.json', 'running', '2025-10-07 to 2025-10-07', 'gpt-5', '2025-10-07T00:00:00Z')
    """)
    db.connection.commit()

    return db


def test_calculate_final_position_first_day_with_trades(test_db):
    """Test calculating final position on first trading day with multiple trades."""

    # Create trading_day for first day
    trading_day_id = test_db.create_trading_day(
        job_id='test-job',
        model='gpt-5',
        date='2025-10-07',
        starting_cash=10000.0,
        starting_portfolio_value=10000.0,
        daily_profit=0.0,
        daily_return_pct=0.0,
        ending_cash=10000.0,  # Not yet calculated
        ending_portfolio_value=10000.0,  # Not yet calculated
        days_since_last_trading=1
    )

    # Add 15 buy actions (matching your real data)
    actions_data = [
        ("MSFT", 3, 528.285, "buy"),
        ("GOOGL", 6, 248.27, "buy"),
        ("NVDA", 10, 186.23, "buy"),
        ("LRCX", 6, 149.23, "buy"),
        ("AVGO", 2, 337.025, "buy"),
        ("AMZN", 5, 220.88, "buy"),
        ("MSFT", 2, 528.285, "buy"),  # Additional MSFT
        ("AMD", 4, 214.85, "buy"),
        ("CRWD", 1, 497.0, "buy"),
        ("QCOM", 4, 169.9, "buy"),
        ("META", 1, 717.72, "buy"),
        ("NVDA", 20, 186.23, "buy"),  # Additional NVDA
        ("NVDA", 13, 186.23, "buy"),  # Additional NVDA
        ("NVDA", 20, 186.23, "buy"),  # Additional NVDA
        ("NVDA", 53, 186.23, "buy"),  # Additional NVDA
    ]

    for symbol, quantity, price, action_type in actions_data:
        test_db.create_action(
            trading_day_id=trading_day_id,
            action_type=action_type,
            symbol=symbol,
            quantity=quantity,
            price=price
        )

    test_db.connection.commit()

    # Create BaseAgent instance
    agent = BaseAgent(signature="gpt-5", basemodel="anthropic/claude-sonnet-4", stock_symbols=[])

    # Mock Database() to return our test_db
    with patch('api.database.Database', return_value=test_db):
        # Calculate final position
        holdings, cash = agent._calculate_final_position_from_actions(
            trading_day_id=trading_day_id,
            starting_cash=10000.0
        )

    # Verify holdings
    assert holdings["MSFT"] == 5, f"Expected 5 MSFT (3+2) but got {holdings.get('MSFT', 0)}"
    assert holdings["GOOGL"] == 6, f"Expected 6 GOOGL but got {holdings.get('GOOGL', 0)}"
    assert holdings["NVDA"] == 116, f"Expected 116 NVDA (10+20+13+20+53) but got {holdings.get('NVDA', 0)}"
    assert holdings["LRCX"] == 6, f"Expected 6 LRCX but got {holdings.get('LRCX', 0)}"
    assert holdings["AVGO"] == 2, f"Expected 2 AVGO but got {holdings.get('AVGO', 0)}"
    assert holdings["AMZN"] == 5, f"Expected 5 AMZN but got {holdings.get('AMZN', 0)}"
    assert holdings["AMD"] == 4, f"Expected 4 AMD but got {holdings.get('AMD', 0)}"
    assert holdings["CRWD"] == 1, f"Expected 1 CRWD but got {holdings.get('CRWD', 0)}"
    assert holdings["QCOM"] == 4, f"Expected 4 QCOM but got {holdings.get('QCOM', 0)}"
    assert holdings["META"] == 1, f"Expected 1 META but got {holdings.get('META', 0)}"

    # Verify cash (should be less than starting)
    assert cash < 10000.0, f"Cash should be less than $10,000 but got ${cash}"

    # Calculate expected cash
    total_spent = sum(qty * price for _, qty, price, _ in actions_data)
    expected_cash = 10000.0 - total_spent
    assert abs(cash - expected_cash) < 0.01, f"Expected cash ${expected_cash} but got ${cash}"


def test_calculate_final_position_with_previous_holdings(test_db):
    """Test calculating final position when starting with existing holdings."""

    # Create day 1 with ending holdings
    day1_id = test_db.create_trading_day(
        job_id='test-job',
        model='gpt-5',
        date='2025-10-06',
        starting_cash=10000.0,
        starting_portfolio_value=10000.0,
        daily_profit=0.0,
        daily_return_pct=0.0,
        ending_cash=8000.0,
        ending_portfolio_value=9500.0,
        days_since_last_trading=1
    )

    # Add day 1 ending holdings
    test_db.create_holding(day1_id, "AAPL", 10)
    test_db.create_holding(day1_id, "MSFT", 5)

    # Create day 2
    day2_id = test_db.create_trading_day(
        job_id='test-job',
        model='gpt-5',
        date='2025-10-07',
        starting_cash=8000.0,
        starting_portfolio_value=9500.0,
        daily_profit=0.0,
        daily_return_pct=0.0,
        ending_cash=8000.0,
        ending_portfolio_value=9500.0,
        days_since_last_trading=1
    )

    # Add day 2 actions (buy more AAPL, sell some MSFT)
    test_db.create_action(day2_id, "buy", "AAPL", 5, 150.0)
    test_db.create_action(day2_id, "sell", "MSFT", 2, 500.0)

    test_db.connection.commit()

    # Create BaseAgent instance
    agent = BaseAgent(signature="gpt-5", basemodel="anthropic/claude-sonnet-4", stock_symbols=[])

    # Mock Database() to return our test_db
    with patch('api.database.Database', return_value=test_db):
        # Calculate final position for day 2
        holdings, cash = agent._calculate_final_position_from_actions(
            trading_day_id=day2_id,
            starting_cash=8000.0
        )

    # Verify holdings
    assert holdings["AAPL"] == 15, f"Expected 15 AAPL (10+5) but got {holdings.get('AAPL', 0)}"
    assert holdings["MSFT"] == 3, f"Expected 3 MSFT (5-2) but got {holdings.get('MSFT', 0)}"

    # Verify cash
    # Started: 8000
    # Buy 5 AAPL @ 150 = -750
    # Sell 2 MSFT @ 500 = +1000
    # Final: 8000 - 750 + 1000 = 8250
    expected_cash = 8000.0 - (5 * 150.0) + (2 * 500.0)
    assert abs(cash - expected_cash) < 0.01, f"Expected cash ${expected_cash} but got ${cash}"


def test_calculate_final_position_no_trades(test_db):
    """Test calculating final position when no trades were executed."""

    # Create day 1 with ending holdings
    day1_id = test_db.create_trading_day(
        job_id='test-job',
        model='gpt-5',
        date='2025-10-06',
        starting_cash=10000.0,
        starting_portfolio_value=10000.0,
        daily_profit=0.0,
        daily_return_pct=0.0,
        ending_cash=9000.0,
        ending_portfolio_value=10000.0,
        days_since_last_trading=1
    )

    test_db.create_holding(day1_id, "AAPL", 10)

    # Create day 2 with NO actions
    day2_id = test_db.create_trading_day(
        job_id='test-job',
        model='gpt-5',
        date='2025-10-07',
        starting_cash=9000.0,
        starting_portfolio_value=10000.0,
        daily_profit=0.0,
        daily_return_pct=0.0,
        ending_cash=9000.0,
        ending_portfolio_value=10000.0,
        days_since_last_trading=1
    )

    # No actions added
    test_db.connection.commit()

    # Create BaseAgent instance
    agent = BaseAgent(signature="gpt-5", basemodel="anthropic/claude-sonnet-4", stock_symbols=[])

    # Mock Database() to return our test_db
    with patch('api.database.Database', return_value=test_db):
        # Calculate final position
        holdings, cash = agent._calculate_final_position_from_actions(
            trading_day_id=day2_id,
            starting_cash=9000.0
        )

    # Verify holdings unchanged
    assert holdings["AAPL"] == 10, f"Expected 10 AAPL but got {holdings.get('AAPL', 0)}"

    # Verify cash unchanged
    assert abs(cash - 9000.0) < 0.01, f"Expected cash $9000 but got ${cash}"
