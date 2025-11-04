"""Drop old schema tables (trading_sessions, positions, reasoning_logs)."""


def drop_old_schema(db):
    """
    Drop old schema tables that have been replaced by new schema.

    Old schema:
    - trading_sessions → replaced by trading_days
    - positions (action-centric) → replaced by trading_days + actions + holdings
    - reasoning_logs → replaced by trading_days.reasoning_full

    Args:
        db: Database instance
    """

    # Drop reasoning_logs (child table first)
    db.connection.execute("DROP TABLE IF EXISTS reasoning_logs")

    # Drop positions (note: this is the OLD action-centric positions table)
    # The new schema doesn't have a positions table at all
    db.connection.execute("DROP TABLE IF EXISTS positions")

    # Drop trading_sessions
    db.connection.execute("DROP TABLE IF EXISTS trading_sessions")

    db.connection.commit()

    print("✅ Dropped old schema tables: trading_sessions, positions, reasoning_logs")


if __name__ == "__main__":
    """Run migration standalone."""
    from api.database import Database
    from tools.deployment_config import get_db_path

    db_path = get_db_path("data/trading.db")
    db = Database(db_path)

    drop_old_schema(db)

    print(f"✅ Migration complete: {db_path}")
