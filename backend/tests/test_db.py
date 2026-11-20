import pytest

from app.config import sqlite_path_from_url
from app.db import Database


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("sqlite:////data/app.db", "/data/app.db"),
        ("sqlite:///./data/app.db", "./data/app.db"),
        ("sqlite:///:memory:", ":memory:"),
        ("/tmp/x.db", "/tmp/x.db"),
    ],
)
def test_sqlite_url_parsing(url, expected):
    assert sqlite_path_from_url(url) == expected


async def test_schema_and_exchange_roundtrip(tmp_path):
    db = Database(str(tmp_path / "nested" / "dir" / "app.db"))
    await db.connect()
    try:
        assert await db.ping()
        assert not await db.session_exists("s-1")
        await db.save_exchange("s-1", "hi", "hello", {"resolution_source": "LIVE_INFERENCE"}, "be nice")
        await db.save_exchange("s-1", "again", "sure", {"resolution_source": "LLM_CACHE"}, None)
        assert await db.session_exists("s-1")
        # system prompt persisted and not overwritten by a later turn without one
        assert await db.get_system_prompt("s-1") == "be nice"
        history = await db.get_history("s-1")
        assert [m["role"] for m in history] == ["user", "assistant", "user", "assistant"]
        assert "metadata" not in history[0]
        assert history[1]["metadata"]["resolution_source"] == "LIVE_INFERENCE"
        assert history[3]["content"] == "sure"
    finally:
        await db.close()


async def test_sql_injection_is_inert(tmp_path):
    db = Database(str(tmp_path / "app.db"))
    await db.connect()
    try:
        evil = "x'; DROP TABLE messages; --"
        await db.save_exchange(evil, evil, "ok", {}, None)
        assert (await db.get_history(evil))[0]["content"] == evil
        assert await db.ping()
    finally:
        await db.close()
