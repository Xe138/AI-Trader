#!/usr/bin/env python3
"""
Script to convert database connection usage to context managers.

Converts patterns like:
    conn = get_db_connection(path)
    # code
    conn.close()

To:
    with db_connection(path) as conn:
        # code
"""

import re
import sys
from pathlib import Path


def fix_test_file(filepath):
    """Convert get_db_connection to db_connection context manager."""
    print(f"Processing: {filepath}")

    with open(filepath, 'r') as f:
        content = f.read()

    original_content = content

    # Step 1: Add db_connection to imports if needed
    if 'from api.database import' in content and 'db_connection' not in content:
        # Find the import statement
        import_pattern = r'(from api\.database import \([\s\S]*?\))'
        match = re.search(import_pattern, content)

        if match:
            old_import = match.group(1)
            # Add db_connection after get_db_connection
            new_import = old_import.replace(
                'get_db_connection,',
                'get_db_connection,\n    db_connection,'
            )
            content = content.replace(old_import, new_import)
            print("  ✓ Added db_connection to imports")

    # Step 2: Convert simple patterns (conn = get_db_connection ... conn.close())
    # This is a simplified version - manual review still needed
    content = content.replace(
        'conn = get_db_connection(',
        'with db_connection('
    )
    content = content.replace(
        ') as conn:',
        ') as conn:'  # No-op to preserve existing context managers
    )

    # Note: We still need manual fixes for:
    # 1. Adding proper indentation
    # 2. Removing conn.close() statements
    # 3. Handling cursor patterns

    if content != original_content:
        with open(filepath, 'w') as f:
            f.write(content)
        print(f"  ✓ Updated {filepath}")
        return True
    else:
        print(f"  - No changes needed for {filepath}")
        return False


def main():
    test_dir = Path(__file__).parent.parent / 'tests'

    # List of test files to update
    test_files = [
        'unit/test_database.py',
        'unit/test_job_manager.py',
        'unit/test_database_helpers.py',
        'unit/test_price_data_manager.py',
        'unit/test_model_day_executor.py',
        'unit/test_trade_tools_new_schema.py',
        'unit/test_get_position_new_schema.py',
        'unit/test_cross_job_position_continuity.py',
        'unit/test_job_manager_duplicate_detection.py',
        'unit/test_dev_database.py',
        'unit/test_database_schema.py',
        'unit/test_model_day_executor_reasoning.py',
        'integration/test_duplicate_simulation_prevention.py',
        'integration/test_dev_mode_e2e.py',
        'integration/test_on_demand_downloads.py',
        'e2e/test_full_simulation_workflow.py',
    ]

    updated_count = 0
    for test_file in test_files:
        filepath = test_dir / test_file
        if filepath.exists():
            if fix_test_file(filepath):
                updated_count += 1
        else:
            print(f"  ⚠ File not found: {filepath}")

    print(f"\n✓ Updated {updated_count} files")
    print("⚠ Manual review required - check indentation and remove conn.close() calls")


if __name__ == '__main__':
    main()
