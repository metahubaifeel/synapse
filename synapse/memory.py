"""SQLite shared memory layer for Synapse.

Provides persistent key-value storage for all agents in the Synapse system.
The database is auto-created at ~/.synapse/synapse.db.

Usage:
    with MemoryStore() as store:
        store.set("key", "value")
        value = store.get("key")
        store.delete("key")
        items = store.list()
"""

from __future__ import annotations

import os
import sqlite3
import time
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Tuple


DEFAULT_DB_DIR = os.path.expanduser("~/.synapse")
DEFAULT_DB_PATH = os.path.join(DEFAULT_DB_DIR, "synapse.db")


class MemoryStore:
    """SQLite-backed shared memory store for Synapse agents.

    Provides persistent key-value storage. Auto-creates the database
    directory and tables on first use. Use as a context manager.
    """

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or DEFAULT_DB_PATH
        self._conn: Optional[sqlite3.Connection] = None

    def _ensure_db(self) -> None:
        """Create the database directory and tables if they don't exist."""
        db_dir = os.path.dirname(self.db_path)
        os.makedirs(db_dir, exist_ok=True)
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    ttl REAL
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agents (
                    name TEXT PRIMARY KEY,
                    cmd TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    status TEXT DEFAULT 'registered',
                    created_at REAL NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    tool TEXT DEFAULT '',
                    status TEXT DEFAULT '',
                    detail TEXT DEFAULT '',
                    created_at REAL NOT NULL
                )
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_events_id ON events(id)"
            )
            self._conn.commit()

    def set(self, key: str, value: str, ttl: Optional[float] = None) -> None:
        """Set a memory key-value pair. Optionally set a TTL in seconds."""
        self._ensure_db()
        now = time.time()
        self._conn.execute(
            """
            INSERT INTO memory (key, value, created_at, updated_at, ttl)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at,
                ttl = excluded.ttl
            """,
            (key, value, now, now, ttl),
        )
        self._conn.commit()

    def get(self, key: str) -> Optional[str]:
        """Get a memory value by key. Returns None if not found or expired."""
        self._ensure_db()
        self._expire_old()
        row = self._conn.execute(
            "SELECT value FROM memory WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else None

    def list(self) -> List[Tuple[str, str]]:
        """List all non-expired memory key-value pairs."""
        self._ensure_db()
        self._expire_old()
        rows = self._conn.execute(
            "SELECT key, value FROM memory ORDER BY updated_at DESC"
        ).fetchall()
        return [(row["key"], row["value"]) for row in rows]

    def delete(self, key: str) -> bool:
        """Delete a memory entry by key. Returns True if deleted."""
        self._ensure_db()
        cursor = self._conn.execute("DELETE FROM memory WHERE key = ?", (key,))
        self._conn.commit()
        return cursor.rowcount > 0

    def _expire_old(self) -> None:
        """Remove entries past their TTL."""
        now = time.time()
        self._conn.execute(
            "DELETE FROM memory WHERE ttl IS NOT NULL AND (created_at + ttl) < ?",
            (now,),
        )
        self._conn.commit()

    # ── Agent registry (stored in the same DB) ──────────────────────────

    def register_agent(
        self, name: str, cmd: str, description: str = ""
    ) -> None:
        """Register an agent in the shared memory database."""
        self._ensure_db()
        now = time.time()
        self._conn.execute(
            """
            INSERT INTO agents (name, cmd, description, status, created_at)
            VALUES (?, ?, ?, 'registered', ?)
            ON CONFLICT(name) DO UPDATE SET
                cmd = excluded.cmd,
                description = excluded.description,
                status = 'registered'
            """,
            (name, cmd, description, now),
        )
        self._conn.commit()

    def get_agent(self, name: str) -> Optional[Dict[str, Any]]:
        """Get an agent by name."""
        self._ensure_db()
        row = self._conn.execute(
            "SELECT * FROM agents WHERE name = ?", (name,)
        ).fetchone()
        return dict(row) if row else None

    def list_agents(self) -> List[Dict[str, Any]]:
        """List all registered agents."""
        self._ensure_db()
        rows = self._conn.execute(
            "SELECT * FROM agents ORDER BY created_at"
        ).fetchall()
        return [dict(row) for row in rows]

    def remove_agent(self, name: str) -> bool:
        """Remove an agent from the registry."""
        self._ensure_db()
        cursor = self._conn.execute("DELETE FROM agents WHERE name = ?", (name,))
        self._conn.commit()
        return cursor.rowcount > 0

    # ── Event log (cross-process watch) ─────────────────────────────────

    def append_event(
        self,
        task_id: str,
        event_type: str,
        tool: str = "",
        status: str = "",
        detail: str = "",
    ) -> int:
        """Append an activity event. Returns the event row id."""
        self._ensure_db()
        now = time.time()
        cursor = self._conn.execute(
            """
            INSERT INTO events (task_id, event_type, tool, status, detail, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (task_id, event_type, tool, status, detail, now),
        )
        self._conn.commit()
        return cursor.lastrowid or 0

    def list_events_since(
        self, after_id: int = 0, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """List events with id > after_id, oldest first."""
        self._ensure_db()
        rows = self._conn.execute(
            """
            SELECT id, task_id, event_type, tool, status, detail, created_at
            FROM events
            WHERE id > ?
            ORDER BY id ASC
            LIMIT ?
            """,
            (after_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "MemoryStore":
        self._ensure_db()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False


@contextmanager
def open_memory(db_path: Optional[str] = None):
    """Context manager for MemoryStore. Handles auto-close."""
    store = MemoryStore(db_path=db_path)
    try:
        yield store
    finally:
        store.close()
