"""Migration: Create trading_days, holdings, and actions tables."""

import sqlite3
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from api.database import Database


def create_trading_days_schema(db: "Database") -> None:
    """Create new schema for day-centric trading results.

    Args:
        db: Database instance to apply migration to
    """
    # Enable foreign key constraint enforcement
    db.connection.execute("PRAGMA foreign_keys = ON")

    # Create jobs table if it doesn't exist (prerequisite for foreign key)
    db.connection.execute("""
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

    # Create trading_days table
    db.connection.execute("""
        CREATE TABLE IF NOT EXISTS trading_days (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            model TEXT NOT NULL,
            date TEXT NOT NULL,

            -- Starting position (cash only, holdings from previous day)
            starting_cash REAL NOT NULL,
            starting_portfolio_value REAL NOT NULL,

            -- Daily performance metrics
            daily_profit REAL NOT NULL,
            daily_return_pct REAL NOT NULL,

            -- Ending state (cash only, holdings in separate table)
            ending_cash REAL NOT NULL,
            ending_portfolio_value REAL NOT NULL,

            -- Reasoning
            reasoning_summary TEXT,
            reasoning_full TEXT,

            -- Metadata
            total_actions INTEGER DEFAULT 0,
            session_duration_seconds REAL,
            days_since_last_trading INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,

            UNIQUE(job_id, model, date),
            FOREIGN KEY (job_id) REFERENCES jobs(job_id)
        )
    """)

    # Create index for lookups
    db.connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_trading_days_lookup
        ON trading_days(job_id, model, date)
    """)

    # Create holdings table (ending positions only)
    db.connection.execute("""
        CREATE TABLE IF NOT EXISTS holdings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trading_day_id INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            quantity INTEGER NOT NULL,

            FOREIGN KEY (trading_day_id) REFERENCES trading_days(id) ON DELETE CASCADE,
            UNIQUE(trading_day_id, symbol)
        )
    """)

    # Create index for holdings lookups
    db.connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_holdings_day
        ON holdings(trading_day_id)
    """)

    # Create actions table (trade ledger)
    db.connection.execute("""
        CREATE TABLE IF NOT EXISTS actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trading_day_id INTEGER NOT NULL,

            action_type TEXT NOT NULL,
            symbol TEXT,
            quantity INTEGER,
            price REAL,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (trading_day_id) REFERENCES trading_days(id) ON DELETE CASCADE
        )
    """)

    # Create index for actions lookups
    db.connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_actions_day
        ON actions(trading_day_id)
    """)

    db.connection.commit()


def drop_old_positions_table(db: "Database") -> None:
    """Drop deprecated positions table after migration complete.

    Args:
        db: Database instance
    """
    db.connection.execute("DROP TABLE IF EXISTS positions")
    db.connection.commit()
