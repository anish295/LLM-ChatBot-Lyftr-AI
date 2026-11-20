"""Shared fixtures.

The fake provider patches ``litellm.acompletion`` with a wrapper that still calls
the *real* LiteLLM function, but with ``mock_response`` set. That means LiteLLM's
real caching layer runs (key derivation, cache hits, ``_hidden_params``) while no
network request is ever made. Per-key behaviour (ok / exception / empty) is
scripted by api_key.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import litellm
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Real provider config is kept aside for the opt-in live test (tests/test_live.py) ...
LIVE_ENV = {var: os.environ.get(var) for var in ("LLM_API_KEYS", "LLM_MODEL", "LLM_REASONING_EFFORT")}
# ... and a developer's real .env never leaks into the unit tests.
for var in ("LLM_API_KEYS", "ENABLE_FAILURE_SIMULATION", "DATABASE_URL", "CACHE_DIR", "CACHE_TYPE"):
    os.environ.pop(var, None)

from app.config import Settings  # noqa: E402

TEST_KEYS = ("sk-test-AAAA1111", "sk-test-BBBB2222")


def count_tokens(messages: list[dict[str, str]]) -> int:
    """Deterministic fake tokenizer: words + 4 per message envelope."""
    return sum(len(m["content"].split()) + 4 for m in messages)


@dataclass
class FakeProvider:
    behaviours: dict[str, Any] = field(default_factory=dict)  # api_key -> "ok" | "empty" | Exception
    calls: list[str] = field(default_factory=list)  # api_keys actually sent to LiteLLM
    delay: float = 0.08  # simulated live latency (skipped on cache hits by LiteLLM)

    def reply_for(self, messages: list[dict[str, str]]) -> str:
        last = messages[-1]["content"]
        turn = sum(1 for m in messages if m["role"] == "user")
        context = " | ".join(m["content"] for m in messages if m["role"] == "user")
        return f"Echo turn {turn}: {last} [context: {context}]"

    async def __call__(self, **kwargs: Any):
        api_key = kwargs.get("api_key")
        self.calls.append(api_key)
        behaviour = self.behaviours.get(api_key, "ok")
        messages = kwargs["messages"]
        if isinstance(behaviour, Exception):
            raise behaviour
        reply = "" if behaviour == "empty" else self.reply_for(messages)
        kwargs["mock_response"] = {
            "id": "chatcmpl-fake",
            "object": "chat.completion",
            "model": kwargs["model"].split("/", 1)[-1],
            "choices": [
                {"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": reply}}
            ],
            "usage": {
                "prompt_tokens": count_tokens(messages),
                "completion_tokens": len(reply.split()),
                "total_tokens": count_tokens(messages) + len(reply.split()),
            },
        }
        kwargs["mock_delay"] = self.delay
        return await _REAL_ACOMPLETION(**kwargs)


_REAL_ACOMPLETION = litellm.acompletion


@pytest.fixture
def fake_llm(monkeypatch) -> FakeProvider:
    fake = FakeProvider()
    monkeypatch.setattr(litellm, "acompletion", fake)
    return fake


@pytest.fixture
def make_settings(tmp_path):
    def _make(**overrides: Any) -> Settings:
        base = dict(
            llm_model="groq/test-model",
            llm_api_keys=TEST_KEYS,
            database_url=f"sqlite:///{(tmp_path / 'data' / 'app.db').as_posix()}",
            allowed_origins=("http://localhost:3000",),
            enable_failure_simulation=True,
            default_system_prompt="You are a helpful, concise assistant.",
            cache_type="disk",
            cache_dir=(tmp_path / "data" / "llm_cache").as_posix(),
            key_cooldown_seconds=0,
            rate_limit_per_minute=0,
            log_level="WARNING",
        )
        base.update(overrides)
        return Settings(**base)

    return _make


@pytest.fixture(autouse=True)
def _reset_litellm_cache():
    yield
    litellm.cache = None
