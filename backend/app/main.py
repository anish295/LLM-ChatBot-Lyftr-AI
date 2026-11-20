"""FastAPI application entrypoint.

Public API (exactly three endpoints): GET /health, POST /chat,
GET /sessions/{session_id}/messages. FastAPI's /docs and /openapi.json are kept
for reviewers.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import router
from .cache import setup_cache
from .config import Settings
from .db import Database
from .errors import CatchAllMiddleware, install_error_handlers
from .llm_gateway import LLMGateway
from .logging_config import configure_logging
from .middleware import RateLimitMiddleware, RequestIdMiddleware
from .session_locks import SessionLocks

logger = logging.getLogger("app")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db = Database(settings.database_path)
        await db.connect()
        app.state.db = db
        app.state.cache_type = setup_cache(settings)
        app.state.gateway = LLMGateway(settings, cache_enabled=True)
        app.state.session_locks = SessionLocks()
        if len(settings.llm_api_keys) < 2:
            logger.warning("key pool has fewer than 2 keys; failover needs at least 2",
                           extra={"keys_configured": len(settings.llm_api_keys)})
        logger.info(
            "startup complete",
            extra={
                "model": settings.llm_model,
                "keys_configured": len(settings.llm_api_keys),
                "cache_type": app.state.cache_type,
                "failure_simulation": settings.enable_failure_simulation,
                "allowed_origins": list(settings.allowed_origins),
                "allowed_origin_regex": settings.allowed_origin_regex,
            },
        )
        try:
            yield
        finally:
            # Graceful shutdown: uvicorn stops accepting requests and drains in-flight
            # ones (--timeout-graceful-shutdown), then we close the DB cleanly.
            await db.close()
            logger.info("shutdown complete")

    app = FastAPI(
        title="LLM Chatbot with Key Failover and Response Caching",
        description=(
            "FastAPI + LiteLLM gateway with an API-key pool, automatic failover on 429/quota/5xx, "
            "LiteLLM response caching (LLM_CACHE vs LIVE_INFERENCE), per-request token tracking and "
            "SQLite session history. Send `X-Simulate-Failure: key_1=429` to POST /chat to see failover."
        ),
        version="1.0.0",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.include_router(router)
    install_error_handlers(app)
    # Middleware order: last added = outermost.
    # CORS -> request id/access log -> rate limit -> catch-all 500 -> routes
    app.add_middleware(CatchAllMiddleware)
    app.add_middleware(RateLimitMiddleware, per_minute=settings.rate_limit_per_minute)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allowed_origins),
        allow_origin_regex=settings.allowed_origin_regex or None,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Failure-Simulation", "X-Request-ID"],
    )
    return app


app = create_app()
