# Streamline Video Platform – Database Workspace

This workspace (`streamline-video-platform-221764-221776`) contains the **database container** for the Streamline Video Platform, a Netflix‑style streaming application with:

- FastAPI backend (separate container)
- React + Vite + Tailwind CSS frontend (separate container)
- **SQLite** as the default database here, designed so it can later be migrated to PostgreSQL with minimal friction.

This README focuses on the **`streaming_database`** directory and how to work with the database schema, seed data, tests, visualizer, and backup/restore scripts.

---

## Directory Structure

```text
streamline-video-platform-221764-221776/
├── README.md                 # This file
└── streaming_database/
    ├── init_db.py            # Create/upgrade schema & seed data (idempotent)
    ├── test_db.py            # Health-check: schema + seeds + SQLite version
    ├── db_shell.py           # Interactive SQLite shell helper
    ├── backup_db.sh          # Universal backup script (SQLite/Postgres/MySQL/Mongo)
    ├── restore_db.sh         # Universal restore script
    ├── myapp.db              # SQLite database file (created by init_db.py)
    ├── db_connection.txt     # SQLite connection info (SQLAlchemy-ready URL)
    ├── .env.example          # Example env vars (SQLITE_DB, POSTGRES_URL)
    └── db_visualizer/
        ├── package.json
        ├── server.js
        └── sqlite.env        # Points the viewer at the correct SQLite DB path
```

---

## Database Schema Overview

The **`init_db.py`** script creates/maintains the following tables:

- `users`
  - Basic user account information.
  - Columns: `id`, `username` (unique), `email` (unique), `password_hash`, `full_name`,
    `is_active`, `created_at`.

- `categories`
  - Content categories/genres (e.g., Action, Drama, Comedy).
  - Columns: `id`, `name` (unique), `description`, `created_at`.

- `videos`
  - Video metadata used by the streaming backend and frontend.
  - Columns: `id`, `title`, `description`, `slug` (unique), `video_url`, `thumbnail_url`,
    `duration_seconds`, `is_published`, `created_at`.

- `video_categories`
  - Join table for the many‑to‑many relationship between `videos` and `categories`.
  - Columns: `video_id`, `category_id` (composite primary key).

- `watch_history`
  - Per‑user, per‑video watch state (last watched time & progress).
  - Columns: `id`, `user_id`, `video_id`, `progress_seconds`, `completed`,
    `last_watched_at`, plus a `UNIQUE(user_id, video_id)` constraint.

- `app_info`
  - Key‑value metadata for the database and project.
  - Columns: `id`, `key` (unique), `value`, `created_at`.

The schema uses generic SQL types (INTEGER, TEXT, TIMESTAMP) and avoids SQLite‑only
features where possible, making a future migration to PostgreSQL straightforward.

---

## Seed Data

`init_db.py` seeds the following data **idempotently** (safe to run multiple times):

- **Demo user**
  - `username`: `demo_user`
  - `email`: `demo@example.com`
  - `full_name`: `Demo User`
  - `password_hash`: non‑empty SHA‑256 hash of a demo password (for example only).
  - `is_active`: `1`

- **Categories**
  - At least these categories are seeded:
    - Action
    - Drama
    - Comedy
    - Sci-Fi
    - Documentary
    - Family

- **Videos**
  - 8–12 demo videos with realistic metadata, for example:
    - `galaxy-odyssey`
    - `urban-comedy-night`
    - `deep-sea-mysteries`
    - `city-of-shadows`
    - `cosmic-frontier`
    - `family-road-trip`
    - `kitchen-stories`
    - `edge-of-reality`
    - `laugh-out-loud`
    - `planet-earthways`
  - Each video has:
    - `title`, `description`
    - `slug` (unique)
    - `video_url`, `thumbnail_url` (paths/placeholders for the app)
    - `duration_seconds`
    - `is_published` flag
  - Videos are associated with one or more categories via `video_categories`.

- **Watch history**
  - Several `watch_history` rows for `demo_user`, covering different videos
    and progress/completed states.

---

## 1. Initialize / Upgrade the Database

From the workspace root:

```bash
cd streaming_database
python init_db.py
```

This will:

1. Create the SQLite database file (`myapp.db`) if it does not exist.
2. Create or update the schema for:
   - `users`, `categories`, `videos`, `video_categories`, `watch_history`, `app_info`
3. Seed:
   - At least one demo user with a hashed password.
   - Several categories.
   - 8–12 demo videos and some `watch_history` rows.
4. Write helper files:
   - `db_connection.txt` with:
     - A **SQLAlchemy‑ready** SQLite URL like:
       - `sqlite:////absolute/path/to/streamline-video-platform-221764-221776/streaming_database/myapp.db`
     - The absolute file path to the database.
   - `db_visualizer/sqlite.env` with:
     - `export SQLITE_DB="/absolute/path/to/.../myapp.db"`

> **Idempotent:** You can run `python init_db.py` as many times as you like. It will
> not create duplicate seed rows and will progressively add any new columns needed
> for the streaming domain.

---

## 2. Run Database Health Tests

After initialization, run the health-check script:

```bash
cd streaming_database
python test_db.py
```

What it does:

- Ensures the database has been initialized (it will call `init_db.py` if needed).
- Reads the DB file path from `db_connection.txt`.
- Connects to the database and **prints the SQLite version**.
- Verifies that required tables exist:
  - `users`, `categories`, `videos`, `video_categories`, `watch_history`, `app_info`
- Verifies core seed data:
  - At least one user (including `demo_user` with a non‑empty `password_hash`).
  - Several categories.
  - At least 8 videos.
  - At least one `watch_history` row for `demo_user`.

A successful run ends with:

- A line like: `SQLite version: X.Y.Z`
- A confirmation that all checks passed.
- Exit code 0.

---

## 3. Using the Node.js Database Visualizer

The `db_visualizer` directory contains a lightweight Node.js app that can inspect
SQLite (and other DBs) via a simple web UI.

### Setup

```bash
cd streaming_database
python init_db.py  # ensure db_visualizer/sqlite.env is generated

cd db_visualizer
npm install
```

`init_db.py` writes `db_visualizer/sqlite.env` that looks like:

```bash
export SQLITE_DB="/absolute/path/to/streamline-video-platform-221764-221776/streaming_database/myapp.db"
```

The viewer’s `server.js` automatically loads this file and uses `SQLITE_DB` to
connect to the correct SQLite database.

### Run the viewer

```bash
cd streaming_database/db_visualizer
npm start
```

Then open the printed URL (typically `http://localhost:3000`) in a browser.
You should see the list of available databases and can explore:

- Tables and schemas
- Rows in `users`, `categories`, `videos`, `watch_history`, etc.

---

## 4. Backup and Restore

The workspace includes universal shell scripts for backing up and restoring the
database. These scripts detect which database engine is in use and act
accordingly (here we primarily use SQLite).

> Run all commands from the `streaming_database` directory.

### Backup

```bash
cd streaming_database
./backup_db.sh
```

For SQLite:

- If `myapp.db` exists in this directory, it will create a file:
  - `database_backup.db`

For other database engines (PostgreSQL/MySQL/MongoDB), the script will attempt
to detect a running instance and create engine‑specific backups as needed.

### Restore

```bash
cd streaming_database
./restore_db.sh
```

For SQLite:

- If `database_backup.db` exists, it will be copied back to `myapp.db`.

For other engines, it will attempt to restore from `database_backup.sql` or
`database_backup.archive` depending on the type.

---

## 5. Interactive SQLite Shell

For ad‑hoc querying and inspection, use the bundled Python shell:

```bash
cd streaming_database
python db_shell.py
```

Supported commands in the shell:

- `.help` – Show help
- `.tables` – List tables
- `.schema [table]` – Show CREATE TABLE statements
- `.describe [table]` – Show column details
- `.quit` / `.exit` – Leave the shell

Standard SQL commands (SELECT, INSERT, UPDATE, DELETE, etc.) are also supported.

---

## 6. Environment Variables and Portability

The database container is designed so that switching from SQLite to PostgreSQL
requires minimal changes in the backend and infrastructure.

- Example environment file: `streaming_database/.env.example`

  ```bash
  # Absolute path to the SQLite database file
  SQLITE_DB=/absolute/path/to/streamline-video-platform-221764-221776/streaming_database/myapp.db

  # Optional PostgreSQL URL for future migration
  # POSTGRES_URL=postgresql://user:password@localhost:5432/streaming_db
  ```

- `init_db.py`:
  - Uses `SQLITE_DB` if it is set; otherwise defaults to `myapp.db` in
    `streaming_database/`.
  - Updates `db_connection.txt` with a SQLAlchemy‑ready URL, e.g.:

    ```text
    Connection string: sqlite:////absolute/path/to/streamline-video-platform-221764-221776/streaming_database/myapp.db
    ```

This setup keeps configuration out of code and centralized in environment
variables, while still working out‑of‑the‑box with SQLite.

---

## Summary

- Run `python streaming_database/init_db.py` to create/upgrade the schema and seed data.
- Run `python streaming_database/test_db.py` to verify the database and seeds.
- Use `./streaming_database/backup_db.sh` and `./streaming_database/restore_db.sh`
  for backups and restores.
- Use the Node.js viewer in `streaming_database/db_visualizer` to visually explore
  the SQLite database.
- Use `.env.example` as the starting point for your environment configuration
  (`SQLITE_DB`, `POSTGRES_URL`).

This database container now provides a complete, seeded streaming domain ready
for the FastAPI backend and React frontend to build upon.
