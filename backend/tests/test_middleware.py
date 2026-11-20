import httpx
from asgi_lifespan import LifespanManager

from app.main import create_app


async def _client(make_settings, **overrides):
    app = create_app(make_settings(**overrides))
    manager = LifespanManager(app)
    await manager.__aenter__()
    c = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    return c, manager


async def test_request_id_header(make_settings, fake_llm):
    c, m = await _client(make_settings)
    try:
        r = await c.get("/health")
        assert len(r.headers["X-Request-ID"]) >= 8
        r = await c.get("/health", headers={"X-Request-ID": "abc123"})
        assert r.headers["X-Request-ID"] == "abc123"
    finally:
        await c.aclose()
        await m.__aexit__(None, None, None)


async def test_rate_limit_is_json_429_and_only_on_chat(make_settings, fake_llm):
    c, m = await _client(make_settings, rate_limit_per_minute=2)
    try:
        for i in range(2):
            assert (await c.post("/chat", json={"session_id": "rl", "message": f"m{i}"})).status_code == 200
        r = await c.post("/chat", json={"session_id": "rl", "message": "m3"})
        assert r.status_code == 429
        assert r.json() == {"detail": "rate limit exceeded"}
        assert int(r.headers["Retry-After"]) >= 1
        # other clients and other endpoints unaffected
        other = await c.post(
            "/chat", json={"session_id": "rl2", "message": "x"}, headers={"X-Forwarded-For": "9.9.9.9"}
        )
        assert other.status_code == 200
        assert (await c.get("/health")).status_code == 200
    finally:
        await c.aclose()
        await m.__aexit__(None, None, None)


async def test_docs_enabled(make_settings, fake_llm):
    c, m = await _client(make_settings)
    try:
        assert (await c.get("/docs")).status_code == 200
        paths = set((await c.get("/openapi.json")).json()["paths"])
        assert paths == {"/health", "/chat", "/sessions/{session_id}/messages"}
    finally:
        await c.aclose()
        await m.__aexit__(None, None, None)
