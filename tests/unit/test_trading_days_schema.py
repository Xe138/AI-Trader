import pytest
import sqlite3
import importlib.util
import sys
import os

# Import migration module with numeric prefix
migration_path = os.path.join(os.path.dirname(__file__), '../../api/migrations/001_trading_days_schema.py')
spec = importlib.util.spec_from_file_location("migration_001", migration_path)
migration_001 = importlib.util.module_from_spec(spec)
sys.modules["migration_001"] = migration_001
spec.loader.exec_module(migration_001)
create_trading_days_schema = migration_001.create_trading_days_schema


class MockDatabase:
    """Simple mock database for testing migrations."""
    def __init__(self, connection):
        self.connection = connection


class TestTradingDaysSchema:

    @pytest.fixture
    def db(self, tmp_path):
        """Create temporary test database."""
        db_path = tmp_path / "test.db"
        connection = sqlite3.connect(str(db_path))
        return MockDatabase(connection)

    def test_create_trading_days_table(self, db):
        """Test trading_days table is created with correct schema."""
        create_trading_days_schema(db)

        # Query schema
        cursor = db.connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='trading_days'"
        )
        schema = cursor.fetchone()[0]

        # Verify required columns
        assert "job_id TEXT NOT NULL" in schema
        assert "model TEXT NOT NULL" in schema
        assert "date TEXT NOT NULL" in schema
        assert "starting_cash REAL NOT NULL" in schema
        assert "starting_portfolio_value REAL NOT NULL" in schema
        assert "daily_profit REAL NOT NULL" in schema
        assert "daily_return_pct REAL NOT NULL" in schema
        assert "ending_cash REAL NOT NULL" in schema
        assert "ending_portfolio_value REAL NOT NULL" in schema
        assert "reasoning_summary TEXT" in schema
        assert "reasoning_full TEXT" in schema
        assert "UNIQUE(job_id, model, date)" in schema

    def test_create_holdings_table(self, db):
        """Test holdings table is created with correct schema."""
        create_trading_days_schema(db)

        cursor = db.connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='holdings'"
        )
        schema = cursor.fetchone()[0]

        assert "trading_day_id INTEGER NOT NULL" in schema
        assert "symbol TEXT NOT NULL" in schema
        assert "quantity INTEGER NOT NULL" in schema
        assert "FOREIGN KEY (trading_day_id) REFERENCES trading_days(id)" in schema
        assert "UNIQUE(trading_day_id, symbol)" in schema

    def test_create_actions_table(self, db):
        """Test actions table is created with correct schema."""
        create_trading_days_schema(db)

        cursor = db.connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='actions'"
        )
        schema = cursor.fetchone()[0]

        assert "trading_day_id INTEGER NOT NULL" in schema
        assert "action_type TEXT NOT NULL" in schema
        assert "symbol TEXT" in schema
        assert "quantity INTEGER" in schema
        assert "price REAL" in schema
        assert "FOREIGN KEY (trading_day_id) REFERENCES trading_days(id)" in schema
