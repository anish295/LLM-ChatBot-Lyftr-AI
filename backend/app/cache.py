"""LiteLLM built-in response cache setup.

CACHE_TYPE=disk  -> litellm Cache(type="disk") backed by diskcache under CACHE_DIR
                    (on the /data volume, so cached answers survive restarts).
CACHE_TYPE=local -> litellm in-memory cache.
If the disk cache cannot be created (read-only FS, missing dir, ...) we fall back
to the in-memory cache instead of crashing: resilience over persistence.
"""

from __future__ import annotations

import logging
from pathlib import Path

import litellm
from litellm.caching.caching import Cache

from .config import Settings

logger = logging.getLogger("app.cache")

_CALL_TYPES = ["acompletion", "completion"]


def setup_cache(settings: Settings) -> str:
    """Install the global LiteLLM cache. Returns the effective cache type."""
    ttl = settings.cache_ttl_seconds or None
    if settings.cache_type == "disk":
        try:
            Path(settings.cache_dir).mkdir(parents=True, exist_ok=True)
            litellm.cache = Cache(
                type="disk",
                disk_cache_dir=settings.cache_dir,
                ttl=ttl,
                supported_call_types=_CALL_TYPES,
            )
            logger.info("llm cache ready", extra={"cache_type": "disk", "cache_dir": settings.cache_dir})
            return "disk"
        except Exception:  # noqa: BLE001
            logger.exception("disk cache unavailable, falling back to in-memory cache")
    litellm.cache = Cache(type="local", ttl=ttl, supported_call_types=_CALL_TYPES)
    logger.info("llm cache ready", extra={"cache_type": "local"})
    return "local"


def cache_enabled() -> bool:
    return litellm.cache is not None
