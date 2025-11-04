import pytest
from api.database import Database


class TestDatabaseInitialization:

    def test_database_creates_new_schema_on_init(self, tmp_path):
        """Test database automatically creates trading_days schema."""
        db_path = tmp_path / "new.db"

        # Create database (should auto-initialize schema)
        db = Database(str(db_path))

        # Verify trading_days table exists
        cursor = db.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='trading_days'"
        )
        assert cursor.fetchone() is not None

        # Verify holdings table exists
        cursor = db.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='holdings'"
        )
        assert cursor.fetchone() is not None

        # Verify actions table exists
        cursor = db.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='actions'"
        )
        assert cursor.fetchone() is not None
