"""POST /chat contract: shape, types, caching labels, multi-turn, per-request tokens."""

import httpx
import pytest
from asgi_lifespan import LifespanManager

from app.main import create_app
from tests.conftest import TEST_KEYS

K1, K2 = TEST_KEYS


@pytest.fixture
async def client(make_settings, fake_llm):
    app = create_app(make_settings())
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            c.fake = fake_llm
            c.app = app
            yield c


async def chat(client, session_id, message, **extra):
    headers = extra.pop("headers", None)
    return await client.post("/chat", json={"session_id": session_id, "message": message, **extra}, headers=headers)


async def test_happy_path_shape_and_types(client):
    r = await chat(client, "s-1", "What is the capital of France?")
    assert r.status_code == 200
    body = r.json()
    assert set(body) >= {"session_id", "reply", "metadata"}
    assert body["session_id"] == "s-1"
    assert isinstance(body["reply"], str) and body["reply"]
    meta = body["metadata"]
    assert set(meta) >= {
        "resolution_source", "model", "latency_ms", "input_tokens", "output_tokens", "key_id", "fallback_attempts",
    }
    assert meta["resolution_source"] == "LIVE_INFERENCE"
    assert meta["model"] == "groq/test-model"
    assert type(meta["latency_ms"]) is int and meta["latency_ms"] >= 0
    assert type(meta["input_tokens"]) is int and meta["input_tokens"] > 0
    assert type(meta["output_tokens"]) is int and meta["output_tokens"] > 0
    assert meta["key_id"] == "key_1"
    assert meta["fallback_attempts"] == 0


async def test_cache_hit_in_new_session(client):
    first = (await chat(client, "s-a", "What is the capital of France?")).json()
    second = (await chat(client, "s-b", "What is the capital of France?")).json()
    m1, m2 = first["metadata"], second["metadata"]
    assert m1["resolution_source"] == "LIVE_INFERENCE"
    assert m2["resolution_source"] == "LLM_CACHE"
    assert second["reply"] == first["reply"]
    assert m2["key_id"] is None and m2["fallback_attempts"] == 0
    assert (m2["input_tokens"], m2["output_tokens"]) == (m1["input_tokens"], m1["output_tokens"])
    assert m2["latency_ms"] < m1["latency_ms"]


async def test_message_is_trimmed_before_use(client):
    a = (await chat(client, "s-t1", "Trim me")).json()
    b = (await chat(client, "s-t2", "   Trim me  \n")).json()
    assert b["metadata"]["resolution_source"] == "LLM_CACHE" and b["reply"] == a["reply"]
    hist = (await client.get("/sessions/s-t2/messages")).json()
    assert hist["messages"][0]["content"] == "Trim me"


async def test_different_message_is_live(client):
    await chat(client, "s-a", "Question one")
    r = (await chat(client, "s-b", "Question two")).json()
    assert r["metadata"]["resolution_source"] == "LIVE_INFERENCE"


async def test_multi_turn_memory_and_isolation(client):
    await chat(client, "s-x", "My name is Ada.")
    r = (await chat(client, "s-x", "What is my name?")).json()
    # The fake provider echoes every user turn it was sent: history was rebuilt.
    assert "My name is Ada." in r["reply"] and r["reply"].startswith("Echo turn 2")
    other = (await chat(client, "s-y", "What is my name?")).json()
    assert "Ada" not in other["reply"] and other["reply"].startswith("Echo turn 1")


async def test_tokens_are_per_request_not_cumulative(client):
    from tests.conftest import count_tokens

    r1 = (await chat(client, "s-tok", "one two three")).json()
    r2 = (await chat(client, "s-tok", "four five six")).json()
    t1, t2 = r1["metadata"], r2["metadata"]
    # input_tokens of turn 2 = exactly the prompt sent in turn 2 (system + history + new)
    sent = [
        {"role": "system", "content": "You are a helpful, concise assistant."},
        {"role": "user", "content": "one two three"},
        {"role": "assistant", "content": r1["reply"]},
        {"role": "user", "content": "four five six"},
    ]
    assert t2["input_tokens"] == count_tokens(sent)
    # output_tokens is just this reply, never a running total
    assert t2["output_tokens"] == len(r2["reply"].split())
    assert t2["input_tokens"] != t1["input_tokens"] + count_tokens(sent)


async def test_equal_length_first_messages_equal_input_tokens(client):
    a = (await chat(client, "s-e1", "apple banana cherry")).json()["metadata"]
    b = (await chat(client, "s-e2", "grape lemon mango")).json()["metadata"]
    assert a["input_tokens"] == b["input_tokens"]


async def test_system_prompt_persisted_per_session(client):
    sent = []
    original = client.fake.reply_for

    def spy(messages):
        sent.append(messages)
        return original(messages)

    client.fake.reply_for = spy
    await chat(client, "s-sp", "Hi", system_prompt="You are a pirate.")
    await chat(client, "s-sp", "Again")  # no system_prompt -> reuse stored one
    await chat(client, "s-other", "Hi")  # different session -> default
    assert sent[0][0] == {"role": "system", "content": "You are a pirate."}
    assert sent[1][0] == {"role": "system", "content": "You are a pirate."}
    assert sent[2][0]["content"] == "You are a helpful, concise assistant."


async def test_history_endpoint(client):
    await chat(client, "s-h", "first", system_prompt="secret system prompt")
    await chat(client, "s-h", "second")
    r = await client.get("/sessions/s-h/messages")
    assert r.status_code == 200
    body = r.json()
    assert body["session_id"] == "s-h"
    msgs = body["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant", "user", "assistant"]
    assert [m["content"] for m in msgs[::2]] == ["first", "second"]
    assert all(m["role"] != "system" for m in msgs)
    assert "secret system prompt" not in r.text
    assert "metadata" not in msgs[0]
    for m in msgs[1::2]:
        assert {"resolution_source", "input_tokens", "output_tokens"} <= set(m["metadata"])


async def test_history_unknown_session_404(client):
    r = await client.get("/sessions/does-not-exist/messages")
    assert r.status_code == 404
    assert r.json() == {"detail": "session not found"}


async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "keys_configured": 2, "cache_enabled": True}


async def test_all_keys_fail_returns_503_and_stores_nothing(client):
    import litellm

    err = litellm.RateLimitError(message="quota", llm_provider="groq", model="m")
    client.fake.behaviours = {K1: err, K2: err}
    r = await chat(client, "s-fail", "hello?")
    assert r.status_code == 503
    assert r.json() == {"detail": "all providers unavailable"}
    assert (await client.get("/sessions/s-fail/messages")).status_code == 404


async def test_real_failover_reports_key_2(client):
    import litellm

    client.fake.behaviours[K1] = litellm.InternalServerError(message="boom", llm_provider="groq", model="m")
    r = (await chat(client, "s-fo", "fail over please")).json()
    assert r["metadata"]["key_id"] == "key_2" and r["metadata"]["fallback_attempts"] == 1


async def test_concurrent_turns_same_session_are_serialized(client):
    import asyncio

    await asyncio.gather(*(chat(client, "s-conc", f"msg {i}") for i in range(5)))
    msgs = (await client.get("/sessions/s-conc/messages")).json()["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant"] * 5
    turns = [int(m["content"].split()[2].rstrip(":")) for m in msgs[1::2]]
    assert turns == [1, 2, 3, 4, 5]
