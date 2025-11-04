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
        5. trading_sessions - One record per model-day trading session
        6. reasoning_logs - AI decision logs linked to sessions
        7. tool_usage - Tool usage statistics
        8. price_data - Historical OHLCV price data (replaces merged.jsonl)
        9. price_data_coverage - Downloaded date range tracking per symbol
        10. simulation_runs - Simulation run tracking for soft delete

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

    # Table 5: Trading Sessions - One per model-day trading session
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trading_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            date TEXT NOT NULL,
            model TEXT NOT NULL,
            session_summary TEXT,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            total_messages INTEGER,
            FOREIGN KEY (job_id) REFERENCES jobs(job_id) ON DELETE CASCADE,
            UNIQUE(job_id, date, model)
        )
    """)

    # Table 6: Reasoning Logs - AI decision logs linked to sessions
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reasoning_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            message_index INTEGER NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'tool')),
            content TEXT NOT NULL,
            summary TEXT,
            tool_name TEXT,
            tool_input TEXT,
            timestamp TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES trading_sessions(id) ON DELETE CASCADE,
            UNIQUE(session_id, message_index)
        )
    """)

    # Table 7: Tool Usage - Tool usage statistics
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

    # Table 8: Price Data - OHLCV price data (replaces merged.jsonl)
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

    # Table 9: Price Data Coverage - Track downloaded date ranges per symbol
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

    # Table 10: Simulation Runs - Track simulation runs for soft delete
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
    from tools.deployment_config import should_preserve_dev_data

    if should_preserve_dev_data():
        print(f"ℹ️  PRESERVE_DEV_DATA=true, keeping existing dev database: {db_path}")
        # Ensure schema exists even if preserving data
        if not Path(db_path).exists():
            print(f"📁 Dev database doesn't exist, creating: {db_path}")
            initialize_database(db_path)
        return

    # Delete existing dev database
    if Path(db_path).exists():
        print(f"🗑️  Removing existing dev database: {db_path}")
        Path(db_path).unlink()

    # Create fresh dev database
    print(f"📁 Creating fresh dev database: {db_path}")
    initialize_database(db_path)


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
    # Check if positions table exists and add missing columns
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='positions'")
    if cursor.fetchone():
        cursor.execute("PRAGMA table_info(positions)")
        columns = [row[1] for row in cursor.fetchall()]

        if 'simulation_run_id' not in columns:
            cursor.execute("""
                ALTER TABLE positions ADD COLUMN simulation_run_id TEXT
            """)

        if 'session_id' not in columns:
            cursor.execute("""
                ALTER TABLE positions ADD COLUMN session_id INTEGER REFERENCES trading_sessions(id)
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

    # Trading sessions table indexes
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_sessions_job_id ON trading_sessions(job_id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_sessions_date ON trading_sessions(date)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_sessions_model ON trading_sessions(model)
    """)
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_sessions_unique
        ON trading_sessions(job_id, date, model)
    """)

    # Reasoning logs table indexes
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_reasoning_logs_session_id
        ON reasoning_logs(session_id)
    """)
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_reasoning_logs_unique
        ON reasoning_logs(session_id, message_index)
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

    # Positions table - add index for simulation_run_id and session_id
    # Check if columns exist before creating indexes
    cursor.execute("PRAGMA table_info(positions)")
    position_columns = [row[1] for row in cursor.fetchall()]

    if 'simulation_run_id' in position_columns:
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_positions_run_id ON positions(simulation_run_id)
        """)

    if 'session_id' in position_columns:
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_positions_session_id ON positions(session_id)
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
        'trading_sessions',
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
    tables = ['jobs', 'job_details', 'positions', 'holdings', 'trading_sessions', 'reasoning_logs',
              'tool_usage', 'price_data', 'price_data_coverage', 'simulation_runs']

    for table in tables:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        stats[table] = cursor.fetchone()[0]

    conn.close()

    return stats


class Database:
    """Database wrapper class with helper methods for trading_days schema."""

    def __init__(self, db_path: str = None):
        """Initialize database connection.

        Args:
            db_path: Path to SQLite database file.
                     If None, uses default from deployment config.
        """
        if db_path is None:
            from tools.deployment_config import get_db_path
            db_path = get_db_path("data/trading.db")

        self.db_path = db_path
        self.connection = sqlite3.connect(db_path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row

        # Auto-initialize schema if needed
        self._initialize_schema()

    def _initialize_schema(self):
        """Initialize database schema if tables don't exist."""
        import importlib.util
        import os

        # Check if trading_days table exists
        cursor = self.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='trading_days'"
        )

        if cursor.fetchone() is None:
            # Schema doesn't exist, create it
            # Import migration module using importlib (module name starts with number)
            migration_path = os.path.join(
                os.path.dirname(__file__),
                'migrations',
                '001_trading_days_schema.py'
            )
            spec = importlib.util.spec_from_file_location(
                "trading_days_schema",
                migration_path
            )
            migration_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(migration_module)
            migration_module.create_trading_days_schema(self)

    def create_trading_day(
        self,
        job_id: str,
        model: str,
        date: str,
        starting_cash: float,
        starting_portfolio_value: float,
        daily_profit: float,
        daily_return_pct: float,
        ending_cash: float,
        ending_portfolio_value: float,
        reasoning_summary: str = None,
        reasoning_full: str = None,
        total_actions: int = 0,
        session_duration_seconds: float = None,
        days_since_last_trading: int = 1
    ) -> int:
        """Create a new trading day record.

        Returns:
            trading_day_id
        """
        cursor = self.connection.execute(
            """
            INSERT INTO trading_days (
                job_id, model, date,
                starting_cash, starting_portfolio_value,
                daily_profit, daily_return_pct,
                ending_cash, ending_portfolio_value,
                reasoning_summary, reasoning_full,
                total_actions, session_duration_seconds,
                days_since_last_trading,
                completed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                job_id, model, date,
                starting_cash, starting_portfolio_value,
                daily_profit, daily_return_pct,
                ending_cash, ending_portfolio_value,
                reasoning_summary, reasoning_full,
                total_actions, session_duration_seconds,
                days_since_last_trading
            )
        )
        self.connection.commit()
        return cursor.lastrowid

    def get_previous_trading_day(
        self,
        job_id: str,
        model: str,
        current_date: str
    ) -> dict:
        """Get the most recent trading day before current_date.

        Handles weekends/holidays by finding actual previous trading day.

        Returns:
            dict with keys: id, date, ending_cash, ending_portfolio_value
            or None if no previous day exists
        """
        cursor = self.connection.execute(
            """
            SELECT id, date, ending_cash, ending_portfolio_value
            FROM trading_days
            WHERE job_id = ? AND model = ? AND date < ?
            ORDER BY date DESC
            LIMIT 1
            """,
            (job_id, model, current_date)
        )

        row = cursor.fetchone()
        if row:
            return {
                "id": row[0],
                "date": row[1],
                "ending_cash": row[2],
                "ending_portfolio_value": row[3]
            }
        return None

    def get_ending_holdings(self, trading_day_id: int) -> list:
        """Get ending holdings for a trading day.

        Returns:
            List of dicts with keys: symbol, quantity
        """
        cursor = self.connection.execute(
            """
            SELECT symbol, quantity
            FROM holdings
            WHERE trading_day_id = ?
            ORDER BY symbol
            """,
            (trading_day_id,)
        )

        return [{"symbol": row[0], "quantity": row[1]} for row in cursor.fetchall()]

    def get_starting_holdings(self, trading_day_id: int) -> list:
        """Get starting holdings from previous day's ending holdings.

        Returns:
            List of dicts with keys: symbol, quantity
            Empty list if first trading day
        """
        # Get previous trading day
        cursor = self.connection.execute(
            """
            SELECT td_prev.id
            FROM trading_days td_current
            JOIN trading_days td_prev ON
                td_prev.job_id = td_current.job_id AND
                td_prev.model = td_current.model AND
                td_prev.date < td_current.date
            WHERE td_current.id = ?
            ORDER BY td_prev.date DESC
            LIMIT 1
            """,
            (trading_day_id,)
        )

        row = cursor.fetchone()
        if not row:
            # First trading day - no previous holdings
            return []

        previous_day_id = row[0]

        # Get previous day's ending holdings
        return self.get_ending_holdings(previous_day_id)

    def create_holding(
        self,
        trading_day_id: int,
        symbol: str,
        quantity: int
    ) -> int:
        """Create a holding record.

        Returns:
            holding_id
        """
        cursor = self.connection.execute(
            """
            INSERT INTO holdings (trading_day_id, symbol, quantity)
            VALUES (?, ?, ?)
            """,
            (trading_day_id, symbol, quantity)
        )
        self.connection.commit()
        return cursor.lastrowid

    def create_action(
        self,
        trading_day_id: int,
        action_type: str,
        symbol: str = None,
        quantity: int = None,
        price: float = None
    ) -> int:
        """Create an action record.

        Returns:
            action_id
        """
        cursor = self.connection.execute(
            """
            INSERT INTO actions (trading_day_id, action_type, symbol, quantity, price)
            VALUES (?, ?, ?, ?, ?)
            """,
            (trading_day_id, action_type, symbol, quantity, price)
        )
        self.connection.commit()
        return cursor.lastrowid

    def get_actions(self, trading_day_id: int) -> list:
        """Get all actions for a trading day.

        Returns:
            List of dicts with keys: action_type, symbol, quantity, price, created_at
        """
        cursor = self.connection.execute(
            """
            SELECT action_type, symbol, quantity, price, created_at
            FROM actions
            WHERE trading_day_id = ?
            ORDER BY created_at
            """,
            (trading_day_id,)
        )

        return [
            {
                "action_type": row[0],
                "symbol": row[1],
                "quantity": row[2],
                "price": row[3],
                "created_at": row[4]
            }
            for row in cursor.fetchall()
        ]
