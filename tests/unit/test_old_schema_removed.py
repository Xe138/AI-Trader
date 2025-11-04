"""Verify old schema tables are removed."""

import pytest
from api.database import Database


def test_old_tables_do_not_exist():
    """Verify trading_sessions, old positions, reasoning_logs don't exist."""

    db = Database(":memory:")

    # Query sqlite_master for old tables
    cursor = db.connection.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name IN (
            'trading_sessions', 'reasoning_logs'
        )
    """)

    tables = cursor.fetchall()

    assert len(tables) == 0, f"Old tables should not exist, found: {tables}"


def test_new_tables_exist():
    """Verify new schema tables exist."""

    db = Database(":memory:")

    cursor = db.connection.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name IN (
            'trading_days', 'holdings', 'actions'
        )
        ORDER BY name
    """)

    tables = [row[0] for row in cursor.fetchall()]

    assert 'trading_days' in tables
    assert 'holdings' in tables
    assert 'actions' in tables
