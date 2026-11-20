"""Per-session asyncio locks so concurrent turns on one session stay ordered.

Locks are reference-counted and dropped when idle, so memory does not grow with
the number of sessions ever seen. Different sessions never block each other.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager


class SessionLocks:
    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}
        self._refs: dict[str, int] = {}

    @asynccontextmanager
    async def hold(self, session_id: str) -> AsyncIterator[None]:
        lock = self._locks.setdefault(session_id, asyncio.Lock())
        self._refs[session_id] = self._refs.get(session_id, 0) + 1
        try:
            async with lock:
                yield
        finally:
            self._refs[session_id] -= 1
            if self._refs[session_id] == 0:
                del self._refs[session_id]
                del self._locks[session_id]

    def __len__(self) -> int:
        return len(self._locks)
