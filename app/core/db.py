import sqlite3
import os
from pathlib import Path
from datetime import datetime, timezone
from contextlib import contextmanager
from typing import List, Optional, Any, Dict
from app.core.config import settings
from app.core.logger import logger

class DatabaseManager:
    """Manages SQLite connection, schema, and migrations."""

    def __init__(self):
        self.db_path = Path(settings.database_url.replace("sqlite:///", ""))
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_db()

    @contextmanager
    def get_connection(self):
        """Context manager for SQLite connections with WAL mode."""
        conn = sqlite3.connect(
            str(self.db_path),
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES
        )
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            yield conn
        finally:
            conn.close()

    def _initialize_db(self):
        """Ensures the database exists and applies migrations."""
        logger.info("db_initialization_started", path=str(self.db_path))
        
        # 1. Create schema_version table if it doesn't exist
        with self.get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                )
            """)
            conn.commit()

        # 2. Apply migrations
        self._run_migrations()
        logger.info("db_initialization_complete")

    def _run_migrations(self):
        """Applies forward-only migrations."""
        migrations = [
            # Version 1: Initial Schema
            """
            CREATE TABLE IF NOT EXISTS channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username_or_link TEXT UNIQUE NOT NULL,
                display_name TEXT,
                added_at TEXT NOT NULL,
                is_active BOOLEAN DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS media (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                media_id TEXT UNIQUE NOT NULL,
                file_type TEXT NOT NULL,
                file_size_bytes INTEGER,
                status TEXT NOT NULL,
                discovered_at TEXT NOT NULL,
                downloaded_at TEXT,
                local_path TEXT,
                FOREIGN KEY (channel_id) REFERENCES channels (id)
            );

            CREATE TABLE IF NOT EXISTS queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                media_id TEXT UNIQUE NOT NULL,
                priority INTEGER DEFAULT 0,
                enqueued_at TEXT NOT NULL,
                status TEXT NOT NULL,
                retry_count INTEGER DEFAULT 0,
                last_error TEXT,
                last_attempt_at TEXT,
                FOREIGN KEY (media_id) REFERENCES media (media_id)
            );

            CREATE TABLE IF NOT EXISTS scheduler_state (
                channel_id INTEGER PRIMARY KEY,
                tier INTEGER DEFAULT 1,
                cooldown_until TEXT,
                empty_poll_streak INTEGER DEFAULT 0,
                active_poll_streak INTEGER DEFAULT 0,
                last_polled_at TEXT,
                last_message_id INTEGER,
                FOREIGN KEY (channel_id) REFERENCES channels (id)
            );

            CREATE TABLE IF NOT EXISTS global_state (
                key TEXT PRIMARY KEY,
                value TEXT
            );

            INSERT OR IGNORE INTO global_state (key, value) VALUES ('paused', '0');
            """,
            # Version 2: Ensure global_state exists (for users who initialized before it was added to V1)
            """
            CREATE TABLE IF NOT EXISTS global_state (
                key TEXT PRIMARY KEY,
                value TEXT
            );
            INSERT OR IGNORE INTO global_state (key, value) VALUES ('paused', '0');
            """,
            # Version 3: Add is_periodic to channels
            """
            ALTER TABLE channels ADD COLUMN is_periodic BOOLEAN DEFAULT 0;
            """
        ]

        with self.get_connection() as conn:
            row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
            current_version = row[0] if row[0] is not None else 0

            for i, sql in enumerate(migrations, 1):
                if i > current_version:
                    logger.info("applying_migration", version=i)
                    try:
                        conn.executescript(sql)
                        conn.execute(
                            "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
                            (i, datetime.now(timezone.utc).isoformat())
                        )
                        conn.commit()
                    except Exception as e:
                        logger.error("migration_failed", version=i, error=str(e))
                        conn.rollback()
                        raise

    def execute(self, query: str, params: tuple = ()) -> sqlite3.Cursor:
        """Executes a single query and commits."""
        with self.get_connection() as conn:
            cursor = conn.execute(query, params)
            conn.commit()
            return cursor

    def fetch_one(self, query: str, params: tuple = ()) -> Optional[sqlite3.Row]:
        """Fetches a single row."""
        with self.get_connection() as conn:
            return conn.execute(query, params).fetchone()

    def fetch_all(self, query: str, params: tuple = ()) -> List[sqlite3.Row]:
        """Fetches all rows."""
        with self.get_connection() as conn:
            return conn.execute(query, params).fetchall()

# Global database instance
db = DatabaseManager()
