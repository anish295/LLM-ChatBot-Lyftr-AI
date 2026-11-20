"""LiteLLM gateway: key pool, automatic failover, and response caching.

Failover policy (deterministic, documented in the README):
  * Keys are always tried in pool order, starting at key_1.
  * Any provider failure on a key (429 / quota, 5xx, timeout, connection error,
    401/403 dead key, empty reply, ...) counts as one failed attempt and the next
    key is tried. The loop is bounded by the pool size, so it can never spin.
  * If every key fails -> AllProvidersUnavailable (mapped to HTTP 503).
  * Key cooldown (circuit breaker): after a *real* 429/401/403 a key is skipped for
    KEY_COOLDOWN_SECONDS. Skipped keys count as failed attempts; if every key is
    cooling down they are still tried as a last resort. Simulated requests neither
    read nor write cooldown state, so the X-Simulate-Failure contract always holds.

Caching: LiteLLM's built-in cache is enabled globally (see cache.py) and each call
passes caching=True. The cache key is derived by LiteLLM from model + messages +
sampling params; api_key is NOT part of it (verified by tests), so a response
produced by key_1 is served to any later identical request regardless of key.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import litellm

from .config import Settings

logger = logging.getLogger("app.gateway")

litellm.drop_params = True  # silently drop params a provider does not support
litellm.suppress_debug_info = True

SIMULATABLE_STATUSES = (429, 500, 502, 503)

# Statuses after which a key is put on cooldown (only for real, non-simulated failures).
_COOLDOWN_STATUSES = {401, 403, 429}


class AllProvidersUnavailable(Exception):
    """Every key in the pool failed for this request."""


class EmptyReplyError(Exception):
    """The provider answered but with no usable text; treated as a failed attempt."""

    status_code = 502


@dataclass
class LLMResult:
    reply: str
    model: str
    input_tokens: int
    output_tokens: int
    key_id: str | None
    fallback_attempts: int
    cache_hit: bool


def provider_of(model: str) -> str:
    return model.split("/", 1)[0] if "/" in model else "openai"


def make_simulated_error(status: int, model: str, key_id: str) -> Exception:
    """Build the exact LiteLLM exception a provider failure with this status raises."""
    provider = provider_of(model)
    message = f"Simulated HTTP {status} for {key_id} (X-Simulate-Failure)"
    if status == 429:
        return litellm.RateLimitError(message=message, llm_provider=provider, model=model)
    if status == 500:
        return litellm.InternalServerError(message=message, llm_provider=provider, model=model)
    if status == 503:
        return litellm.ServiceUnavailableError(message=message, llm_provider=provider, model=model)
    return litellm.APIError(status_code=status, message=message, llm_provider=provider, model=model)


def _status_of(exc: Exception) -> int | None:
    status = getattr(exc, "status_code", None)
    try:
        return int(status) if status is not None else None
    except (TypeError, ValueError):
        return None


class LLMGateway:
    def __init__(self, settings: Settings, cache_enabled: bool = True) -> None:
        self.settings = settings
        self.model = settings.llm_model
        self._keys: list[tuple[str, str]] = [
            (f"key_{i + 1}", key) for i, key in enumerate(settings.llm_api_keys)
        ]
        self.cache_enabled = cache_enabled
        self._cooldown_until: dict[str, float] = {}

    # ------------------------------------------------------------------ helpers
    @property
    def keys_configured(self) -> int:
        return len(self._keys)

    @property
    def key_ids(self) -> list[str]:
        return [key_id for key_id, _ in self._keys]

    def _redact(self, text: str) -> str:
        """Remove any raw key from text before it reaches a log line."""
        for _, key in self._keys:
            if key and key in text:
                text = text.replace(key, "***")
        return text

    def _in_cooldown(self, key_id: str) -> bool:
        until = self._cooldown_until.get(key_id)
        return until is not None and until > time.monotonic()

    def _start_cooldown(self, key_id: str) -> None:
        if self.settings.key_cooldown_seconds > 0:
            self._cooldown_until[key_id] = time.monotonic() + self.settings.key_cooldown_seconds

    def _build_kwargs(self, api_key: str, messages: list[dict[str, str]], bypass_cache: bool) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "api_key": api_key,
            "temperature": self.settings.llm_temperature,
            "max_tokens": self.settings.llm_max_tokens,
            "timeout": self.settings.llm_timeout_seconds,
            "num_retries": 0,  # failover is ours; never retry the same key inside LiteLLM
            "caching": self.cache_enabled,
        }
        if self.settings.llm_reasoning_effort:
            kwargs["reasoning_effort"] = self.settings.llm_reasoning_effort
        if bypass_cache:
            # Skip the cache *read*; a fresh live answer is still stored.
            kwargs["cache"] = {"no-cache": True}
        return kwargs

    async def _store_in_cache(self, response: Any, kwargs: dict[str, Any]) -> None:
        """Write a live answer to LiteLLM's cache *before* we respond.

        LiteLLM normally stores responses from a background logging task, i.e. a few
        ms after the call returns. A client firing the identical request right away
        could then miss the cache. Writing synchronously through the same
        ``litellm.cache`` API (same key derivation) removes that race; LiteLLM's own
        later write is an idempotent overwrite of the same entry.
        """
        if not self.cache_enabled or litellm.cache is None:
            return
        try:
            store_kwargs = {k: v for k, v in kwargs.items() if k != "cache"}
            await litellm.cache.async_add_cache(response, **store_kwargs)
        except Exception:  # noqa: BLE001 - caching must never break a reply
            logger.warning("cache write failed", extra={"event": "cache_write_failed"}, exc_info=True)

    def _to_result(
        self, response: Any, messages: list[dict[str, str]], key_id: str, failures: int
    ) -> LLMResult:
        try:
            content = response.choices[0].message.content
        except (AttributeError, IndexError, KeyError):
            content = None
        reply = (content or "").strip()
        if not reply:
            raise EmptyReplyError("provider returned an empty reply")

        hidden = getattr(response, "_hidden_params", None) or {}
        cache_hit = bool(hidden.get("cache_hit"))

        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "prompt_tokens", None) if usage else None
        output_tokens = getattr(usage, "completion_tokens", None) if usage else None
        if input_tokens is None:
            input_tokens = litellm.token_counter(model=self.model, messages=messages)
        if output_tokens is None:
            output_tokens = litellm.token_counter(model=self.model, text=reply)

        return LLMResult(
            reply=reply,
            model=self.model,
            input_tokens=int(input_tokens),
            output_tokens=int(output_tokens),
            key_id=None if cache_hit else key_id,
            fallback_attempts=0 if cache_hit else failures,
            cache_hit=cache_hit,
        )

    # --------------------------------------------------------------- main entry
    async def complete(
        self,
        messages: list[dict[str, str]],
        simulated_failures: dict[str, int] | None = None,
    ) -> LLMResult:
        """Run the failover loop.

        simulated_failures: None when no simulation was requested. Otherwise a map
        key_id -> HTTP status for this request only (may be empty if the header named
        no configured key). Any simulated request bypasses the cache read.
        """
        simulating = simulated_failures is not None
        simulated = simulated_failures or {}
        bypass_cache = simulating
        failures = 0
        deferred: list[tuple[str, str]] = []

        for key_id, api_key in self._keys:
            if not simulating and self._in_cooldown(key_id):
                failures += 1
                deferred.append((key_id, api_key))
                logger.warning("key skipped (cooldown)", extra={"key_id": key_id, "event": "key_cooldown_skip"})
                continue
            result, bypass_cache = await self._attempt(
                key_id, api_key, messages, simulated.get(key_id), bypass_cache, failures, simulating
            )
            if result is not None:
                return result
            failures += 1

        # Last resort: keys that were only skipped because of cooldown. By now every
        # other key has failed or is cooling down, so they all count as attempts.
        for key_id, api_key in deferred:
            result, bypass_cache = await self._attempt(
                key_id, api_key, messages, None, bypass_cache, len(self._keys) - 1, simulating
            )
            if result is not None:
                return result

        logger.error(
            "all providers unavailable",
            extra={"event": "all_keys_failed", "keys": len(self._keys), "simulated": simulating},
        )
        raise AllProvidersUnavailable("all providers unavailable")

    async def _attempt(
        self,
        key_id: str,
        api_key: str,
        messages: list[dict[str, str]],
        simulated_status: int | None,
        bypass_cache: bool,
        failures_so_far: int,
        simulating: bool,
    ) -> tuple[LLMResult | None, bool]:
        """One call on one key. Returns (result or None on failure, bypass_cache)."""
        try:
            if simulated_status is not None:
                raise make_simulated_error(simulated_status, self.model, key_id)
            kwargs = self._build_kwargs(api_key, messages, bypass_cache)
            response = await litellm.acompletion(**kwargs)
            result = self._to_result(response, messages, key_id, failures_so_far)
            if not result.cache_hit:
                await self._store_in_cache(response, kwargs)
        except Exception as exc:  # noqa: BLE001 - every provider failure fails over
            status = _status_of(exc)
            if isinstance(exc, EmptyReplyError):
                # An empty answer may have been cached; never serve it again.
                bypass_cache = True
            if not simulating and status in _COOLDOWN_STATUSES:
                self._start_cooldown(key_id)
            logger.warning(
                "key failed, failing over",
                extra={
                    "event": "key_failover",
                    "key_id": key_id,
                    "status": status,
                    "error_type": type(exc).__name__,
                    "simulated": simulated_status is not None,
                    "detail": self._redact(str(exc))[:300],
                },
            )
            return None, bypass_cache
        logger.info(
            "llm call succeeded",
            extra={
                "event": "llm_success",
                "key_id": result.key_id,
                "cache_hit": result.cache_hit,
                "fallback_attempts": result.fallback_attempts,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
            },
        )
        return result, bypass_cache
