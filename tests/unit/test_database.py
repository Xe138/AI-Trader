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

        conn = get_db_connection(db_path)
        assert conn is not None
        assert os.path.exists(os.path.dirname(db_path))

        conn.close()
        os.unlink(db_path)
        os.rmdir(os.path.dirname(db_path))
        os.rmdir(temp_dir)

    def test_get_db_connection_enables_foreign_keys(self):
        """Should enable foreign key constraints."""
        temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        temp_db.close()

        conn = get_db_connection(temp_db.name)

        # Check if foreign keys are enabled
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys")
        result = cursor.fetchone()[0]

        assert result == 1  # 1 = enabled

        conn.close()
        os.unlink(temp_db.name)

    def test_get_db_connection_row_factory(self):
        """Should set row factory for dict-like access."""
        temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        temp_db.close()

        conn = get_db_connection(temp_db.name)

        assert conn.row_factory == sqlite3.Row

        conn.close()
        os.unlink(temp_db.name)

    def test_get_db_connection_thread_safety(self):
        """Should allow check_same_thread=False for async compatibility."""
        temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        temp_db.close()

        # This should not raise an error
        conn = get_db_connection(temp_db.name)
        assert conn is not None

        conn.close()
        os.unlink(temp_db.name)


@pytest.mark.unit
class TestSchemaInitialization:
    """Test database schema initialization."""

    def test_initialize_database_creates_all_tables(self, clean_db):
        """Should create all 9 tables."""
        conn = get_db_connection(clean_db)
        cursor = conn.cursor()

        # Query sqlite_master for table names
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
        """)

        tables = [row[0] for row in cursor.fetchall()]

        expected_tables = [
            'holdings',
            'job_details',
            'jobs',
            'positions',
            'reasoning_logs',
            'tool_usage',
            'price_data',
            'price_data_coverage',
            'simulation_runs'
        ]

        assert sorted(tables) == sorted(expected_tables)

        conn.close()

    def test_initialize_database_creates_jobs_table(self, clean_db):
        """Should create jobs table with correct schema."""
        conn = get_db_connection(clean_db)
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

        conn.close()

    def test_initialize_database_creates_positions_table(self, clean_db):
        """Should create positions table with correct schema."""
        conn = get_db_connection(clean_db)
        cursor = conn.cursor()

        cursor.execute("PRAGMA table_info(positions)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}

        required_columns = [
            'id', 'job_id', 'date', 'model', 'action_id', 'action_type',
            'symbol', 'amount', 'price', 'cash', 'portfolio_value',
            'daily_profit', 'daily_return_pct', 'cumulative_profit',
            'cumulative_return_pct', 'created_at'
        ]

        for col_name in required_columns:
            assert col_name in columns

        conn.close()

    def test_initialize_database_creates_indexes(self, clean_db):
        """Should create all performance indexes."""
        conn = get_db_connection(clean_db)
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
            'idx_positions_job_id',
            'idx_positions_date',
            'idx_positions_model',
            'idx_positions_date_model',
            'idx_positions_unique',
            'idx_holdings_position_id',
            'idx_holdings_symbol',
            'idx_reasoning_logs_job_date_model',
            'idx_tool_usage_job_date_model'
        ]

        for index in required_indexes:
            assert index in indexes, f"Missing index: {index}"

        conn.close()

    def test_initialize_database_idempotent(self, clean_db):
        """Should be safe to call multiple times."""
        # Initialize once (already done by clean_db fixture)
        # Initialize again
        initialize_database(clean_db)

        # Should still have correct tables
        conn = get_db_connection(clean_db)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT COUNT(*) FROM sqlite_master
            WHERE type='table' AND name='jobs'
        """)

        assert cursor.fetchone()[0] == 1  # Only one jobs table

        conn.close()


@pytest.mark.unit
class TestForeignKeyConstraints:
    """Test foreign key constraint enforcement."""

    def test_cascade_delete_job_details(self, clean_db, sample_job_data):
        """Should cascade delete job_details when job is deleted."""
        conn = get_db_connection(clean_db)
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

        conn.close()

    def test_cascade_delete_positions(self, clean_db, sample_job_data, sample_position_data):
        """Should cascade delete positions when job is deleted."""
        conn = get_db_connection(clean_db)
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

        # Insert position
        cursor.execute("""
            INSERT INTO positions (
                job_id, date, model, action_id, action_type, symbol, amount, price,
                cash, portfolio_value, daily_profit, daily_return_pct,
                cumulative_profit, cumulative_return_pct, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, tuple(sample_position_data.values()))

        conn.commit()

        # Delete job
        cursor.execute("DELETE FROM jobs WHERE job_id = ?", (sample_job_data["job_id"],))
        conn.commit()

        # Verify position was cascade deleted
        cursor.execute("SELECT COUNT(*) FROM positions WHERE job_id = ?", (sample_job_data["job_id"],))
        assert cursor.fetchone()[0] == 0

        conn.close()

    def test_cascade_delete_holdings(self, clean_db, sample_job_data, sample_position_data):
        """Should cascade delete holdings when position is deleted."""
        conn = get_db_connection(clean_db)
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

        # Insert position
        cursor.execute("""
            INSERT INTO positions (
                job_id, date, model, action_id, action_type, symbol, amount, price,
                cash, portfolio_value, daily_profit, daily_return_pct,
                cumulative_profit, cumulative_return_pct, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, tuple(sample_position_data.values()))

        position_id = cursor.lastrowid

        # Insert holding
        cursor.execute("""
            INSERT INTO holdings (position_id, symbol, quantity)
            VALUES (?, ?, ?)
        """, (position_id, "AAPL", 10))

        conn.commit()

        # Verify holding exists
        cursor.execute("SELECT COUNT(*) FROM holdings WHERE position_id = ?", (position_id,))
        assert cursor.fetchone()[0] == 1

        # Delete position
        cursor.execute("DELETE FROM positions WHERE id = ?", (position_id,))
        conn.commit()

        # Verify holding was cascade deleted
        cursor.execute("SELECT COUNT(*) FROM holdings WHERE position_id = ?", (position_id,))
        assert cursor.fetchone()[0] == 0

        conn.close()


@pytest.mark.unit
class TestUtilityFunctions:
    """Test database utility functions."""

    def test_drop_all_tables(self, test_db_path):
        """Should drop all tables when called."""
        # Initialize database
        initialize_database(test_db_path)

        # Verify tables exist
        conn = get_db_connection(test_db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        assert cursor.fetchone()[0] == 9  # Updated to reflect all tables
        conn.close()

        # Drop all tables
        drop_all_tables(test_db_path)

        # Verify tables are gone
        conn = get_db_connection(test_db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        assert cursor.fetchone()[0] == 0
        conn.close()

    def test_vacuum_database(self, clean_db):
        """Should execute VACUUM command without errors."""
        # This should not raise an error
        vacuum_database(clean_db)

        # Verify database still accessible
        conn = get_db_connection(clean_db)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM jobs")
        assert cursor.fetchone()[0] == 0
        conn.close()

    def test_get_database_stats_empty(self, clean_db):
        """Should return correct stats for empty database."""
        stats = get_database_stats(clean_db)

        assert "database_size_mb" in stats
        assert stats["jobs"] == 0
        assert stats["job_details"] == 0
        assert stats["positions"] == 0
        assert stats["holdings"] == 0
        assert stats["reasoning_logs"] == 0
        assert stats["tool_usage"] == 0

    def test_get_database_stats_with_data(self, clean_db, sample_job_data):
        """Should return correct row counts with data."""
        conn = get_db_connection(clean_db)
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
        conn.close()

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

        # Create database without warnings column (simulate old schema)
        conn = get_db_connection(test_db_path)
        cursor = conn.cursor()

        # Create jobs table without warnings column (old schema)
        cursor.execute("""
            CREATE TABLE jobs (
                job_id TEXT PRIMARY KEY,
                config_path TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('pending', 'downloading_data', 'running', 'completed', 'partial', 'failed')),
                date_range TEXT NOT NULL,
                models TEXT NOT NULL,
                created_at TEXT NOT NULL,
                started_at TEXT,
                updated_at TEXT,
                completed_at TEXT,
                total_duration_seconds REAL,
                error TEXT
            )
        """)
        conn.commit()

        # Verify warnings column doesn't exist
        cursor.execute("PRAGMA table_info(jobs)")
        columns = [row[1] for row in cursor.fetchall()]
        assert 'warnings' not in columns

        conn.close()

        # Run initialize_database which should trigger migration
        initialize_database(test_db_path)

        # Verify warnings column was added
        conn = get_db_connection(test_db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(jobs)")
        columns = [row[1] for row in cursor.fetchall()]
        assert 'warnings' in columns

        # Verify we can insert and query warnings
        cursor.execute("""
            INSERT INTO jobs (job_id, config_path, status, date_range, models, created_at, warnings)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, ("test-job", "configs/test.json", "completed", "[]", "[]", "2025-01-20T00:00:00Z", "Test warning"))
        conn.commit()

        cursor.execute("SELECT warnings FROM jobs WHERE job_id = ?", ("test-job",))
        result = cursor.fetchone()
        assert result[0] == "Test warning"

        conn.close()

        # Clean up after test - drop all tables so we don't affect other tests
        drop_all_tables(test_db_path)

    def test_migration_adds_simulation_run_id_column(self, test_db_path):
        """Should add simulation_run_id column to existing positions table without it."""
        from api.database import drop_all_tables

        # Start with a clean slate
        drop_all_tables(test_db_path)

        # Create database without simulation_run_id column (simulate old schema)
        conn = get_db_connection(test_db_path)
        cursor = conn.cursor()

        # Create jobs table first (for foreign key)
        cursor.execute("""
            CREATE TABLE jobs (
                job_id TEXT PRIMARY KEY,
                config_path TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('pending', 'downloading_data', 'running', 'completed', 'partial', 'failed')),
                date_range TEXT NOT NULL,
                models TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        # Create positions table without simulation_run_id column (old schema)
        cursor.execute("""
            CREATE TABLE positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                date TEXT NOT NULL,
                model TEXT NOT NULL,
                action_id INTEGER NOT NULL,
                cash REAL NOT NULL,
                portfolio_value REAL NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (job_id) REFERENCES jobs(job_id) ON DELETE CASCADE
            )
        """)
        conn.commit()

        # Verify simulation_run_id column doesn't exist
        cursor.execute("PRAGMA table_info(positions)")
        columns = [row[1] for row in cursor.fetchall()]
        assert 'simulation_run_id' not in columns

        conn.close()

        # Run initialize_database which should trigger migration
        initialize_database(test_db_path)

        # Verify simulation_run_id column was added
        conn = get_db_connection(test_db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(positions)")
        columns = [row[1] for row in cursor.fetchall()]
        assert 'simulation_run_id' in columns

        conn.close()

        # Clean up after test - drop all tables so we don't affect other tests
        drop_all_tables(test_db_path)


@pytest.mark.unit
class TestCheckConstraints:
    """Test CHECK constraints on table columns."""

    def test_jobs_status_constraint(self, clean_db):
        """Should reject invalid job status values."""
        conn = get_db_connection(clean_db)
        cursor = conn.cursor()

        # Try to insert job with invalid status
        with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
            cursor.execute("""
                INSERT INTO jobs (job_id, config_path, status, date_range, models, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, ("test-job", "configs/test.json", "invalid_status", "[]", "[]", "2025-01-20T00:00:00Z"))

        conn.close()

    def test_job_details_status_constraint(self, clean_db, sample_job_data):
        """Should reject invalid job_detail status values."""
        conn = get_db_connection(clean_db)
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

        conn.close()

    def test_positions_action_type_constraint(self, clean_db, sample_job_data):
        """Should reject invalid action_type values."""
        conn = get_db_connection(clean_db)
        cursor = conn.cursor()

        # Insert valid job first
        cursor.execute("""
            INSERT INTO jobs (job_id, config_path, status, date_range, models, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, tuple(sample_job_data.values()))

        # Try to insert position with invalid action_type
        with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
            cursor.execute("""
                INSERT INTO positions (
                    job_id, date, model, action_id, action_type, cash, portfolio_value, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (sample_job_data["job_id"], "2025-01-16", "gpt-5", 1, "invalid_action", 10000, 10000, "2025-01-16T00:00:00Z"))

        conn.close()


# Coverage target: 95%+ for api/database.py
