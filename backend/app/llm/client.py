"""LiteLLM -> OpenRouter -> Cerebras call with schema validation and a single reprompt."""

from __future__ import annotations

import asyncio
import logging

import litellm

from .prompts import build_reprompt
from .schemas import RESPONSE_FORMAT, LLMResponse, parse_llm_output

logger = logging.getLogger(__name__)

MODEL = "openrouter/openai/gpt-oss-120b"
EXTRA_BODY = {"provider": {"order": ["cerebras"]}}
TIMEOUT_SECONDS = 30.0

UNAVAILABLE_MESSAGE = "The assistant is unavailable right now — please try again."
UNREADABLE_MESSAGE = "The assistant returned an unreadable response — please try again."


class LLMUnavailableError(Exception):
    """Timeout, network failure, 5xx, rate limit, auth failure, ... (maps to HTTP 503)."""


class LLMUnreadableError(Exception):
    """Output was malformed / schema-invalid even after one reprompt (maps to HTTP 503)."""


async def _complete(messages: list[dict[str, str]]) -> str | None:
    try:
        response = await asyncio.wait_for(
            litellm.acompletion(
                model=MODEL,
                messages=messages,
                response_format=RESPONSE_FORMAT,
                reasoning_effort="low",
                extra_body=EXTRA_BODY,
                timeout=TIMEOUT_SECONDS,
            ),
            timeout=TIMEOUT_SECONDS,
        )
        return response.choices[0].message.content
    except Exception as exc:  # noqa: BLE001 - every upstream failure is the same 503 to the user
        logger.warning("LLM call failed: %s: %s", type(exc).__name__, exc)
        raise LLMUnavailableError(str(exc)) from exc


async def get_structured_response(messages: list[dict[str, str]]) -> LLMResponse:
    """Call the model; on unparseable output reprompt once, then raise LLMUnreadableError."""
    raw = await _complete(messages)
    try:
        return parse_llm_output(raw)
    except ValueError as first_error:
        logger.warning("LLM output failed validation, reprompting once: %s", first_error)
        retry_raw = await _complete(build_reprompt(messages, raw, str(first_error)))
        try:
            return parse_llm_output(retry_raw)
        except ValueError as second_error:
            logger.warning("LLM retry also failed validation: %s", second_error)
            raise LLMUnreadableError(str(second_error)) from second_error
