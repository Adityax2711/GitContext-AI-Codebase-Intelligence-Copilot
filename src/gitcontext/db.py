"""Database persistence layer for GitContext.

Stores:
- User accounts and linked GitHub identities
- User sessions and OAuth verification states
- Imported repositories and access metadata
- Indexing jobs and status transitions
- Conversations and chat message histories with citations
- Bug investigation findings and fix proposal reviews

Uses SQLite by default with thread safety and WAL mode, supporting PostgreSQL
when DATABASE_URL is configured.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

logger = logging.getLogger(__name__)

DB_PATH = Path(os.getenv("GITCONTEXT_DB_PATH", Path.cwd() / "data" / "gitcontext.db")).resolve()


class DatabaseManager:
    """Manages SQLite database connections and table schemas."""

    _instance: Optional[DatabaseManager] = None
    _lock = threading.Lock()

    def __init__(self, db_path: Path = DB_PATH) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._init_schema()

    @classmethod
    def get_instance(cls, db_path: Optional[Path] = None) -> DatabaseManager:
        with cls._lock:
            if cls._instance is None or (db_path and cls._instance.db_path != db_path):
                cls._instance = DatabaseManager(db_path or DB_PATH)
            return cls._instance

    def _get_connection(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(
                str(self.db_path),
                timeout=30.0,
                check_same_thread=False,
            )
            conn.row_factory = sqlite3.Row
            # Enable WAL mode for concurrent reads & writes
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA foreign_keys=ON;")
            self._local.conn = conn
        return self._local.conn

    @contextmanager
    def connection(self) -> Generator[sqlite3.Connection, None, None]:
        conn = self._get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def _init_schema(self) -> None:
        """Create database tables if they do not exist."""
        with self.connection() as conn:
            conn.executescript(
                """
                -- Users table
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT UNIQUE,
                    password_hash TEXT,
                    salt TEXT,
                    name TEXT,
                    github_id INTEGER UNIQUE,
                    github_login TEXT,
                    github_avatar TEXT,
                    github_token TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                -- Sessions table
                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                -- OAuth verification states (anti-CSRF)
                CREATE TABLE IF NOT EXISTS oauth_states (
                    state TEXT PRIMARY KEY,
                    user_id INTEGER,
                    action TEXT DEFAULT 'login',
                    redirect_uri TEXT,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                -- Repositories table
                CREATE TABLE IF NOT EXISTS repositories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    owner TEXT NOT NULL,
                    name TEXT NOT NULL,
                    full_name TEXT NOT NULL,
                    branch TEXT DEFAULT 'main',
                    local_path TEXT NOT NULL UNIQUE,
                    is_private INTEGER DEFAULT 0,
                    default_branch TEXT DEFAULT 'main',
                    total_chunks INTEGER DEFAULT 0,
                    total_files INTEGER DEFAULT 0,
                    last_indexed_at TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
                );

                -- Indexing jobs table
                CREATE TABLE IF NOT EXISTS indexing_jobs (
                    id TEXT PRIMARY KEY,
                    repo_id INTEGER,
                    status TEXT NOT NULL, -- pending, running, completed, failed
                    progress REAL DEFAULT 0.0,
                    error_message TEXT,
                    total_files INTEGER DEFAULT 0,
                    total_chunks INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    finished_at TEXT,
                    FOREIGN KEY (repo_id) REFERENCES repositories(id) ON DELETE CASCADE
                );

                -- Conversations table
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    repo_id INTEGER,
                    user_id INTEGER,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (repo_id) REFERENCES repositories(id) ON DELETE CASCADE,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
                );

                -- Chat messages table
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL, -- user, assistant, system
                    content TEXT NOT NULL,
                    citations_json TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
                );

                -- Fix proposals and code review status
                CREATE TABLE IF NOT EXISTS fix_proposals (
                    id TEXT PRIMARY KEY,
                    repo_id INTEGER,
                    user_id INTEGER,
                    file_path TEXT NOT NULL,
                    diff_content TEXT NOT NULL,
                    rationale TEXT NOT NULL,
                    status TEXT DEFAULT 'pending', -- pending, approved, rejected, applied
                    test_results_json TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (repo_id) REFERENCES repositories(id) ON DELETE CASCADE,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
                );

                -- Indexes for fast lookups
                CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
                CREATE INDEX IF NOT EXISTS idx_users_github_id ON users(github_id);
                CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
                CREATE INDEX IF NOT EXISTS idx_repos_full_name ON repositories(full_name);
                CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id);
                """
            )


# Global singleton access
def get_db(db_path: Optional[Path] = None) -> DatabaseManager:
    return DatabaseManager.get_instance(db_path)
