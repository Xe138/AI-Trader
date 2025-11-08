"""
Unit tests for api/database.py module.

Coverage target: 95%+

Tests verify:
- Database connection management
- Schema initialization
- Table creation and indexes
- Foreign key constraints
- Utility functions
"""

import pytest
import sqlite3
import os
import tempfile
from pathlib import Path
from api.database import (
    get_db_connection,
    db_connection,
    initialize_database,
    drop_all_tables,
    vacuum_database,
    get_database_stats
)


@pytest.mark.unit
class TestDatabaseConnection:
    """Test database connection functionality."""

    def test_get_db_connection_creates_directory(self):
        """Should create data directory if it doesn't exist."""
        temp_dir = tempfile.mkdtemp()
        db_path = os.path.join(temp_dir, "subdir", "test.db")

        with db_connection(db_path) as conn:
            assert conn is not None
            assert os.path.exists(os.path.dirname(db_path))

        os.unlink(db_path)
        os.rmdir(os.path.dirname(db_path))
        os.rmdir(temp_dir)

    def test_get_db_connection_enables_foreign_keys(self):
        """Should enable foreign key constraints."""
        temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        temp_db.close()

        with db_connection(temp_db.name) as conn:

            # Check if foreign keys are enabled
            cursor = conn.cursor()
            cursor.execute("PRAGMA foreign_keys")
            result = cursor.fetchone()[0]

            assert result == 1  # 1 = enabled

        os.unlink(temp_db.name)

    def test_get_db_connection_row_factory(self):
        """Should set row factory for dict-like access."""
        temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        temp_db.close()

        with db_connection(temp_db.name) as conn:

            assert conn.row_factory == sqlite3.Row

        os.unlink(temp_db.name)

    def test_get_db_connection_thread_safety(self):
        """Should allow check_same_thread=False for async compatibility."""
        temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        temp_db.close()

        # This should not raise an error
        with db_connection(temp_db.name) as conn:
            assert conn is not None

        os.unlink(temp_db.name)


@pytest.mark.unit
class TestSchemaInitialization:
    """Test database schema initialization."""

    def test_initialize_database_creates_all_tables(self, clean_db):
        """Should create all 10 tables."""
        with db_connection(clean_db) as conn:
            cursor = conn.cursor()

            # Query sqlite_master for table names
            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name NOT LIKE 'sqlite_%'
                ORDER BY name
            """)

            tables = [row[0] for row in cursor.fetchall()]

            expected_tables = [
                'actions',
                'holdings',
                'job_details',
                'jobs',
                'tool_usage',
                'price_data',
                'price_data_coverage',
                'simulation_runs',
                'trading_days'  # New day-centric schema
            ]

            assert sorted(tables) == sorted(expected_tables)


    def test_initialize_database_creates_jobs_table(self, clean_db):
        """Should create jobs table with correct schema."""
        with db_connection(clean_db) as conn:
            cursor = conn.cursor()

            cursor.execute("PRAGMA table_info(jobs)")
            columns = {row[1]: row[2] for row in cursor.fetchall()}

            expected_columns = {
                'job_id': 'TEXT',
                'config_path': 'TEXT',
                'status': 'TEXT',
                'date_range': 'TEXT',
                'models': 'TEXT',
                'created_at': 'TEXT',
                'started_at': 'TEXT',
                'updated_at': 'TEXT',
                'completed_at': 'TEXT',
                'total_duration_seconds': 'REAL',
                'error': 'TEXT',
                'warnings': 'TEXT'
            }

            for col_name, col_type in expected_columns.items():
                assert col_name in columns
                assert columns[col_name] == col_type


    def test_initialize_database_creates_trading_days_table(self, clean_db):
        """Should create trading_days table with correct schema."""
        with db_connection(clean_db) as conn:
            cursor = conn.cursor()

            cursor.execute("PRAGMA table_info(trading_days)")
            columns = {row[1]: row[2] for row in cursor.fetchall()}

            required_columns = [
                'id', 'job_id', 'date', 'model', 'starting_cash', 'ending_cash',
                'starting_portfolio_value', 'ending_portfolio_value',
                'daily_profit', 'daily_return_pct', 'days_since_last_trading',
                'total_actions', 'reasoning_summary', 'reasoning_full', 'created_at'
            ]

            for col_name in required_columns:
                assert col_name in columns


    def test_initialize_database_creates_indexes(self, clean_db):
        """Should create all performance indexes."""
        with db_connection(clean_db) as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='index' AND name LIKE 'idx_%'
                ORDER BY name
            """)

            indexes = [row[0] for row in cursor.fetchall()]

            required_indexes = [
                'idx_jobs_status',
                'idx_jobs_created_at',
                'idx_job_details_job_id',
                'idx_job_details_status',
                'idx_job_details_unique',
                'idx_trading_days_lookup',  # Compound index in new schema
                'idx_holdings_day',
                'idx_actions_day',
                'idx_tool_usage_job_date_model'
            ]

            for index in required_indexes:
                assert index in indexes, f"Missing index: {index}"


    def test_initialize_database_idempotent(self, clean_db):
        """Should be safe to call multiple times."""
        # Initialize once (already done by clean_db fixture)
        # Initialize again
        initialize_database(clean_db)

        # Should still have correct tables
        with db_connection(clean_db) as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT COUNT(*) FROM sqlite_master
                WHERE type='table' AND name='jobs'
            """)

            assert cursor.fetchone()[0] == 1  # Only one jobs table



@pytest.mark.unit
class TestForeignKeyConstraints:
    """Test foreign key constraint enforcement."""

    def test_cascade_delete_job_details(self, clean_db, sample_job_data):
        """Should cascade delete job_details when job is deleted."""
        with db_connection(clean_db) as conn:
            cursor = conn.cursor()

            # Insert job
            cursor.execute("""
                INSERT INTO jobs (job_id, config_path, status, date_range, models, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                sample_job_data["job_id"],
                sample_job_data["config_path"],
                sample_job_data["status"],
                sample_job_data["date_range"],
                sample_job_data["models"],
                sample_job_data["created_at"]
            ))

            # Insert job_detail
            cursor.execute("""
                INSERT INTO job_details (job_id, date, model, status)
                VALUES (?, ?, ?, ?)
            """, (sample_job_data["job_id"], "2025-01-16", "gpt-5", "pending"))

            conn.commit()

            # Verify job_detail exists
            cursor.execute("SELECT COUNT(*) FROM job_details WHERE job_id = ?", (sample_job_data["job_id"],))
            assert cursor.fetchone()[0] == 1

            # Delete job
            cursor.execute("DELETE FROM jobs WHERE job_id = ?", (sample_job_data["job_id"],))
            conn.commit()

            # Verify job_detail was cascade deleted
            cursor.execute("SELECT COUNT(*) FROM job_details WHERE job_id = ?", (sample_job_data["job_id"],))
            assert cursor.fetchone()[0] == 0


    def test_cascade_delete_trading_days(self, clean_db, sample_job_data):
        """Should cascade delete trading_days when job is deleted."""
        with db_connection(clean_db) as conn:
            cursor = conn.cursor()

            # Insert job
            cursor.execute("""
                INSERT INTO jobs (job_id, config_path, status, date_range, models, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                sample_job_data["job_id"],
                sample_job_data["config_path"],
                sample_job_data["status"],
                sample_job_data["date_range"],
                sample_job_data["models"],
                sample_job_data["created_at"]
            ))

            # Insert trading_day
            cursor.execute("""
                INSERT INTO trading_days (
                    job_id, date, model, starting_cash, ending_cash,
                    starting_portfolio_value, ending_portfolio_value,
                    daily_profit, daily_return_pct, days_since_last_trading,
                    total_actions, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                sample_job_data["job_id"], "2025-01-16", "test-model",
                10000.0, 9500.0, 10000.0, 9500.0,
                -500.0, -5.0, 0, 1, "2025-01-16T10:00:00Z"
            ))

            conn.commit()

            # Delete job
            cursor.execute("DELETE FROM jobs WHERE job_id = ?", (sample_job_data["job_id"],))
            conn.commit()

            # Verify trading_day was cascade deleted
            cursor.execute("SELECT COUNT(*) FROM trading_days WHERE job_id = ?", (sample_job_data["job_id"],))
            assert cursor.fetchone()[0] == 0


    def test_cascade_delete_holdings(self, clean_db, sample_job_data):
        """Should cascade delete holdings when trading_day is deleted."""
        with db_connection(clean_db) as conn:
            cursor = conn.cursor()

            # Insert job
            cursor.execute("""
                INSERT INTO jobs (job_id, config_path, status, date_range, models, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                sample_job_data["job_id"],
                sample_job_data["config_path"],
                sample_job_data["status"],
                sample_job_data["date_range"],
                sample_job_data["models"],
                sample_job_data["created_at"]
            ))

            # Insert trading_day
            cursor.execute("""
                INSERT INTO trading_days (
                    job_id, date, model, starting_cash, ending_cash,
                    starting_portfolio_value, ending_portfolio_value,
                    daily_profit, daily_return_pct, days_since_last_trading,
                    total_actions, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                sample_job_data["job_id"], "2025-01-16", "test-model",
                10000.0, 9500.0, 10000.0, 9500.0,
                -500.0, -5.0, 0, 1, "2025-01-16T10:00:00Z"
            ))

            trading_day_id = cursor.lastrowid

            # Insert holding
            cursor.execute("""
                INSERT INTO holdings (trading_day_id, symbol, quantity)
                VALUES (?, ?, ?)
            """, (trading_day_id, "AAPL", 10))

            conn.commit()

            # Verify holding exists
            cursor.execute("SELECT COUNT(*) FROM holdings WHERE trading_day_id = ?", (trading_day_id,))
            assert cursor.fetchone()[0] == 1

            # Delete trading_day
            cursor.execute("DELETE FROM trading_days WHERE id = ?", (trading_day_id,))
            conn.commit()

            # Verify holding was cascade deleted
            cursor.execute("SELECT COUNT(*) FROM holdings WHERE trading_day_id = ?", (trading_day_id,))
            assert cursor.fetchone()[0] == 0



@pytest.mark.unit
class TestUtilityFunctions:
    """Test database utility functions."""

    def test_drop_all_tables(self, test_db_path):
        """Should drop all tables when called."""
        # Initialize database
        initialize_database(test_db_path)

        # Also initialize new schema
        from api.database import Database
        db = Database(test_db_path)
        db.connection.close()

        # Verify tables exist
        with db_connection(test_db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
            # New schema: jobs, job_details, trading_days, holdings, actions, tool_usage, price_data, price_data_coverage, simulation_runs (9 tables)
            assert cursor.fetchone()[0] == 9

        # Drop all tables
        drop_all_tables(test_db_path)

        # Verify tables are gone
        with db_connection(test_db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
            assert cursor.fetchone()[0] == 0

    def test_vacuum_database(self, clean_db):
        """Should execute VACUUM command without errors."""
        # This should not raise an error
        vacuum_database(clean_db)

        # Verify database still accessible
        with db_connection(clean_db) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM jobs")
            assert cursor.fetchone()[0] == 0

    def test_get_database_stats_empty(self, clean_db):
        """Should return correct stats for empty database."""
        stats = get_database_stats(clean_db)

        assert "database_size_mb" in stats
        assert stats["jobs"] == 0
        assert stats["job_details"] == 0
        assert stats["trading_days"] == 0
        assert stats["holdings"] == 0
        assert stats["actions"] == 0
        assert stats["tool_usage"] == 0

    def test_get_database_stats_with_data(self, clean_db, sample_job_data):
        """Should return correct row counts with data."""
        with db_connection(clean_db) as conn:
            cursor = conn.cursor()

            # Insert job
            cursor.execute("""
                INSERT INTO jobs (job_id, config_path, status, date_range, models, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                sample_job_data["job_id"],
                sample_job_data["config_path"],
                sample_job_data["status"],
                sample_job_data["date_range"],
                sample_job_data["models"],
                sample_job_data["created_at"]
            ))

            # Insert job_detail
            cursor.execute("""
                INSERT INTO job_details (job_id, date, model, status)
                VALUES (?, ?, ?, ?)
            """, (sample_job_data["job_id"], "2025-01-16", "gpt-5", "pending"))

            conn.commit()

        stats = get_database_stats(clean_db)

        assert stats["jobs"] == 1
        assert stats["job_details"] == 1
        assert stats["database_size_mb"] > 0


@pytest.mark.unit
class TestSchemaMigration:
    """Test database schema migration functionality."""

    def test_migration_adds_warnings_column(self, test_db_path):
        """Should add warnings column to existing jobs table without it."""
        from api.database import drop_all_tables

        # Start with a clean slate
        drop_all_tables(test_db_path)

        # Initialize database with current schema
        initialize_database(test_db_path)

        # Verify warnings column exists in current schema
        with db_connection(test_db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(jobs)")
            columns = [row[1] for row in cursor.fetchall()]
            assert 'warnings' in columns, "warnings column should exist in jobs table schema"

            # Verify we can insert and query warnings
            cursor.execute("""
                INSERT INTO jobs (job_id, config_path, status, date_range, models, created_at, warnings)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, ("test-job", "configs/test.json", "completed", "[]", "[]", "2025-01-20T00:00:00Z", "Test warning"))
            conn.commit()

            cursor.execute("SELECT warnings FROM jobs WHERE job_id = ?", ("test-job",))
            result = cursor.fetchone()
            assert result[0] == "Test warning"


        # Clean up after test - drop all tables so we don't affect other tests
        drop_all_tables(test_db_path)


@pytest.mark.unit
class TestCheckConstraints:
    """Test CHECK constraints on table columns."""

    def test_jobs_status_constraint(self, clean_db):
        """Should reject invalid job status values."""
        with db_connection(clean_db) as conn:
            cursor = conn.cursor()

            # Try to insert job with invalid status
            with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
                cursor.execute("""
                    INSERT INTO jobs (job_id, config_path, status, date_range, models, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, ("test-job", "configs/test.json", "invalid_status", "[]", "[]", "2025-01-20T00:00:00Z"))


    def test_job_details_status_constraint(self, clean_db, sample_job_data):
        """Should reject invalid job_detail status values."""
        with db_connection(clean_db) as conn:
            cursor = conn.cursor()

            # Insert valid job first
            cursor.execute("""
                INSERT INTO jobs (job_id, config_path, status, date_range, models, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, tuple(sample_job_data.values()))

            # Try to insert job_detail with invalid status
            with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
                cursor.execute("""
                    INSERT INTO job_details (job_id, date, model, status)
                    VALUES (?, ?, ?, ?)
                """, (sample_job_data["job_id"], "2025-01-16", "gpt-5", "invalid_status"))


    def test_actions_action_type_constraint(self, clean_db, sample_job_data):
        """Should reject invalid action_type values in actions table."""
        with db_connection(clean_db) as conn:
            cursor = conn.cursor()

            # Insert valid job first
            cursor.execute("""
                INSERT INTO jobs (job_id, config_path, status, date_range, models, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, tuple(sample_job_data.values()))

            # Insert trading_day
            cursor.execute("""
                INSERT INTO trading_days (
                    job_id, date, model, starting_cash, ending_cash,
                    starting_portfolio_value, ending_portfolio_value,
                    daily_profit, daily_return_pct, days_since_last_trading,
                    total_actions, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                sample_job_data["job_id"], "2025-01-16", "test-model",
                10000.0, 9500.0, 10000.0, 9500.0,
                -500.0, -5.0, 0, 1, "2025-01-16T10:00:00Z"
            ))

            trading_day_id = cursor.lastrowid

            # Try to insert action with invalid action_type
            with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
                cursor.execute("""
                    INSERT INTO actions (
                        trading_day_id, action_type, symbol, quantity, price, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                """, (trading_day_id, "invalid_action", "AAPL", 10, 150.0, "2025-01-16T10:00:00Z"))



# Coverage target: 95%+ for api/database.py
