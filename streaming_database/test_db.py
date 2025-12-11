#!/usr/bin/env python3
"""Test SQLite database connection and streaming domain seed data.

This script is a lightweight health check for the streaming_database container.
It will:

- Ensure the database has been initialized (calling init_db.py if needed).
- Read the SQLite database path from db_connection.txt.
- Connect to the database and print the SQLite version.
- Assert that required tables exist: users, categories, videos,
  video_categories, watch_history, and app_info.
- Assert that demo seed data exists: at least one user (demo_user), several
  categories, 8+ videos, and some watch_history rows.

Exit code 0 means all checks passed; any failure results in a non-zero exit.
"""

import os
import sqlite3
import subprocess
import sys
from typing import List

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONNECTION_FILE = os.path.join(BASE_DIR, "db_connection.txt")
INIT_SCRIPT = os.path.join(BASE_DIR, "init_db.py")


def _run_init_db() -> None:
    """Run the database initialization script if needed."""
    if not os.path.exists(INIT_SCRIPT):
        raise FileNotFoundError(f"init_db.py not found at {INIT_SCRIPT}")

    print("Database not fully initialized; running init_db.py ...")
    result = subprocess.run(
        [sys.executable, INIT_SCRIPT],
        cwd=BASE_DIR,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"init_db.py failed with exit code {result.returncode}")


def _get_db_path_from_connection_file() -> str:
    """Parse db_connection.txt to extract the absolute SQLite database file path."""
    if not os.path.exists(CONNECTION_FILE):
        print("db_connection.txt not found; attempting to initialize database.")
        _run_init_db()

    if not os.path.exists(CONNECTION_FILE):
        raise FileNotFoundError("db_connection.txt is still missing after initialization.")

    db_path: str | None = None
    connection_string: str | None = None

    with open(CONNECTION_FILE, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped.startswith("# File path:"):
                db_path = stripped.split(":", 1)[1].strip()
            elif stripped.startswith("# Connection string:"):
                connection_string = stripped.split(":", 1)[1].strip()

    if not db_path and connection_string and connection_string.startswith("sqlite:///"):
        # Fall back to parsing the SQLite URL if needed
        db_path = connection_string[len("sqlite:///") :]

    if not db_path:
        raise RuntimeError(
            "Unable to determine database path from db_connection.txt. "
            "Expected a line starting with '# File path:'."
        )

    return os.path.abspath(db_path)


def _assert_tables_exist(cursor: sqlite3.Cursor, required_tables: List[str]) -> None:
    """Ensure that all required tables are present in the SQLite database."""
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )
    existing = {row[0] for row in cursor.fetchall()}
    missing = [t for t in required_tables if t not in existing]
    if missing:
        raise AssertionError(f"Missing required tables: {', '.join(missing)}")


def _assert_seed_data(cursor: sqlite3.Cursor) -> None:
    """Ensure that core seed data is present in the database."""
    # At least one user and specifically demo_user with a non-empty password_hash
    cursor.execute("SELECT COUNT(*) FROM users")
    user_count = cursor.fetchone()[0]
    if user_count < 1:
        raise AssertionError("Expected at least one user in the users table.")

    cursor.execute(
        "SELECT COUNT(*) FROM users WHERE username = 'demo_user' AND password_hash IS NOT NULL AND LENGTH(password_hash) > 0"
    )
    demo_user_rows = cursor.fetchone()[0]
    if demo_user_rows < 1:
        raise AssertionError(
            "Expected a seeded demo user with a hashed password (username 'demo_user')."
        )

    # Several categories
    cursor.execute("SELECT COUNT(*) FROM categories")
    category_count = cursor.fetchone()[0]
    if category_count < 3:
        raise AssertionError(
            f"Expected several categories, found {category_count}."
        )

    # 8–12 videos seeded
    cursor.execute("SELECT COUNT(*) FROM videos")
    video_count = cursor.fetchone()[0]
    if video_count < 8:
        raise AssertionError(
            f"Expected at least 8 seeded videos, found {video_count}."
        )

    # Some watch_history rows for demo_user
    cursor.execute(
        "SELECT id FROM users WHERE username = 'demo_user'"
    )
    demo_row = cursor.fetchone()
    if not demo_row:
        raise AssertionError("demo_user not found when checking watch_history.")
    demo_user_id = int(demo_row[0])

    cursor.execute(
        "SELECT COUNT(*) FROM watch_history WHERE user_id = ?",
        (demo_user_id,),
    )
    history_count = cursor.fetchone()[0]
    if history_count < 1:
        raise AssertionError(
            "Expected at least one watch_history row for demo_user."
        )


# PUBLIC_INTERFACE
def main() -> int:
    """Entry point for the database health check script.

    Returns:
        int: Process exit code (0 for success, non-zero for failure).
    """
    try:
        db_path = _get_db_path_from_connection_file()

        # If the database file itself is missing, try initialization once
        if not os.path.exists(db_path):
            print(f"Database file '{db_path}' not found; attempting to initialize.")
            _run_init_db()
            db_path = _get_db_path_from_connection_file()
            if not os.path.exists(db_path):
                print(f"Database file '{db_path}' is still missing after initialization.")
                return 1

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Report SQLite version (preserves original behavior)
        cursor.execute("SELECT sqlite_version()")
        version = cursor.fetchone()[0]
        print(f"SQLite version: {version}")

        # Validate schema
        required_tables = [
            "users",
            "categories",
            "videos",
            "video_categories",
            "watch_history",
            "app_info",
        ]
        _assert_tables_exist(cursor, required_tables)

        # Validate seed data presence
        _assert_seed_data(cursor)

        conn.close()
        print("All database checks passed successfully.")
        return 0

    except (sqlite3.Error, FileNotFoundError, RuntimeError, AssertionError) as exc:
        print(f"Database check failed: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
