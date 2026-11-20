"""The three public endpoints: GET /health, POST /chat, GET /sessions/{id}/messages."""

from __future__ import annotations

import time

import litellm
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from .config import Settings
from .db import Database
from .llm_gateway import AllProvidersUnavailable, LLMGateway
from .schemas import ChatMetadata, ChatRequest, ChatResponse, ErrorResponse, HealthResponse, HistoryResponse
from .session_locks import SessionLocks
from .simulation import HEADER_NAME, parse_simulation_header

router = APIRouter()

ALL_UNAVAILABLE = "all providers unavailable"
SESSION_NOT_FOUND = "session not found"


def _db(request: Request) -> Database:
    return request.app.state.db


def _gateway(request: Request) -> LLMGateway:
    return request.app.state.gateway


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _locks(request: Request) -> SessionLocks:
    return request.app.state.session_locks


@router.post(
    "/chat",
    response_model=ChatResponse,
    responses={422: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
    summary="Send a message; returns the reply plus per-request metadata",
)
async def chat(body: ChatRequest, request: Request) -> ChatResponse:
    # Body is already validated here; latency covers all request handling after it.
    started = time.perf_counter()
    settings = _settings(request)
    db = _db(request)
    gateway = _gateway(request)
    simulated = (
        parse_simulation_header(request.headers.get(HEADER_NAME), gateway.key_ids)
        if settings.enable_failure_simulation
        else None  # switch off -> header is ignored entirely
    )

    async with _locks(request).hold(body.session_id):
        stored_prompt = await db.get_system_prompt(body.session_id)
        system_prompt = body.system_prompt or stored_prompt or settings.default_system_prompt
        history = await db.get_history(body.session_id)
        messages = [{"role": "system", "content": system_prompt}]
        messages += [{"role": m["role"], "content": m["content"]} for m in history]
        messages.append({"role": "user", "content": body.message})

        try:
            result = await gateway.complete(messages, simulated_failures=simulated)
        except AllProvidersUnavailable:
            # Nothing has been written for this turn, so history is untouched.
            raise HTTPException(status_code=503, detail=ALL_UNAVAILABLE) from None

        metadata = ChatMetadata(
            resolution_source="LLM_CACHE" if result.cache_hit else "LIVE_INFERENCE",
            model=result.model,
            latency_ms=int((time.perf_counter() - started) * 1000),
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            key_id=result.key_id,
            fallback_attempts=result.fallback_attempts,
        )
        # User message + reply are inserted together, only after success.
        await db.save_exchange(
            body.session_id, body.message, result.reply, metadata.model_dump(), body.system_prompt
        )

    return ChatResponse(session_id=body.session_id, reply=result.reply, metadata=metadata)


@router.get(
    "/health",
    response_model=HealthResponse,
    responses={503: {"model": ErrorResponse}},
    summary="Liveness + readiness: app up, DB reachable, key pool loaded",
)
async def health(request: Request):
    db_ok = await _db(request).ping()
    keys = _gateway(request).keys_configured
    cache_on = litellm.cache is not None
    if db_ok and keys > 0:
        return HealthResponse(status="ok", keys_configured=keys, cache_enabled=cache_on)
    return JSONResponse(
        status_code=503,
        content={
            "detail": "database unreachable" if not db_ok else "no API keys configured",
            "status": "unavailable",
            "keys_configured": keys,
            "cache_enabled": cache_on,
        },
    )


@router.get(
    "/sessions/{session_id}/messages",
    response_model=None,
    responses={200: {"model": HistoryResponse}, 404: {"model": ErrorResponse}},
    summary="Stored history of one session, oldest first, without the system prompt",
)
async def session_messages(session_id: str, request: Request):
    db = _db(request)
    if not await db.session_exists(session_id):
        raise HTTPException(status_code=404, detail=SESSION_NOT_FOUND)
    return {"session_id": session_id, "messages": await db.get_history(session_id)}
