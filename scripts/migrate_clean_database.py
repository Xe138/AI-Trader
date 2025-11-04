#!/usr/bin/env python3
"""
Clean database migration script.

Drops old positions table and creates fresh trading_days schema.
WARNING: This deletes all existing position data.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.database import Database
import importlib.util
import sys

# Import migration module using importlib to handle numeric prefix
spec = importlib.util.spec_from_file_location(
    "trading_days_schema",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "api", "migrations", "001_trading_days_schema.py")
)
trading_days_schema = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trading_days_schema)
drop_old_positions_table = trading_days_schema.drop_old_positions_table


def migrate_clean_database():
    """Drop old schema and create clean new schema."""
    print("Starting clean database migration...")

    db = Database()

    # Drop old positions table
    print("Dropping old positions table...")
    drop_old_positions_table(db)

    # New schema already created by Database.__init__()
    print("New trading_days schema created successfully")

    # Verify new tables exist
    cursor = db.connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [row[0] for row in cursor.fetchall()]

    print(f"\nCurrent tables: {', '.join(tables)}")

    # Verify positions table is gone
    if 'positions' in tables:
        print("WARNING: positions table still exists!")
        return False

    # Verify new tables exist
    required_tables = ['trading_days', 'holdings', 'actions']
    for table in required_tables:
        if table not in tables:
            print(f"ERROR: Required table '{table}' not found!")
            return False

    print("\nMigration completed successfully!")
    return True


if __name__ == "__main__":
    success = migrate_clean_database()
    sys.exit(0 if success else 1)
