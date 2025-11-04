"""Integration tests for P&L calculation in BaseAgent."""
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import os
import json


class TestAgentPnLIntegration:
    """Test P&L calculation integration in BaseAgent.run_trading_session."""

    @pytest.fixture
    def test_db(self, tmp_path):
        """Create test database with trading_days schema."""
        import importlib
        from api.database import Database

        migration_module = importlib.import_module("api.migrations.001_trading_days_schema")
        create_trading_days_schema = migration_module.create_trading_days_schema

        db_path = tmp_path / "test.db"
        db = Database(str(db_path))

        # Create jobs table (prerequisite)
        db.connection.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                status TEXT
            )
        """)

        # Create trading_days schema
        create_trading_days_schema(db)

        # Insert test job
        db.connection.execute(
            "INSERT INTO jobs (job_id, status) VALUES (?, ?)",
            ("test-job", "running")
        )
        db.connection.commit()

        yield db
        db.connection.close()

    @pytest.mark.asyncio
    @patch('agent.base_agent.base_agent.is_dev_mode')
    @patch('tools.deployment_config.get_db_path')
    @patch('tools.general_tools.get_config_value')
    @patch('tools.general_tools.write_config_value')
    async def test_run_trading_session_creates_trading_day_record(
        self, mock_write_config, mock_get_config, mock_db_path, mock_is_dev, test_db
    ):
        """Test that run_trading_session creates a trading_day record with P&L."""
        from agent.base_agent.base_agent import BaseAgent

        # Setup dev mode
        mock_is_dev.return_value = True

        # Setup database path
        mock_db_path.return_value = test_db.db_path

        # Setup config mocks
        mock_get_config.side_effect = lambda key: {
            "IF_TRADE": False,
            "JOB_ID": "test-job",
            "TODAY_DATE": "2025-01-15",
            "SIGNATURE": "test-model"
        }.get(key)

        # Create BaseAgent instance
        agent = BaseAgent(
            signature="test-model",
            basemodel="gpt-4",
            max_steps=2,
            initial_cash=10000.0,
            init_date="2025-01-01"
        )

        # Skip actual initialization - just set up mocks directly
        agent.client = Mock()
        agent.tools = []

        # Mock the AI model to return finish signal immediately
        agent.model = AsyncMock()
        agent.model.ainvoke = AsyncMock(return_value=Mock(
            content="<FINISH_SIGNAL>"
        ))

        # Mock agent creation
        with patch('agent.base_agent.base_agent.create_agent') as mock_create_agent:
            mock_agent = MagicMock()
            mock_agent.ainvoke = AsyncMock(return_value={
                "messages": [{"content": "<FINISH_SIGNAL>"}]
            })
            mock_create_agent.return_value = mock_agent

            # Mock price tools
            with patch('tools.price_tools.get_open_prices') as mock_get_prices:
                with patch('tools.price_tools.get_yesterday_open_and_close_price') as mock_yesterday_prices:
                    mock_get_prices.return_value = {"AAPL_price": 150.0}
                    mock_yesterday_prices.return_value = ({}, {"AAPL_price": 145.0})

                    # Mock context injector
                    agent.context_injector = Mock()
                    agent.context_injector.session_id = "test-session-id"
                    agent.context_injector.job_id = "test-job"

                    # Mock get_current_position_from_db to return initial holdings
                    with patch('agent_tools.tool_trade.get_current_position_from_db') as mock_get_position:
                        mock_get_position.return_value = ({"CASH": 10000.0}, 0)

                        # Mock add_no_trade_record_to_db to avoid FK constraint issues
                        with patch('tools.price_tools.add_no_trade_record_to_db') as mock_no_trade:
                            # Run trading session
                            await agent.run_trading_session("2025-01-15")

                            # Verify trading_day record was created
                            cursor = test_db.connection.execute(
                                """
                                SELECT id, model, date, starting_cash, ending_cash,
                                       starting_portfolio_value, ending_portfolio_value,
                                       daily_profit, daily_return_pct, total_actions
                                FROM trading_days
                                WHERE job_id = ? AND model = ? AND date = ?
                                """,
                                ("test-job", "test-model", "2025-01-15")
                            )
                            row = cursor.fetchone()

                            # Verify record exists
                            assert row is not None, "trading_day record should be created"

                            # Verify basic fields
                            assert row[1] == "test-model"
                            assert row[2] == "2025-01-15"
                            assert row[3] == 10000.0  # starting_cash
                            assert row[5] == 10000.0  # starting_portfolio_value (first day)
                            assert row[7] == 0.0  # daily_profit (first day)
                            assert row[8] == 0.0  # daily_return_pct (first day)

                            # Verify action count
                            assert row[9] == 0  # total_actions (no trades executed in test)

    @pytest.mark.asyncio
    async def test_pnl_calculation_components_exist(self):
        """Verify P&L calculation components exist and are importable."""
        from agent.pnl_calculator import DailyPnLCalculator
        from agent.reasoning_summarizer import ReasoningSummarizer

        # Test DailyPnLCalculator
        calculator = DailyPnLCalculator(initial_cash=10000.0)
        assert calculator is not None

        # Test first day calculation (should be zero P&L)
        result = calculator.calculate(
            previous_day=None,
            current_date="2025-01-15",
            current_prices={"AAPL": 150.0}
        )
        assert result["daily_profit"] == 0.0
        assert result["daily_return_pct"] == 0.0
        assert result["starting_portfolio_value"] == 10000.0

        # Test ReasoningSummarizer (without actual AI model)
        # We'll test this with a mock model
        mock_model = Mock()
        summarizer = ReasoningSummarizer(model=mock_model)
        assert summarizer is not None
