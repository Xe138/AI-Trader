import pytest
from datetime import datetime
from api.database import Database


class TestDatabaseHelpers:

    @pytest.fixture
    def db(self, tmp_path):
        """Create test database with schema."""
        import importlib
        migration_module = importlib.import_module('api.migrations.001_trading_days_schema')
        create_trading_days_schema = migration_module.create_trading_days_schema

        db_path = tmp_path / "test.db"
        db = Database(str(db_path))

        # Create jobs table (prerequisite)
        db.connection.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                status TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        create_trading_days_schema(db)
        return db

    def test_create_trading_day(self, db):
        """Test creating a new trading day record."""
        # Insert job first
        db.connection.execute(
            "INSERT INTO jobs (job_id, status) VALUES (?, ?)",
            ("test-job", "running")
        )

        trading_day_id = db.create_trading_day(
            job_id="test-job",
            model="gpt-4",
            date="2025-01-15",
            starting_cash=10000.0,
            starting_portfolio_value=10000.0,
            daily_profit=0.0,
            daily_return_pct=0.0,
            ending_cash=9500.0,
            ending_portfolio_value=9500.0
        )

        assert trading_day_id is not None

        # Verify record created
        cursor = db.connection.execute(
            "SELECT * FROM trading_days WHERE id = ?",
            (trading_day_id,)
        )
        row = cursor.fetchone()
        assert row is not None

    def test_get_previous_trading_day(self, db):
        """Test retrieving previous trading day."""
        # Setup: Create job and two trading days
        db.connection.execute(
            "INSERT INTO jobs (job_id, status) VALUES (?, ?)",
            ("test-job", "running")
        )

        day1_id = db.create_trading_day(
            job_id="test-job",
            model="gpt-4",
            date="2025-01-15",
            starting_cash=10000.0,
            starting_portfolio_value=10000.0,
            daily_profit=0.0,
            daily_return_pct=0.0,
            ending_cash=9500.0,
            ending_portfolio_value=9500.0
        )

        day2_id = db.create_trading_day(
            job_id="test-job",
            model="gpt-4",
            date="2025-01-16",
            starting_cash=9500.0,
            starting_portfolio_value=9500.0,
            daily_profit=-500.0,
            daily_return_pct=-5.0,
            ending_cash=9700.0,
            ending_portfolio_value=9700.0
        )

        # Test: Get previous day from day2
        previous = db.get_previous_trading_day(
            job_id="test-job",
            model="gpt-4",
            current_date="2025-01-16"
        )

        assert previous is not None
        assert previous["date"] == "2025-01-15"
        assert previous["ending_cash"] == 9500.0

    def test_get_previous_trading_day_with_weekend_gap(self, db):
        """Test retrieving previous trading day across weekend."""
        db.connection.execute(
            "INSERT INTO jobs (job_id, status) VALUES (?, ?)",
            ("test-job", "running")
        )

        # Friday
        db.create_trading_day(
            job_id="test-job",
            model="gpt-4",
            date="2025-01-17",  # Friday
            starting_cash=10000.0,
            starting_portfolio_value=10000.0,
            daily_profit=0.0,
            daily_return_pct=0.0,
            ending_cash=9500.0,
            ending_portfolio_value=9500.0
        )

        # Test: Get previous from Monday (should find Friday)
        previous = db.get_previous_trading_day(
            job_id="test-job",
            model="gpt-4",
            current_date="2025-01-20"  # Monday
        )

        assert previous is not None
        assert previous["date"] == "2025-01-17"

    def test_get_previous_trading_day_across_jobs(self, db):
        """Test retrieving previous trading day from different job (cross-job continuity)."""
        # Setup: Create two jobs
        db.connection.execute(
            "INSERT INTO jobs (job_id, status, config_path, date_range, models, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("job-1", "completed", "config.json", "2025-10-07,2025-10-07", "deepseek-chat-v3.1", "2025-11-07T00:00:00Z")
        )
        db.connection.execute(
            "INSERT INTO jobs (job_id, status, config_path, date_range, models, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("job-2", "running", "config.json", "2025-10-08,2025-10-08", "deepseek-chat-v3.1", "2025-11-07T01:00:00Z")
        )

        # Day 1 in job-1
        db.create_trading_day(
            job_id="job-1",
            model="deepseek-chat-v3.1",
            date="2025-10-07",
            starting_cash=10000.0,
            starting_portfolio_value=10000.0,
            daily_profit=214.58,
            daily_return_pct=2.15,
            ending_cash=123.59,
            ending_portfolio_value=10214.58
        )

        # Test: Get previous day from job-2 on next date
        # Should find job-1's record (cross-job continuity)
        previous = db.get_previous_trading_day(
            job_id="job-2",
            model="deepseek-chat-v3.1",
            current_date="2025-10-08"
        )

        assert previous is not None
        assert previous["date"] == "2025-10-07"
        assert previous["ending_cash"] == 123.59
        assert previous["ending_portfolio_value"] == 10214.58

    def test_get_ending_holdings(self, db):
        """Test retrieving ending holdings for a trading day."""
        db.connection.execute(
            "INSERT INTO jobs (job_id, status) VALUES (?, ?)",
            ("test-job", "running")
        )

        trading_day_id = db.create_trading_day(
            job_id="test-job",
            model="gpt-4",
            date="2025-01-15",
            starting_cash=10000.0,
            starting_portfolio_value=10000.0,
            daily_profit=0.0,
            daily_return_pct=0.0,
            ending_cash=9000.0,
            ending_portfolio_value=10000.0
        )

        # Add holdings
        db.create_holding(trading_day_id, "AAPL", 10)
        db.create_holding(trading_day_id, "MSFT", 5)

        # Test
        holdings = db.get_ending_holdings(trading_day_id)

        assert len(holdings) == 2
        assert {"symbol": "AAPL", "quantity": 10} in holdings
        assert {"symbol": "MSFT", "quantity": 5} in holdings

    def test_get_starting_holdings_first_day(self, db):
        """Test starting holdings for first trading day (should be empty)."""
        db.connection.execute(
            "INSERT INTO jobs (job_id, status) VALUES (?, ?)",
            ("test-job", "running")
        )

        trading_day_id = db.create_trading_day(
            job_id="test-job",
            model="gpt-4",
            date="2025-01-15",
            starting_cash=10000.0,
            starting_portfolio_value=10000.0,
            daily_profit=0.0,
            daily_return_pct=0.0,
            ending_cash=9500.0,
            ending_portfolio_value=9500.0
        )

        holdings = db.get_starting_holdings(trading_day_id)

        assert holdings == []

    def test_get_starting_holdings_from_previous_day(self, db):
        """Test starting holdings derived from previous day's ending."""
        db.connection.execute(
            "INSERT INTO jobs (job_id, status) VALUES (?, ?)",
            ("test-job", "running")
        )

        # Day 1
        day1_id = db.create_trading_day(
            job_id="test-job",
            model="gpt-4",
            date="2025-01-15",
            starting_cash=10000.0,
            starting_portfolio_value=10000.0,
            daily_profit=0.0,
            daily_return_pct=0.0,
            ending_cash=9000.0,
            ending_portfolio_value=10000.0
        )
        db.create_holding(day1_id, "AAPL", 10)

        # Day 2
        day2_id = db.create_trading_day(
            job_id="test-job",
            model="gpt-4",
            date="2025-01-16",
            starting_cash=9000.0,
            starting_portfolio_value=10000.0,
            daily_profit=0.0,
            daily_return_pct=0.0,
            ending_cash=8500.0,
            ending_portfolio_value=9500.0
        )

        # Test: Day 2 starting = Day 1 ending
        holdings = db.get_starting_holdings(day2_id)

        assert len(holdings) == 1
        assert holdings[0]["symbol"] == "AAPL"
        assert holdings[0]["quantity"] == 10

    def test_create_action(self, db):
        """Test creating an action record."""
        db.connection.execute(
            "INSERT INTO jobs (job_id, status) VALUES (?, ?)",
            ("test-job", "running")
        )

        trading_day_id = db.create_trading_day(
            job_id="test-job",
            model="gpt-4",
            date="2025-01-15",
            starting_cash=10000.0,
            starting_portfolio_value=10000.0,
            daily_profit=0.0,
            daily_return_pct=0.0,
            ending_cash=9500.0,
            ending_portfolio_value=9500.0
        )

        action_id = db.create_action(
            trading_day_id=trading_day_id,
            action_type="buy",
            symbol="AAPL",
            quantity=10,
            price=100.0
        )

        assert action_id is not None

        # Verify
        cursor = db.connection.execute(
            "SELECT * FROM actions WHERE id = ?",
            (action_id,)
        )
        row = cursor.fetchone()
        assert row is not None

    def test_get_actions(self, db):
        """Test retrieving all actions for a trading day."""
        db.connection.execute(
            "INSERT INTO jobs (job_id, status) VALUES (?, ?)",
            ("test-job", "running")
        )

        trading_day_id = db.create_trading_day(
            job_id="test-job",
            model="gpt-4",
            date="2025-01-15",
            starting_cash=10000.0,
            starting_portfolio_value=10000.0,
            daily_profit=0.0,
            daily_return_pct=0.0,
            ending_cash=9500.0,
            ending_portfolio_value=9500.0
        )

        db.create_action(trading_day_id, "buy", "AAPL", 10, 100.0)
        db.create_action(trading_day_id, "sell", "MSFT", 5, 50.0)

        actions = db.get_actions(trading_day_id)

        assert len(actions) == 2
