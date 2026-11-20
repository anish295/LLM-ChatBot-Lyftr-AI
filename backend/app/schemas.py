"""Request / response models. Field names match the assignment contract exactly."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

MAX_MESSAGE_CHARS = 4000
MAX_SESSION_ID_CHARS = 128
MAX_SYSTEM_PROMPT_CHARS = 4000

# strip_whitespace runs before the length checks, so "   " fails min_length=1
# and the stripped text is what reaches the LLM and the database.
MessageText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_MESSAGE_CHARS)
]
SessionId = Annotated[str, StringConstraints(min_length=1, max_length=MAX_SESSION_ID_CHARS)]


class ChatRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"session_id": "s-7f3a", "message": "What is the capital of France?"}]
        }
    )

    session_id: SessionId = Field(description="Client-generated id, 1-128 chars. Unknown id starts a session.")
    message: MessageText = Field(description="User message, 1-4000 chars after trimming whitespace.")
    system_prompt: str | None = Field(
        default=None,
        max_length=MAX_SYSTEM_PROMPT_CHARS,
        description="Optional; overrides the default system prompt for this session.",
    )

    @field_validator("session_id")
    @classmethod
    def _session_id_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("session_id must not be blank")
        return value

    @field_validator("system_prompt")
    @classmethod
    def _normalize_system_prompt(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class ChatMetadata(BaseModel):
    resolution_source: Literal["LIVE_INFERENCE", "LLM_CACHE"]
    model: str
    latency_ms: int
    input_tokens: int
    output_tokens: int
    key_id: str | None
    fallback_attempts: int


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    metadata: ChatMetadata


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    metadata: dict[str, Any] | None = Field(default=None, description="Assistant messages only.")


class HistoryResponse(BaseModel):
    session_id: str
    messages: list[HistoryMessage]


class HealthResponse(BaseModel):
    status: Literal["ok"]
    keys_configured: int
    cache_enabled: bool


class ErrorResponse(BaseModel):
    detail: Any
