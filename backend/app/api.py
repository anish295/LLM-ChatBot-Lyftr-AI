"""The three public endpoints: GET /health, POST /chat, GET /sessions/{id}/messages."""

from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException, Request

from .config import Settings
from .db import Database
from .llm_gateway import AllProvidersUnavailable, LLMGateway
from .schemas import ChatMetadata, ChatRequest, ChatResponse, ErrorResponse
from .session_locks import SessionLocks

router = APIRouter()

ALL_UNAVAILABLE = "all providers unavailable"


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

    async with _locks(request).hold(body.session_id):
        stored_prompt = await db.get_system_prompt(body.session_id)
        system_prompt = body.system_prompt or stored_prompt or settings.default_system_prompt
        history = await db.get_history(body.session_id)
        messages = [{"role": "system", "content": system_prompt}]
        messages += [{"role": m["role"], "content": m["content"]} for m in history]
        messages.append({"role": "user", "content": body.message})

        try:
            result = await _gateway(request).complete(messages)
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
