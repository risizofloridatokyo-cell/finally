"""Structured-output schema for the FinAlly assistant (PLAN §9) and the chat HTTP models."""

from __future__ import annotations

import json
import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

_FENCE_RE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL | re.IGNORECASE)


class TradeInstruction(BaseModel):
    ticker: str
    side: Literal["buy", "sell"]
    quantity: float  # number of shares (fractional allowed); range checks live in execute_trade

    @field_validator("ticker", mode="before")
    @classmethod
    def _clean_ticker(cls, v: Any) -> Any:
        return v.strip().upper() if isinstance(v, str) else v

    @field_validator("side", mode="before")
    @classmethod
    def _lower_side(cls, v: Any) -> Any:
        return v.strip().lower() if isinstance(v, str) else v


class WatchlistChange(BaseModel):
    ticker: str
    action: Literal["add", "remove"]

    @field_validator("ticker", mode="before")
    @classmethod
    def _clean_ticker(cls, v: Any) -> Any:
        return v.strip().upper() if isinstance(v, str) else v

    @field_validator("action", mode="before")
    @classmethod
    def _lower_action(cls, v: Any) -> Any:
        return v.strip().lower() if isinstance(v, str) else v


class LLMResponse(BaseModel):
    """What the model must return. `trades` / `watchlist_changes` are optional."""

    message: str
    trades: list[TradeInstruction] = Field(default_factory=list)
    watchlist_changes: list[WatchlistChange] = Field(default_factory=list)

    @field_validator("trades", "watchlist_changes", mode="before")
    @classmethod
    def _none_to_empty(cls, v: Any) -> Any:
        return [] if v is None else v


# Strict JSON schema sent as response_format. Hand-written (rather than derived from LLMResponse)
# so every property is `required` with additionalProperties=false, which strict structured-output
# backends require; the model is told to send empty arrays when it has nothing to do.
RESPONSE_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "message": {"type": "string"},
        "trades": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "ticker": {"type": "string"},
                    "side": {"type": "string", "enum": ["buy", "sell"]},
                    "quantity": {"type": "number"},
                },
                "required": ["ticker", "side", "quantity"],
            },
        },
        "watchlist_changes": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "ticker": {"type": "string"},
                    "action": {"type": "string", "enum": ["add", "remove"]},
                },
                "required": ["ticker", "action"],
            },
        },
    },
    "required": ["message", "trades", "watchlist_changes"],
}

RESPONSE_FORMAT: dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {"name": "finally_assistant_response", "strict": True, "schema": RESPONSE_JSON_SCHEMA},
}


def parse_llm_output(raw: str | None) -> LLMResponse:
    """Parse and validate raw model output. Raises ValueError (incl. pydantic errors) if unusable."""
    if raw is None or not raw.strip():
        raise ValueError("empty response")
    text = raw.strip()
    fence = _FENCE_RE.match(text)
    if fence:
        text = fence.group(1)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"response is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("response JSON must be an object")
    # pydantic.ValidationError subclasses ValueError
    return LLMResponse.model_validate(data)


class ChatRequest(BaseModel):
    message: str = Field(max_length=4000)

    @field_validator("message")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("message must not be empty")
        return v
