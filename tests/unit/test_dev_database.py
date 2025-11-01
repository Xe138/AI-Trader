import os
import pytest
from pathlib import Path
from api.database import initialize_dev_database, cleanup_dev_database


def test_initialize_dev_database_creates_fresh_db(tmp_path):
    """Test dev database initialization creates clean schema"""
    db_path = str(tmp_path / "test_dev.db")

    # Create initial database with some data
    from api.database import get_db_connection, initialize_database
    initialize_database(db_path)
    conn = get_db_connection(db_path)
    conn.execute("INSERT INTO jobs (job_id, config_path, status, date_range, models, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                 ("test-job", "config.json", "completed", "2025-01-01:2025-01-31", '["model1"]', "2025-01-01T00:00:00"))
    conn.commit()
    conn.close()

    # Verify data exists
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM jobs")
    assert cursor.fetchone()[0] == 1
    conn.close()

    # Initialize dev database (should reset)
    initialize_dev_database(db_path)

    # Verify data is cleared
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM jobs")
    assert cursor.fetchone()[0] == 0
    conn.close()


def test_cleanup_dev_database_removes_files(tmp_path):
    """Test dev cleanup removes database and data files"""
    # Setup dev files
    db_path = str(tmp_path / "test_dev.db")
    data_path = str(tmp_path / "dev_agent_data")

    Path(db_path).touch()
    Path(data_path).mkdir(parents=True, exist_ok=True)
    (Path(data_path) / "test_file.jsonl").touch()

    # Verify files exist
    assert Path(db_path).exists()
    assert Path(data_path).exists()

    # Cleanup
    cleanup_dev_database(db_path, data_path)

    # Verify files removed
    assert not Path(db_path).exists()
    assert not Path(data_path).exists()


def test_initialize_dev_respects_preserve_flag(tmp_path):
    """Test that PRESERVE_DEV_DATA flag prevents cleanup"""
    os.environ["PRESERVE_DEV_DATA"] = "true"
    db_path = str(tmp_path / "test_dev.db")

    # Create database with data
    from api.database import get_db_connection, initialize_database
    initialize_database(db_path)
    conn = get_db_connection(db_path)
    conn.execute("INSERT INTO jobs (job_id, config_path, status, date_range, models, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                 ("test-job", "config.json", "completed", "2025-01-01:2025-01-31", '["model1"]', "2025-01-01T00:00:00"))
    conn.commit()
    conn.close()

    # Initialize with preserve flag
    initialize_dev_database(db_path)

    # Verify data is preserved
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM jobs")
    assert cursor.fetchone()[0] == 1
    conn.close()

    os.environ.pop("PRESERVE_DEV_DATA")
