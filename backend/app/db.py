"""SQLite persistence (aiosqlite) for chat sessions and messages.

The schema is created on every startup (idempotent). WAL mode and a busy timeout
keep concurrent readers/writers happy. Every query is parameterized.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL,
    role        TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content     TEXT NOT NULL,
    metadata    TEXT,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages (session_id, id);

CREATE TABLE IF NOT EXISTS sessions (
    session_id     TEXT PRIMARY KEY,
    system_prompt  TEXT,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);
"""


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


class Database:
    def __init__(self, path: str) -> None:
        self.path = path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        if self.path != ":memory:":
            Path(self.path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        # isolation_level=None -> autocommit; writes use explicit BEGIN/COMMIT.
        self._conn = await aiosqlite.connect(self.path, timeout=10, isolation_level=None)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA busy_timeout = 10000")
        if self.path != ":memory:":
            await self._conn.execute("PRAGMA journal_mode = WAL")
        await self._conn.execute("PRAGMA synchronous = NORMAL")
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()
        logger.info("database ready", extra={"db_path": self.path})

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("database not connected")
        return self._conn

    async def ping(self) -> bool:
        try:
            async with self.conn.execute("SELECT 1") as cur:
                row = await cur.fetchone()
            return row is not None and row[0] == 1
        except Exception:  # noqa: BLE001 - health check must never raise
            logger.exception("database ping failed")
            return False

    async def session_exists(self, session_id: str) -> bool:
        async with self.conn.execute(
            "SELECT 1 FROM sessions WHERE session_id = ? "
            "UNION SELECT 1 FROM messages WHERE session_id = ? LIMIT 1",
            (session_id, session_id),
        ) as cur:
            return await cur.fetchone() is not None

    async def get_system_prompt(self, session_id: str) -> str | None:
        async with self.conn.execute(
            "SELECT system_prompt FROM sessions WHERE session_id = ?", (session_id,)
        ) as cur:
            row = await cur.fetchone()
        return row["system_prompt"] if row else None

    async def get_history(self, session_id: str) -> list[dict[str, Any]]:
        """Messages for a session, oldest first. Metadata is decoded for assistant turns."""
        async with self.conn.execute(
            "SELECT role, content, metadata FROM messages WHERE session_id = ? ORDER BY id ASC",
            (session_id,),
        ) as cur:
            rows = await cur.fetchall()
        history: list[dict[str, Any]] = []
        for row in rows:
            item: dict[str, Any] = {"role": row["role"], "content": row["content"]}
            if row["role"] == "assistant" and row["metadata"]:
                try:
                    item["metadata"] = json.loads(row["metadata"])
                except json.JSONDecodeError:
                    item["metadata"] = {}
            history.append(item)
        return history

    async def save_exchange(
        self,
        session_id: str,
        user_message: str,
        assistant_reply: str,
        metadata: dict[str, Any],
        system_prompt: str | None,
    ) -> None:
        """Persist a successful turn atomically: both messages or nothing.

        system_prompt is only written when the client supplied one, so later turns
        without it keep reusing the stored value.
        """
        user_ts = utc_now_iso()
        assistant_ts = utc_now_iso()
        conn = self.conn
        try:
            await conn.execute("BEGIN IMMEDIATE")
            await conn.execute(
                "INSERT INTO sessions (session_id, system_prompt, created_at, updated_at) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(session_id) DO UPDATE SET "
                "system_prompt = COALESCE(excluded.system_prompt, sessions.system_prompt), "
                "updated_at = excluded.updated_at",
                (session_id, system_prompt, user_ts, assistant_ts),
            )
            await conn.execute(
                "INSERT INTO messages (session_id, role, content, metadata, created_at) "
                "VALUES (?, 'user', ?, NULL, ?)",
                (session_id, user_message, user_ts),
            )
            await conn.execute(
                "INSERT INTO messages (session_id, role, content, metadata, created_at) "
                "VALUES (?, 'assistant', ?, ?, ?)",
                (session_id, assistant_reply, json.dumps(metadata), assistant_ts),
            )
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise
