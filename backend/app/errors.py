"""JSON-only error handling: every error body is {"detail": ...}, never a stack trace or HTML."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("app.errors")


def _clean_validation_errors(exc: RequestValidationError) -> list[dict]:
    """FastAPI's default 422 shape (type/loc/msg), minus echoed input and ctx objects."""
    cleaned = []
    for err in exc.errors():
        cleaned.append(
            {
                "type": err.get("type"),
                "loc": list(err.get("loc", ())),
                "msg": err.get("msg"),
            }
        )
    return cleaned


async def validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": _clean_validation_errors(exc)})


async def http_exception_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=getattr(exc, "headers", None),
    )


class CatchAllMiddleware(BaseHTTPMiddleware):
    """Last line of defence: any unhandled exception becomes a JSON 500.

    Registered *inside* the CORS middleware so even a 500 carries CORS headers and
    the browser shows our message instead of an opaque network error. The trace
    is logged server-side only.
    """

    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except Exception:  # noqa: BLE001
            logger.exception("unhandled error", extra={"path": request.url.path, "method": request.method})
            return JSONResponse(status_code=500, content={"detail": "internal server error"})


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, validation_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
