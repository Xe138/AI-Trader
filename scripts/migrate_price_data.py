#!/usr/bin/env python3
"""
Migration script: Import merged.jsonl price data into SQLite database.

This script:
1. Reads existing merged.jsonl file
2. Parses OHLCV data for each symbol/date
3. Inserts into price_data table
4. Tracks coverage in price_data_coverage table

Run this once to migrate from jsonl to database.
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from api.database import get_db_connection, initialize_database


def migrate_merged_jsonl(
    jsonl_path: str = "data/merged.jsonl",
    db_path: str = "data/jobs.db"
):
    """
    Migrate price data from merged.jsonl to SQLite database.

    Args:
        jsonl_path: Path to merged.jsonl file
        db_path: Path to SQLite database
    """
    jsonl_file = Path(jsonl_path)

    if not jsonl_file.exists():
        print(f"⚠️  merged.jsonl not found at {jsonl_path}")
        print("   No price data to migrate. Skipping migration.")
        return

    print(f"📊 Migrating price data from {jsonl_path} to {db_path}")

    # Ensure database is initialized
    initialize_database(db_path)

    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    # Track what we're importing
    total_records = 0
    symbols_processed = set()
    symbol_date_ranges = defaultdict(lambda: {"min": None, "max": None})

    created_at = datetime.utcnow().isoformat() + "Z"

    print("Reading merged.jsonl...")

    with open(jsonl_file, 'r') as f:
        for line_num, line in enumerate(f, 1):
            if not line.strip():
                continue

            try:
                record = json.loads(line)

                # Extract metadata
                meta = record.get("Meta Data", {})
                symbol = meta.get("2. Symbol")

                if not symbol:
                    print(f"⚠️  Line {line_num}: No symbol found, skipping")
                    continue

                symbols_processed.add(symbol)

                # Extract time series data
                time_series = record.get("Time Series (Daily)", {})

                if not time_series:
                    print(f"⚠️  {symbol}: No time series data, skipping")
                    continue

                # Insert each date's data
                for date, ohlcv in time_series.items():
                    try:
                        # Parse OHLCV values
                        open_price = float(ohlcv.get("1. buy price") or ohlcv.get("1. open", 0))
                        high_price = float(ohlcv.get("2. high", 0))
                        low_price = float(ohlcv.get("3. low", 0))
                        close_price = float(ohlcv.get("4. sell price") or ohlcv.get("4. close", 0))
                        volume = int(ohlcv.get("5. volume", 0))

                        # Insert or replace price data
                        cursor.execute("""
                            INSERT OR REPLACE INTO price_data
                            (symbol, date, open, high, low, close, volume, created_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """, (symbol, date, open_price, high_price, low_price, close_price, volume, created_at))

                        total_records += 1

                        # Track date range for this symbol
                        if symbol_date_ranges[symbol]["min"] is None or date < symbol_date_ranges[symbol]["min"]:
                            symbol_date_ranges[symbol]["min"] = date
                        if symbol_date_ranges[symbol]["max"] is None or date > symbol_date_ranges[symbol]["max"]:
                            symbol_date_ranges[symbol]["max"] = date

                    except (ValueError, KeyError) as e:
                        print(f"⚠️  {symbol} {date}: Failed to parse OHLCV data: {e}")
                        continue

                # Commit every 1000 records for progress
                if total_records % 1000 == 0:
                    conn.commit()
                    print(f"   Imported {total_records} records...")

            except json.JSONDecodeError as e:
                print(f"⚠️  Line {line_num}: JSON decode error: {e}")
                continue

    # Final commit
    conn.commit()

    print(f"\n✓ Imported {total_records} price records for {len(symbols_processed)} symbols")

    # Update coverage tracking
    print("\nUpdating coverage tracking...")

    for symbol, date_range in symbol_date_ranges.items():
        if date_range["min"] and date_range["max"]:
            cursor.execute("""
                INSERT OR REPLACE INTO price_data_coverage
                (symbol, start_date, end_date, downloaded_at, source)
                VALUES (?, ?, ?, ?, 'migrated_from_jsonl')
            """, (symbol, date_range["min"], date_range["max"], created_at))

    conn.commit()
    conn.close()

    print(f"✓ Coverage tracking updated for {len(symbol_date_ranges)} symbols")
    print("\n✅ Migration complete!")
    print(f"\nSymbols migrated: {', '.join(sorted(symbols_processed))}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Migrate merged.jsonl to SQLite database")
    parser.add_argument(
        "--jsonl",
        default="data/merged.jsonl",
        help="Path to merged.jsonl file (default: data/merged.jsonl)"
    )
    parser.add_argument(
        "--db",
        default="data/jobs.db",
        help="Path to SQLite database (default: data/jobs.db)"
    )

    args = parser.parse_args()

    migrate_merged_jsonl(args.jsonl, args.db)
