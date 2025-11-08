import pytest
import sqlite3
from api.database import initialize_database, get_db_connection, db_connection

def test_jobs_table_allows_downloading_data_status(tmp_path):
    """Test that jobs table accepts downloading_data status."""
    db_path = str(tmp_path / "test.db")
    initialize_database(db_path)

    with db_connection(db_path) as conn:
        cursor = conn.cursor()

        # Should not raise constraint violation
        cursor.execute("""
            INSERT INTO jobs (job_id, config_path, status, date_range, models, created_at)
            VALUES ('test-123', 'config.json', 'downloading_data', '[]', '[]', '2025-11-01T00:00:00Z')
        """)
        conn.commit()

        # Verify it was inserted
        cursor.execute("SELECT status FROM jobs WHERE job_id = 'test-123'")
        result = cursor.fetchone()
        assert result[0] == "downloading_data"


def test_jobs_table_has_warnings_column(tmp_path):
    """Test that jobs table has warnings TEXT column."""
    db_path = str(tmp_path / "test.db")
    initialize_database(db_path)

    with db_connection(db_path) as conn:
        cursor = conn.cursor()

        # Insert job with warnings
        cursor.execute("""
            INSERT INTO jobs (job_id, config_path, status, date_range, models, created_at, warnings)
            VALUES ('test-456', 'config.json', 'completed', '[]', '[]', '2025-11-01T00:00:00Z', '["Warning 1", "Warning 2"]')
        """)
        conn.commit()

        # Verify warnings can be retrieved
        cursor.execute("SELECT warnings FROM jobs WHERE job_id = 'test-456'")
        result = cursor.fetchone()
        assert result[0] == '["Warning 1", "Warning 2"]'

