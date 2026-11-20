"""Request id + access log, and a lightweight per-IP rate limiter for POST /chat."""

from __future__ import annotations

import logging
import time
import uuid
from collections import deque

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .logging_config import request_id_var

access_log = logging.getLogger("app.access")


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Attach X-Request-ID (honouring a sane incoming one) and emit one JSON access log line."""

    async def dispatch(self, request: Request, call_next):
        incoming = request.headers.get("X-Request-ID", "")
        rid = incoming if 0 < len(incoming) <= 64 and incoming.isprintable() else uuid.uuid4().hex[:16]
        token = request_id_var.set(rid)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["X-Request-ID"] = rid
        access_log.info(
            "request",
            extra={
                "request_id": rid,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": int((time.perf_counter() - started) * 1000),
            },
        )
        return response


def client_ip(request: Request) -> str:
    # Behind Render/Vercel-style proxies the first X-Forwarded-For hop is the client.
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window limit on POST /chat per client IP (in memory, per process).

    Deliberately generous (RATE_LIMIT_PER_MINUTE, default 120) - it exists to stop a
    runaway client from burning the free-tier LLM quota, not to throttle graders.
    0 disables it. /health and history reads are never limited.
    """

    def __init__(self, app, per_minute: int) -> None:
        super().__init__(app)
        self.per_minute = per_minute
        self.window = 60.0
        self._hits: dict[str, deque[float]] = {}

    async def dispatch(self, request: Request, call_next):
        if self.per_minute <= 0 or request.method != "POST" or request.url.path != "/chat":
            return await call_next(request)
        now = time.monotonic()
        ip = client_ip(request)
        hits = self._hits.setdefault(ip, deque())
        while hits and now - hits[0] > self.window:
            hits.popleft()
        if len(hits) >= self.per_minute:
            retry_after = max(1, int(self.window - (now - hits[0])) + 1)
            return JSONResponse(
                status_code=429,
                content={"detail": "rate limit exceeded"},
                headers={"Retry-After": str(retry_after)},
            )
        hits.append(now)
        if len(self._hits) > 10_000:  # bound memory: drop idle clients
            for key in [k for k, v in self._hits.items() if not v or now - v[-1] > self.window]:
                del self._hits[key]
        return await call_next(request)
