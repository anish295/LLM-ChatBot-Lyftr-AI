"""Optional live smoke test against the real provider.

Runs only when LLM_API_KEYS (2+ real keys) is set in the environment, e.g.
    LLM_API_KEYS=k1,k2 LLM_MODEL=groq/openai/gpt-oss-120b pytest -m live
"""

import uuid

import httpx
import pytest
from asgi_lifespan import LifespanManager

from app.main import create_app
from tests.conftest import LIVE_ENV

KEYS = tuple(k.strip() for k in (LIVE_ENV["LLM_API_KEYS"] or "").split(",") if k.strip())

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        len(KEYS) < 2 or any(k.startswith("your_") for k in KEYS),
        reason="needs 2+ real keys in LLM_API_KEYS",
    ),
]


async def test_live_end_to_end(make_settings):
    overrides = {"llm_api_keys": KEYS, "llm_timeout_seconds": 60.0}
    if LIVE_ENV["LLM_MODEL"]:
        overrides["llm_model"] = LIVE_ENV["LLM_MODEL"]
    if LIVE_ENV["LLM_REASONING_EFFORT"]:
        overrides["llm_reasoning_effort"] = LIVE_ENV["LLM_REASONING_EFFORT"]
    app = create_app(make_settings(**overrides))
    question = f"Reply with the single word OK. ({uuid.uuid4().hex[:6]})"
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t", timeout=120) as c:
            live = await c.post("/chat", json={"session_id": "live-1", "message": question})
            assert live.status_code == 200, live.text
            assert live.json()["metadata"]["resolution_source"] == "LIVE_INFERENCE"
            hit = await c.post("/chat", json={"session_id": "live-2", "message": question})
            assert hit.json()["metadata"]["resolution_source"] == "LLM_CACHE"
            assert hit.json()["reply"] == live.json()["reply"]
            assert hit.json()["metadata"]["latency_ms"] < live.json()["metadata"]["latency_ms"]
            fo = await c.post(
                "/chat",
                json={"session_id": "live-3", "message": question},
                headers={"X-Simulate-Failure": "key_1=429"},
            )
            assert fo.status_code == 200, fo.text
            assert fo.json()["metadata"]["key_id"] == "key_2"
