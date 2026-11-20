"""X-Simulate-Failure: parser unit tests + the contract table end to end."""

import httpx
import pytest
from asgi_lifespan import LifespanManager

from app.main import create_app
from app.simulation import parse_simulation_header
from tests.conftest import TEST_KEYS

K1, K2 = TEST_KEYS
KEYS = ["key_1", "key_2"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, None),
        ("", None),
        ("   ", None),
        ("key_1=429", {"key_1": 429}),
        (" key_1 = 500 ", {"key_1": 500}),
        ("KEY_1=502", {"key_1": 502}),
        ("key_1=429,key_2=500", {"key_1": 429, "key_2": 500}),
        ("*=429", {"key_1": 429, "key_2": 429}),
        ("*=429,key_2=503", {"key_1": 429, "key_2": 503}),
        ("key_1=404", {}),  # unsupported status ignored
        ("garbage", {}),
        ("key_9=429", {}),  # unknown key ignored
        ("key_1=429,,oops,key_2=abc", {"key_1": 429}),
    ],
)
def test_parse_header(raw, expected):
    assert parse_simulation_header(raw, KEYS) == expected


def _client_factory(make_settings, fake_llm):
    async def _make(**overrides):
        app = create_app(make_settings(**overrides))
        manager = LifespanManager(app)
        await manager.__aenter__()
        client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
        client.manager = manager
        return client

    return _make


@pytest.fixture
async def client(make_settings, fake_llm):
    c = await _client_factory(make_settings, fake_llm)()
    yield c
    await c.aclose()
    await c.manager.__aexit__(None, None, None)


async def post(client, sid, msg, header=None):
    headers = {"X-Simulate-Failure": header} if header else {}
    return await client.post("/chat", json={"session_id": sid, "message": msg}, headers=headers)


@pytest.mark.parametrize("header", ["key_1=429", "key_1=500", "key_1=502", "key_1=503"])
async def test_key_1_failure_falls_back_to_key_2(client, fake_llm, header):
    r = await post(client, "s-sim", "Tell me a fact", header)
    assert r.status_code == 200
    meta = r.json()["metadata"]
    assert meta["key_id"] == "key_2" and meta["fallback_attempts"] == 1
    assert meta["resolution_source"] == "LIVE_INFERENCE"
    assert r.json()["reply"].startswith("Echo")  # a real answer from the surviving key
    assert fake_llm.calls == [K2]


@pytest.mark.parametrize("header", ["*=429", "key_1=429,key_2=500", "*=503"])
async def test_all_keys_failing_is_clean_503(client, header):
    await post(client, "s-keep", "first turn")  # pre-existing history
    r = await post(client, "s-keep", "doomed turn", header)
    assert r.status_code == 503
    assert r.json() == {"detail": "all providers unavailable"}
    msgs = (await client.get("/sessions/s-keep/messages")).json()["messages"]
    assert len(msgs) == 2 and "doomed turn" not in str(msgs)


async def test_failed_new_session_is_not_created(client):
    r = await post(client, "s-new-fail", "hello", "*=429")
    assert r.status_code == 503
    assert (await client.get("/sessions/s-new-fail/messages")).status_code == 404


async def test_simulated_request_bypasses_cache(client):
    first = await post(client, "s-c1", "Cache me if you can")
    assert first.json()["metadata"]["resolution_source"] == "LIVE_INFERENCE"
    cached = await post(client, "s-c2", "Cache me if you can")
    assert cached.json()["metadata"]["resolution_source"] == "LLM_CACHE"
    sim = await post(client, "s-c3", "Cache me if you can", "key_1=429")
    assert sim.json()["metadata"]["resolution_source"] == "LIVE_INFERENCE"
    assert sim.json()["metadata"]["key_id"] == "key_2"


async def test_simulation_is_per_request_only(client, fake_llm):
    await post(client, "s-pr", "first", "key_1=429")
    r = await post(client, "s-pr", "second")  # no header -> normal behaviour
    assert r.json()["metadata"]["key_id"] == "key_1"
    assert r.json()["metadata"]["fallback_attempts"] == 0


async def test_header_ignored_when_switch_off(make_settings, fake_llm):
    client = await _client_factory(make_settings, fake_llm)(enable_failure_simulation=False)
    try:
        r = await post(client, "s-off", "hello", "*=429")
        assert r.status_code == 200
        assert r.json()["metadata"]["key_id"] == "key_1"
    finally:
        await client.aclose()
        await client.manager.__aexit__(None, None, None)


async def test_no_key_leakage_anywhere(client):
    responses = [
        await post(client, "s-leak", "hi"),
        await post(client, "s-leak", "hi again", "key_1=429"),
        await post(client, "s-leak", "doomed", "*=429"),
        await client.get("/sessions/s-leak/messages"),
        await client.get("/health"),
    ]
    for r in responses:
        for key in TEST_KEYS:
            assert key not in r.text
