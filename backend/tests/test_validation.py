"""422 validation and JSON-only error bodies."""

import httpx
import pytest
from asgi_lifespan import LifespanManager

from app.main import create_app


@pytest.fixture
async def client(make_settings, fake_llm):
    app = create_app(make_settings())
    async with LifespanManager(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            c.app = app
            yield c


def _assert_json_detail(r, status):
    assert r.status_code == status, r.text
    assert r.headers["content-type"].startswith("application/json")
    body = r.json()
    assert "detail" in body
    assert "Traceback" not in r.text and "<html" not in r.text.lower()


@pytest.mark.parametrize(
    "payload",
    [
        {"session_id": "s-1", "message": ""},
        {"session_id": "s-1", "message": "   \n\t "},
        {"session_id": "s-1", "message": "x" * 4001},
        {"session_id": "s-1", "message": "  " + "x" * 4001 + "  "},
        {"session_id": "s-1"},
        {"message": "hello"},
        {"session_id": "", "message": "hello"},
        {"session_id": "   ", "message": "hello"},
        {"session_id": "s" * 129, "message": "hello"},
        {"session_id": "s-1", "message": 123},
        {"session_id": 42, "message": "hello"},
        {"session_id": "s-1", "message": None},
        {},
        [],
        "just a string",
    ],
)
async def test_invalid_payloads_are_422(client, payload):
    r = await client.post("/chat", json=payload)
    _assert_json_detail(r, 422)


async def test_validation_error_lists_field(client):
    r = await client.post("/chat", json={"session_id": "s-1", "message": "  "})
    assert any(err["loc"][-1] == "message" for err in r.json()["detail"])


@pytest.mark.parametrize(
    ("content", "content_type"),
    [
        ('{"session_id": "s-1", "message": ', "application/json"),
        ("not json at all", "application/json"),
        ("", "application/json"),
        ("{'single': 'quotes'}", "application/json"),
        ('{"session_id": "s-1", "message": "hi"}', "text/plain"),
    ],
)
async def test_malformed_json_is_422(client, content, content_type):
    r = await client.post("/chat", content=content, headers={"content-type": content_type})
    _assert_json_detail(r, 422)


async def test_boundaries_accepted(client):
    r = await client.post("/chat", json={"session_id": "s" * 128, "message": "x" * 4000})
    assert r.status_code == 200
    r = await client.post("/chat", json={"session_id": "a", "message": "  y  ", "extra_field": 1})
    assert r.status_code == 200


async def test_failed_validation_stores_nothing(client):
    await client.post("/chat", json={"session_id": "s-v", "message": ""})
    assert (await client.get("/sessions/s-v/messages")).status_code == 404


async def test_unknown_route_and_method_are_json(client):
    _assert_json_detail(await client.get("/nope"), 404)
    _assert_json_detail(await client.get("/chat"), 405)


async def test_unexpected_exception_is_json_500_with_cors(client, monkeypatch):
    async def boom(*args, **kwargs):
        raise RuntimeError("secret internals")

    monkeypatch.setattr(client.app.state.gateway, "complete", boom)
    r = await client.post(
        "/chat",
        json={"session_id": "s-500", "message": "hello"},
        headers={"Origin": "http://localhost:3000"},
    )
    _assert_json_detail(r, 500)
    assert r.json() == {"detail": "internal server error"}
    assert "secret internals" not in r.text
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"


async def test_cors_preflight_allows_simulation_header(client):
    r = await client.options(
        "/chat",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-simulate-failure",
        },
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "x-simulate-failure" in r.headers["access-control-allow-headers"].lower()


async def test_cors_rejects_unknown_origin(client):
    r = await client.get("/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in r.headers


async def test_cors_origin_regex_allows_netlify_deploy_urls_only(make_settings, fake_llm):
    regex = r"https://([a-z0-9]+--)?lyftr-llm-chatbot\.netlify\.app"
    app = create_app(make_settings(allowed_origin_regex=regex))
    async with LifespanManager(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            for origin, allowed in [
                ("https://lyftr-llm-chatbot.netlify.app", True),
                ("https://6b007d25c20f9e9a36919bdb--lyftr-llm-chatbot.netlify.app", True),
                ("http://localhost:3000", True),  # exact list still applies
                ("https://evil-lyftr-llm-chatbot.netlify.app", False),
                ("https://lyftr-llm-chatbot.netlify.app.evil.com", False),
            ]:
                r = await c.get("/health", headers={"Origin": origin})
                assert (r.headers.get("access-control-allow-origin") == origin) is allowed, origin
