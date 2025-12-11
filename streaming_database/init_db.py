#!/usr/bin/env python3
"""Initialize SQLite database for streaming_database.

This script creates or upgrades the SQLite database schema for the streaming
domain and seeds demo data in an idempotent way. It is safe to run multiple
times: schema migrations are additive and seed data is inserted/updated
without creating duplicates.

The schema is intentionally simple and uses types that are easy to migrate
to PostgreSQL later (INTEGER, TEXT, TIMESTAMP).
"""

import hashlib
import os
import sqlite3
from typing import Dict


# Default values kept for consistency with other tooling (backup/restore scripts)
DB_USER = "kaviasqlite"  # Not used for SQLite, but kept for consistency
DB_PASSWORD = "kaviadefaultpassword"  # Not used for SQLite, but kept for consistency
DB_PORT = "5000"  # Not used for SQLite, but kept for consistency

# Determine database path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB_FILENAME = "myapp.db"

# Allow overriding the DB path via environment variable for future portability
env_db_path = os.getenv("SQLITE_DB")
if env_db_path:
    DB_PATH = os.path.abspath(env_db_path)
else:
    DB_PATH = os.path.join(BASE_DIR, DEFAULT_DB_FILENAME)


def _ensure_column(cursor: sqlite3.Cursor, table: str, column_def: str) -> None:
    """Ensure that a column exists on a table, adding it if missing.

    This is used to perform simple, additive schema migrations on existing
    SQLite databases without dropping data.
    """
    column_name = column_def.split()[0]
    cursor.execute(f"PRAGMA table_info({table})")
    existing_columns = [row[1] for row in cursor.fetchall()]
    if column_name not in existing_columns:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column_def}")


def _create_schema(cursor: sqlite3.Cursor) -> None:
    """Create all tables required for the streaming domain if they do not exist."""
    # app_info: generic key-value metadata about the application/database
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS app_info (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            value TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # users: end users of the streaming platform
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT,
            full_name TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    # Migrate older databases that may not have these newer columns
    _ensure_column(cursor, "users", "password_hash TEXT")
    _ensure_column(cursor, "users", "full_name TEXT")
    _ensure_column(cursor, "users", "is_active INTEGER NOT NULL DEFAULT 1")

    # categories: video genres/categories (e.g., Action, Drama)
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # videos: metadata about each video asset
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            slug TEXT UNIQUE NOT NULL,
            video_url TEXT NOT NULL,
            thumbnail_url TEXT,
            duration_seconds INTEGER,
            is_published INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # video_categories: many-to-many join between videos and categories
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS video_categories (
            video_id INTEGER NOT NULL,
            category_id INTEGER NOT NULL,
            PRIMARY KEY (video_id, category_id),
            FOREIGN KEY (video_id) REFERENCES videos(id) ON DELETE CASCADE,
            FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE
        )
        """
    )

    # watch_history: last watch state per user/video pair
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS watch_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            video_id INTEGER NOT NULL,
            progress_seconds INTEGER NOT NULL DEFAULT 0,
            completed INTEGER NOT NULL DEFAULT 0,
            last_watched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, video_id),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (video_id) REFERENCES videos(id) ON DELETE CASCADE
        )
        """
    )

    # Useful indexes for lookup performance
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_videos_slug ON videos(slug)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_watch_history_user_id ON watch_history(user_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_watch_history_video_id ON watch_history(video_id)"
    )


def _hash_password(password: str) -> str:
    """Hash a plain-text password for demo purposes.

    NOTE: This uses a simple SHA-256 hash and is NOT suitable for production
    authentication. The FastAPI backend should use a stronger, salted KDF
    such as bcrypt or Argon2 for real user passwords.
    """
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def _seed_app_info(cursor: sqlite3.Cursor) -> None:
    """Seed core app_info keys in an idempotent way."""
    entries = {
        "project_name": "streaming_database",
        "version": "0.2.0",
        "author": "Demo Seed",
        "description": "SQLite database for the Streamline Video Platform (streaming metadata, users, history).",
        "schema": "users, categories, videos, video_categories, watch_history, app_info",
    }
    for key, value in entries.items():
        cursor.execute(
            "INSERT OR REPLACE INTO app_info (key, value) VALUES (?, ?)",
            (key, value),
        )


def _seed_demo_user(cursor: sqlite3.Cursor) -> int:
    """Seed at least one demo user with a hashed password and return its id."""
    username = "demo_user"
    email = "demo@example.com"
    full_name = "Demo User"
    password_hash = _hash_password("password123")

    # Insert if missing
    cursor.execute(
        """
        INSERT OR IGNORE INTO users (username, email, password_hash, full_name, is_active)
        VALUES (?, ?, ?, ?, 1)
        """,
        (username, email, password_hash, full_name),
    )

    # Update to keep data fresh/idempotent
    cursor.execute(
        """
        UPDATE users
        SET email = ?, password_hash = ?, full_name = ?, is_active = 1
        WHERE username = ?
        """,
        (email, password_hash, full_name, username),
    )

    cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()
    if not row:
        raise RuntimeError("Failed to seed demo user.")
    return int(row[0])


def _seed_categories(cursor: sqlite3.Cursor) -> Dict[str, int]:
    """Seed a core set of video categories and return a mapping name -> id."""
    categories = [
        ("Action", "High-energy movies and series filled with stunts and chases."),
        ("Drama", "Character-driven stories with emotional stakes."),
        ("Comedy", "Light-hearted content to make you laugh."),
        ("Sci-Fi", "Speculative science fiction and futuristic adventures."),
        ("Documentary", "Non-fictional, informative films and series."),
        ("Family", "Family-friendly movies and shows."),
    ]

    for name, description in categories:
        cursor.execute(
            """
            INSERT OR IGNORE INTO categories (name, description)
            VALUES (?, ?)
            """,
            (name, description),
        )

    cursor.execute("SELECT id, name FROM categories")
    rows = cursor.fetchall()
    return {name: cat_id for (cat_id, name) in rows}


def _seed_videos(cursor: sqlite3.Cursor, category_ids: Dict[str, int]) -> Dict[str, int]:
    """Seed demo videos and their category mappings; return slug -> id mapping."""
    videos = [
        {
            "slug": "galaxy-odyssey",
            "title": "Galaxy Odyssey",
            "description": "A crew of explorers travels through distant galaxies on a risky mission.",
            "video_url": "/videos/galaxy-odyssey.mp4",
            "thumbnail_url": "/thumbnails/galaxy-odyssey.jpg",
            "duration_seconds": 5400,
            "categories": ["Sci-Fi", "Action"],
        },
        {
            "slug": "urban-comedy-night",
            "title": "Urban Comedy Night",
            "description": "Stand-up comedians take the stage for a night of laughs.",
            "video_url": "/videos/urban-comedy-night.mp4",
            "thumbnail_url": "/thumbnails/urban-comedy-night.jpg",
            "duration_seconds": 3600,
            "categories": ["Comedy"],
        },
        {
            "slug": "deep-sea-mysteries",
            "title": "Deep Sea Mysteries",
            "description": "A documentary exploring the most remote parts of the ocean.",
            "video_url": "/videos/deep-sea-mysteries.mp4",
            "thumbnail_url": "/thumbnails/deep-sea-mysteries.jpg",
            "duration_seconds": 4200,
            "categories": ["Documentary"],
        },
        {
            "slug": "city-of-shadows",
            "title": "City of Shadows",
            "description": "A gritty crime drama set in a neon-lit metropolis.",
            "video_url": "/videos/city-of-shadows.mp4",
            "thumbnail_url": "/thumbnails/city-of-shadows.jpg",
            "duration_seconds": 4800,
            "categories": ["Drama", "Action"],
        },
        {
            "slug": "cosmic-frontier",
            "title": "Cosmic Frontier",
            "description": "A serialized sci-fi show following a frontier space station.",
            "video_url": "/videos/cosmic-frontier.mp4",
            "thumbnail_url": "/thumbnails/cosmic-frontier.jpg",
            "duration_seconds": 2700,
            "categories": ["Sci-Fi"],
        },
        {
            "slug": "family-road-trip",
            "title": "Family Road Trip",
            "description": "A heartwarming story of a family rediscovering each other on the road.",
            "video_url": "/videos/family-road-trip.mp4",
            "thumbnail_url": "/thumbnails/family-road-trip.jpg",
            "duration_seconds": 5400,
            "categories": ["Family", "Comedy"],
        },
        {
            "slug": "kitchen-stories",
            "title": "Kitchen Stories",
            "description": "A cozy cooking show sharing recipes and stories.",
            "video_url": "/videos/kitchen-stories.mp4",
            "thumbnail_url": "/thumbnails/kitchen-stories.jpg",
            "duration_seconds": 1500,
            "categories": ["Documentary", "Family"],
        },
        {
            "slug": "edge-of-reality",
            "title": "Edge of Reality",
            "description": "A mind-bending sci-fi thriller about simulated worlds.",
            "video_url": "/videos/edge-of-reality.mp4",
            "thumbnail_url": "/thumbnails/edge-of-reality.jpg",
            "duration_seconds": 6000,
            "categories": ["Sci-Fi", "Drama"],
        },
        {
            "slug": "laugh-out-loud",
            "title": "Laugh Out Loud",
            "description": "A curated collection of hilarious sketches.",
            "video_url": "/videos/laugh-out-loud.mp4",
            "thumbnail_url": "/thumbnails/laugh-out-loud.jpg",
            "duration_seconds": 1800,
            "categories": ["Comedy"],
        },
        {
            "slug": "planet-earthways",
            "title": "Planet Earthways",
            "description": "Stunning visuals showcase nature across the globe.",
            "video_url": "/videos/planet-earthways.mp4",
            "thumbnail_url": "/thumbnails/planet-earthways.jpg",
            "duration_seconds": 3600,
            "categories": ["Documentary", "Family"],
        },
    ]

    for video in videos:
        cursor.execute(
            """
            INSERT OR IGNORE INTO videos
                (slug, title, description, video_url, thumbnail_url, duration_seconds, is_published)
            VALUES (?, ?, ?, ?, ?, ?, 1)
            """,
            (
                video["slug"],
                video["title"],
                video["description"],
                video["video_url"],
                video["thumbnail_url"],
                video["duration_seconds"],
            ),
        )

        # Fetch id to create join-table entries
        cursor.execute("SELECT id FROM videos WHERE slug = ?", (video["slug"],))
        row = cursor.fetchone()
        if not row:
            raise RuntimeError(f"Failed to seed video with slug '{video['slug']}'")
        video_id = int(row[0])

        for cat_name in video["categories"]:
            cat_id = category_ids.get(cat_name)
            if cat_id is None:
                continue
            cursor.execute(
                """
                INSERT OR IGNORE INTO video_categories (video_id, category_id)
                VALUES (?, ?)
                """,
                (video_id, cat_id),
            )

    cursor.execute("SELECT id, slug FROM videos")
    rows = cursor.fetchall()
    return {slug: vid_id for (vid_id, slug) in rows}


def _seed_watch_history(
    cursor: sqlite3.Cursor, demo_user_id: int, video_ids: Dict[str, int]
) -> None:
    """Seed a handful of watch_history entries for the demo user.

    Uses INSERT OR REPLACE with a UNIQUE(user_id, video_id) constraint to keep
    the data idempotent while still resembling real watch progress tracking.
    """
    samples = [
        ("galaxy-odyssey", 1200, 0),
        ("deep-sea-mysteries", 2100, 0),
        ("urban-comedy-night", 3500, 1),
        ("family-road-trip", 1800, 0),
        ("edge-of-reality", 900, 0),
    ]

    for slug, progress_seconds, completed in samples:
        video_id = video_ids.get(slug)
        if video_id is None:
            continue
        cursor.execute(
            """
            INSERT OR REPLACE INTO watch_history
                (user_id, video_id, progress_seconds, completed, last_watched_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (demo_user_id, video_id, progress_seconds, completed),
        )


def _write_connection_files() -> None:
    """Write db_connection.txt and db_visualizer/sqlite.env with the current DB path."""
    db_path = os.path.abspath(DB_PATH)
    connection_string = f"sqlite:///{db_path}"

    # db_connection.txt
    try:
        connection_file_path = os.path.join(BASE_DIR, "db_connection.txt")
        with open(connection_file_path, "w", encoding="utf-8") as f:
            f.write("# SQLite connection methods:\n")
            f.write(f"# Python: sqlite3.connect('{db_path}')\n")
            f.write(f"# Connection string: {connection_string}\n")
            f.write(f"# File path: {db_path}\n")
        print(f"Connection information saved to {connection_file_path}")
    except Exception as exc:  # pragma: no cover - best-effort logging
        print(f"Warning: Could not save connection info: {exc}")

    # db_visualizer/sqlite.env
    try:
        visualizer_dir = os.path.join(BASE_DIR, "db_visualizer")
        if not os.path.exists(visualizer_dir):
            os.makedirs(visualizer_dir, exist_ok=True)
            print("Created db_visualizer directory")

        sqlite_env_path = os.path.join(visualizer_dir, "sqlite.env")
        with open(sqlite_env_path, "w", encoding="utf-8") as f:
            f.write(f'export SQLITE_DB="{db_path}"\n')
        print(f"Environment variables saved to {sqlite_env_path}")
    except Exception as exc:  # pragma: no cover - best-effort logging
        print(f"Warning: Could not save environment variables: {exc}")


# PUBLIC_INTERFACE
def initialize_database() -> None:
    """Create or upgrade the SQLite database schema and seed demo data.

    This function:

    - Detects whether the database file already exists.
    - Creates/updates tables: users, categories, videos, video_categories,
      watch_history, and app_info.
    - Seeds one demo user with a hashed password, several categories,
      8–12 videos, and some watch_history rows.
    - Writes db_connection.txt with a SQLAlchemy-ready sqlite URL and
      db_visualizer/sqlite.env with the correct SQLITE_DB path.
    """
    print("Starting SQLite setup...")

    db_exists = os.path.exists(DB_PATH)
    if db_exists:
        print(f"SQLite database already exists at {DB_PATH}")
    else:
        print(f"Creating new SQLite database at {DB_PATH}...")

    conn = sqlite3.connect(DB_PATH)
    try:
        # Ensure foreign key constraints are enforced
        conn.execute("PRAGMA foreign_keys = ON")
        cursor = conn.cursor()

        # Schema and seeds
        _create_schema(cursor)
        _seed_app_info(cursor)
        demo_user_id = _seed_demo_user(cursor)
        category_ids = _seed_categories(cursor)
        video_ids = _seed_videos(cursor, category_ids)
        _seed_watch_history(cursor, demo_user_id, video_ids)

        conn.commit()

        # Basic statistics
        cursor.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        table_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM users")
        user_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM categories")
        category_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM videos")
        video_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM watch_history")
        history_count = cursor.fetchone()[0]

        print("\nSQLite setup complete!")
        print(f"Database path : {DB_PATH}")
        print(f"Tables        : {table_count}")
        print(f"Users         : {user_count}")
        print(f"Categories    : {category_count}")
        print(f"Videos        : {video_count}")
        print(f"Watch history : {history_count}")
        print("")

    finally:
        conn.close()

    # Write connection helpers after successful initialization
    _write_connection_files()

    print("To connect to the database, you can use one of the following methods:")
    print(f"  1. Python sqlite3: sqlite3.connect('{os.path.abspath(DB_PATH)}')")
    print(f"  2. SQLAlchemy URL: sqlite:///{os.path.abspath(DB_PATH)}")
    print(f"  3. Direct file   : {os.path.abspath(DB_PATH)}")
    print("")
    print("For the Node.js database viewer:")
    print("  - Ensure db_visualizer/sqlite.env exists (generated by this script).")
    print("  - From db_visualizer/, run: npm install && npm start")
    print("")


if __name__ == "__main__":
    initialize_database()
    print("\nScript completed successfully.")
