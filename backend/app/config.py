"""Application settings, loaded exclusively from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

_TRUE = {"1", "true", "yes", "on"}


def _env(name: str, default: str = "") -> str:
    value = os.getenv(name)
    return default if value is None else value.strip()


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in _TRUE


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)))
    except ValueError:
        return default


def _split_csv(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def normalize_origin(origin: str) -> str:
    """CORS origins are compared exactly; strip trailing slashes users often paste."""
    return origin.strip().rstrip("/")


def sqlite_path_from_url(url: str) -> str:
    """Translate a SQLAlchemy-style SQLite URL into a filesystem path.

    sqlite:////data/app.db -> /data/app.db (absolute)
    sqlite:///./app.db     -> ./app.db     (relative)
    sqlite:///:memory:     -> :memory:
    A bare path is accepted as-is.
    """
    url = url.strip()
    for prefix in ("sqlite+aiosqlite:///", "sqlite:///"):
        if url.startswith(prefix):
            return url[len(prefix):] or "app.db"
    if url.startswith("sqlite://"):
        return url[len("sqlite://"):] or "app.db"
    return url or "app.db"


@dataclass(frozen=True)
class Settings:
    llm_model: str = "groq/openai/gpt-oss-120b"
    llm_api_keys: tuple[str, ...] = ()
    database_url: str = "sqlite:///./data/app.db"
    allowed_origins: tuple[str, ...] = ("http://localhost:3000",)
    enable_failure_simulation: bool = False
    default_system_prompt: str = "You are a helpful, concise assistant."
    cache_type: str = "disk"
    cache_dir: str = "./data/llm_cache"
    cache_ttl_seconds: int = 0
    llm_timeout_seconds: float = 30.0
    llm_temperature: float = 0.0
    llm_max_tokens: int = 1024
    llm_reasoning_effort: str = ""
    key_cooldown_seconds: float = 30.0
    rate_limit_per_minute: int = 120
    log_level: str = "INFO"
    extra: dict = field(default_factory=dict)

    @property
    def database_path(self) -> str:
        return sqlite_path_from_url(self.database_url)

    @property
    def key_ids(self) -> list[str]:
        return [f"key_{i + 1}" for i in range(len(self.llm_api_keys))]

    @classmethod
    def from_env(cls) -> "Settings":
        origins = tuple(
            normalize_origin(o)
            for o in _split_csv(_env("ALLOWED_ORIGINS", "http://localhost:3000"))
        )
        default_data = Path("/data") if Path("/data").is_dir() else Path("./data")
        return cls(
            llm_model=_env("LLM_MODEL", cls.llm_model) or cls.llm_model,
            llm_api_keys=tuple(_split_csv(_env("LLM_API_KEYS"))),
            database_url=_env("DATABASE_URL", f"sqlite:///{(default_data / 'app.db').as_posix()}"),
            allowed_origins=origins,
            enable_failure_simulation=_env_bool("ENABLE_FAILURE_SIMULATION", False),
            default_system_prompt=_env("DEFAULT_SYSTEM_PROMPT", cls.default_system_prompt)
            or cls.default_system_prompt,
            cache_type=(_env("CACHE_TYPE", "disk") or "disk").lower(),
            cache_dir=_env("CACHE_DIR", (default_data / "llm_cache").as_posix()),
            cache_ttl_seconds=max(0, _env_int("CACHE_TTL_SECONDS", 0)),
            llm_timeout_seconds=_env_float("LLM_TIMEOUT_SECONDS", 30.0),
            llm_temperature=_env_float("LLM_TEMPERATURE", 0.0),
            llm_max_tokens=_env_int("LLM_MAX_TOKENS", 1024),
            llm_reasoning_effort=_env("LLM_REASONING_EFFORT", "").lower(),
            key_cooldown_seconds=max(0.0, _env_float("KEY_COOLDOWN_SECONDS", 30.0)),
            rate_limit_per_minute=max(0, _env_int("RATE_LIMIT_PER_MINUTE", 120)),
            log_level=(_env("LOG_LEVEL", "INFO") or "INFO").upper(),
        )
