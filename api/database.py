"""
Database utilities and schema management for AI-Trader API.

This module provides:
- SQLite connection management
- Database schema initialization (6 tables)
- ACID-compliant transaction support
"""

import sqlite3
from pathlib import Path
import os
from tools.deployment_config import get_db_path


def get_db_connection(db_path: str = "data/jobs.db") -> sqlite3.Connection:
    """
    Get SQLite database connection with proper configuration.

    Automatically resolves to dev database if DEPLOYMENT_MODE=DEV.

    Args:
        db_path: Path to SQLite database file

    Returns:
        Configured SQLite connection

    Configuration:
        - Foreign keys enabled for referential integrity
        - Row factory for dict-like access
        - Check same thread disabled for FastAPI async compatibility
    """
    # Resolve path based on deployment mode
    resolved_path = get_db_path(db_path)

    # Ensure data directory exists
    db_path_obj = Path(resolved_path)
    db_path_obj.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(resolved_path, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row

    return conn


def resolve_db_path(db_path: str) -> str:
    """
    Resolve database path based on deployment mode

    Convenience function for testing.

    Args:
        db_path: Base database path

    Returns:
        Resolved path (dev or prod)
    """
    return get_db_path(db_path)


def initialize_database(db_path: str = "data/jobs.db") -> None:
    """
    Create all database tables with enhanced schema.

    Tables created:
        1. jobs - High-level job metadata and status
        2. job_details - Per model-day execution tracking
        3. positions - Trading positions and P&L metrics
        4. holdings - Portfolio holdings per position
        5. reasoning_logs - AI decision logs (optional, for detail=full)
        6. tool_usage - Tool usage statistics
        7. price_data - Historical OHLCV price data (replaces merged.jsonl)
        8. price_data_coverage - Downloaded date range tracking per symbol
        9. simulation_runs - Simulation run tracking for soft delete

    Args:
        db_path: Path to SQLite database file
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    # Table 1: Jobs - Job metadata and lifecycle
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
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
            error TEXT,
            warnings TEXT
        )
    """)

    # Table 2: Job Details - Per model-day execution
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS job_details (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            date TEXT NOT NULL,
            model TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('pending', 'running', 'completed', 'failed', 'skipped')),
            started_at TEXT,
            completed_at TEXT,
            duration_seconds REAL,
            error TEXT,
            FOREIGN KEY (job_id) REFERENCES jobs(job_id) ON DELETE CASCADE
        )
    """)

    # Table 3: Positions - Trading positions and P&L
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            date TEXT NOT NULL,
            model TEXT NOT NULL,
            action_id INTEGER NOT NULL,
            action_type TEXT CHECK(action_type IN ('buy', 'sell', 'no_trade')),
            symbol TEXT,
            amount INTEGER,
            price REAL,
            cash REAL NOT NULL,
            portfolio_value REAL NOT NULL,
            daily_profit REAL,
            daily_return_pct REAL,
            cumulative_profit REAL,
            cumulative_return_pct REAL,
            simulation_run_id TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (job_id) REFERENCES jobs(job_id) ON DELETE CASCADE,
            FOREIGN KEY (simulation_run_id) REFERENCES simulation_runs(run_id) ON DELETE SET NULL
        )
    """)

    # Table 4: Holdings - Portfolio holdings
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS holdings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            position_id INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            FOREIGN KEY (position_id) REFERENCES positions(id) ON DELETE CASCADE
        )
    """)

    # Table 5: Reasoning Logs - AI decision logs (optional)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reasoning_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            date TEXT NOT NULL,
            model TEXT NOT NULL,
            step_number INTEGER NOT NULL,
            timestamp TEXT NOT NULL,
            role TEXT CHECK(role IN ('user', 'assistant', 'tool')),
            content TEXT,
            tool_name TEXT,
            FOREIGN KEY (job_id) REFERENCES jobs(job_id) ON DELETE CASCADE
        )
    """)

    # Table 6: Tool Usage - Tool usage statistics
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tool_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            date TEXT NOT NULL,
            model TEXT NOT NULL,
            tool_name TEXT NOT NULL,
            call_count INTEGER NOT NULL DEFAULT 1,
            total_duration_seconds REAL,
            FOREIGN KEY (job_id) REFERENCES jobs(job_id) ON DELETE CASCADE
        )
    """)

    # Table 7: Price Data - OHLCV price data (replaces merged.jsonl)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS price_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            date TEXT NOT NULL,
            open REAL NOT NULL,
            high REAL NOT NULL,
            low REAL NOT NULL,
            close REAL NOT NULL,
            volume INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(symbol, date)
        )
    """)

    # Table 8: Price Data Coverage - Track downloaded date ranges per symbol
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS price_data_coverage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            downloaded_at TEXT NOT NULL,
            source TEXT DEFAULT 'alpha_vantage',
            UNIQUE(symbol, start_date, end_date)
        )
    """)

    # Table 9: Simulation Runs - Track simulation runs for soft delete
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS simulation_runs (
            run_id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL,
            model TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('active', 'superseded')),
            created_at TEXT NOT NULL,
            superseded_at TEXT,
            FOREIGN KEY (job_id) REFERENCES jobs(job_id) ON DELETE CASCADE
        )
    """)

    # Run schema migrations for existing databases
    _migrate_schema(cursor)

    # Create indexes for performance
    _create_indexes(cursor)

    conn.commit()
    conn.close()


def initialize_dev_database(db_path: str = "data/trading_dev.db") -> None:
    """
    Initialize dev database with clean schema

    Deletes and recreates dev database unless PRESERVE_DEV_DATA=true.
    Used at startup in DEV mode to ensure clean testing environment.

    Args:
        db_path: Path to dev database file
    """
    print(f"🔍 DIAGNOSTIC: initialize_dev_database() CALLED with db_path={db_path}")
    from tools.deployment_config import should_preserve_dev_data

    preserve = should_preserve_dev_data()
    print(f"🔍 DIAGNOSTIC: should_preserve_dev_data() returned: {preserve}")

    if preserve:
        print(f"ℹ️  PRESERVE_DEV_DATA=true, keeping existing dev database: {db_path}")
        # Ensure schema exists even if preserving data
        db_exists = Path(db_path).exists()
        print(f"🔍 DIAGNOSTIC: Database exists check: {db_exists}")
        if not db_exists:
            print(f"📁 Dev database doesn't exist, creating: {db_path}")
            initialize_database(db_path)
        print(f"🔍 DIAGNOSTIC: initialize_dev_database() RETURNING (preserve mode)")
        return

    # Delete existing dev database
    db_exists = Path(db_path).exists()
    print(f"🔍 DIAGNOSTIC: Database exists (before deletion): {db_exists}")
    if db_exists:
        print(f"🗑️  Removing existing dev database: {db_path}")
        Path(db_path).unlink()
        print(f"🔍 DIAGNOSTIC: Database deleted successfully")

    # Create fresh dev database
    print(f"📁 Creating fresh dev database: {db_path}")
    initialize_database(db_path)
    print(f"🔍 DIAGNOSTIC: initialize_dev_database() COMPLETED successfully")


def cleanup_dev_database(db_path: str = "data/trading_dev.db", data_path: str = "./data/dev_agent_data") -> None:
    """
    Cleanup dev database and data files

    Args:
        db_path: Path to dev database file
        data_path: Path to dev data directory
    """
    import shutil

    # Remove dev database
    if Path(db_path).exists():
        print(f"🗑️  Removing dev database: {db_path}")
        Path(db_path).unlink()

    # Remove dev data directory
    if Path(data_path).exists():
        print(f"🗑️  Removing dev data directory: {data_path}")
        shutil.rmtree(data_path)


def _migrate_schema(cursor: sqlite3.Cursor) -> None:
    """
    Migrate existing database schema to latest version.

    Note: For pre-production databases, simply delete and recreate.
    This migration is only for preserving data during development.
    """
    # Check if positions table exists and has simulation_run_id column
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='positions'")
    if cursor.fetchone():
        cursor.execute("PRAGMA table_info(positions)")
        columns = [row[1] for row in cursor.fetchall()]

        if 'simulation_run_id' not in columns:
            cursor.execute("""
                ALTER TABLE positions ADD COLUMN simulation_run_id TEXT
            """)


def _create_indexes(cursor: sqlite3.Cursor) -> None:
    """Create database indexes for query performance."""

    # Jobs table indexes
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at DESC)
    """)

    # Job details table indexes
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_job_details_job_id ON job_details(job_id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_job_details_status ON job_details(status)
    """)
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_job_details_unique
        ON job_details(job_id, date, model)
    """)

    # Positions table indexes
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_positions_job_id ON positions(job_id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_positions_date ON positions(date)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_positions_model ON positions(model)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_positions_date_model ON positions(date, model)
    """)
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_positions_unique
        ON positions(job_id, date, model, action_id)
    """)

    # Holdings table indexes
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_holdings_position_id ON holdings(position_id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_holdings_symbol ON holdings(symbol)
    """)

    # Reasoning logs table indexes
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_reasoning_logs_job_date_model
        ON reasoning_logs(job_id, date, model)
    """)

    # Tool usage table indexes
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_tool_usage_job_date_model
        ON tool_usage(job_id, date, model)
    """)

    # Price data table indexes
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_price_data_symbol_date ON price_data(symbol, date)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_price_data_date ON price_data(date)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_price_data_symbol ON price_data(symbol)
    """)

    # Price data coverage table indexes
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_coverage_symbol ON price_data_coverage(symbol)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_coverage_dates ON price_data_coverage(start_date, end_date)
    """)

    # Simulation runs table indexes
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_runs_job_model ON simulation_runs(job_id, model)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_runs_status ON simulation_runs(status)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_runs_dates ON simulation_runs(start_date, end_date)
    """)

    # Positions table - add index for simulation_run_id
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_positions_run_id ON positions(simulation_run_id)
    """)


def drop_all_tables(db_path: str = "data/jobs.db") -> None:
    """
    Drop all database tables. USE WITH CAUTION.

    This is primarily for testing and development.

    Args:
        db_path: Path to SQLite database file
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    tables = [
        'tool_usage',
        'reasoning_logs',
        'holdings',
        'positions',
        'simulation_runs',
        'job_details',
        'jobs',
        'price_data_coverage',
        'price_data'
    ]

    for table in tables:
        cursor.execute(f"DROP TABLE IF EXISTS {table}")

    conn.commit()
    conn.close()


def vacuum_database(db_path: str = "data/jobs.db") -> None:
    """
    Reclaim disk space after deletions.

    Should be run periodically after cleanup operations.

    Args:
        db_path: Path to SQLite database file
    """
    conn = get_db_connection(db_path)
    conn.execute("VACUUM")
    conn.close()


def get_database_stats(db_path: str = "data/jobs.db") -> dict:
    """
    Get database statistics for monitoring.

    Returns:
        Dictionary with table row counts and database size

    Example:
        {
            "database_size_mb": 12.5,
            "jobs": 150,
            "job_details": 3000,
            "positions": 15000,
            "holdings": 45000,
            "reasoning_logs": 300000,
            "tool_usage": 12000
        }
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    stats = {}

    # Get database file size
    if os.path.exists(db_path):
        size_bytes = os.path.getsize(db_path)
        stats["database_size_mb"] = round(size_bytes / (1024 * 1024), 2)
    else:
        stats["database_size_mb"] = 0

    # Get row counts for each table
    tables = ['jobs', 'job_details', 'positions', 'holdings', 'reasoning_logs', 'tool_usage',
              'price_data', 'price_data_coverage', 'simulation_runs']

    for table in tables:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        stats[table] = cursor.fetchone()[0]

    conn.close()

    return stats
