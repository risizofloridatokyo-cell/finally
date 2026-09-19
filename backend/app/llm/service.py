"""Chat orchestration: context -> LLM -> auto-execute -> persist (PLAN §9)."""

from __future__ import annotations

import asyncio
import importlib
import inspect
import logging
from types import ModuleType
from typing import Any

from fastapi import HTTPException

from .client import (
    UNAVAILABLE_MESSAGE,
    UNREADABLE_MESSAGE,
    LLMUnavailableError,
    LLMUnreadableError,
    get_structured_response,
)
from .mock import is_mock_enabled, mock_response
from .prompts import build_messages
from .schemas import LLMResponse

logger = logging.getLogger(__name__)

HISTORY_LIMIT = 20


# Sibling modules are resolved at call time (not import time) so they can be built and patched
# independently; tests monkeypatch these accessors.
def _db() -> ModuleType:
    return importlib.import_module("app.db")


def _portfolio() -> ModuleType:
    return importlib.import_module("app.portfolio.service")


def _watchlist() -> ModuleType:
    return importlib.import_module("app.watchlist.service")


async def _execute_actions(parsed: LLMResponse) -> dict[str, Any] | None:
    """Run the LLM's trades and watchlist changes. Failures become rejected entries, not errors."""
    portfolio, watchlist = _portfolio(), _watchlist()
    trades: list[dict[str, Any]] = []
    changes: list[dict[str, Any]] = []
    errors: list[str] = []

    for t in parsed.trades:
        try:
            # blocking sqlite + process-level lock: keep it off the event loop
            result = await asyncio.to_thread(portfolio.execute_trade, t.ticker, t.side, t.quantity)
            trades.append(
                {
                    "ticker": result.get("ticker", t.ticker),
                    "side": result.get("side", t.side),
                    "quantity": result.get("quantity", t.quantity),
                    "price": result.get("price"),
                    "status": "executed",
                }
            )
        except portfolio.TradeError as exc:
            trades.append(
                {
                    "ticker": t.ticker,
                    "side": t.side,
                    "quantity": t.quantity,
                    "price": None,
                    "status": "rejected",
                }
            )
            errors.append(f"{t.ticker} {t.side} rejected: {exc.message}")

    for w in parsed.watchlist_changes:
        try:
            call = watchlist.add_ticker if w.action == "add" else watchlist.remove_ticker
            result = call(w.ticker)
            if inspect.isawaitable(result):  # the real service is async; tolerate a sync one
                await result
            changes.append({"ticker": w.ticker, "action": w.action, "status": "executed"})
        except watchlist.InvalidTicker:
            changes.append({"ticker": w.ticker, "action": w.action, "status": "rejected"})
            errors.append(f"Invalid ticker symbol: {w.ticker}")

    if not (trades or changes or errors):
        return None
    return {"trades": trades, "watchlist_changes": changes, "errors": errors}


async def handle_chat(message: str) -> dict[str, Any]:
    """Process one chat turn. Returns {"message", "actions"}; raises HTTPException(503) on failure.

    Nothing is executed or persisted unless the LLM produced a usable response.
    """
    db = _db()

    if is_mock_enabled():
        parsed = mock_response(message)
    else:
        ctx = await asyncio.to_thread(_portfolio().get_portfolio_context)
        with db.get_conn() as conn:
            history = db.recent_chat_messages(conn, HISTORY_LIMIT)
        messages = build_messages(ctx, history, message)
        try:
            parsed = await get_structured_response(messages)
        except LLMUnavailableError:
            raise HTTPException(status_code=503, detail=UNAVAILABLE_MESSAGE) from None
        except LLMUnreadableError:
            raise HTTPException(status_code=503, detail=UNREADABLE_MESSAGE) from None

    actions = await _execute_actions(parsed)

    with db.get_conn() as conn:  # one transaction: both rows or neither
        db.insert_chat_message(conn, "user", message, None)
        db.insert_chat_message(conn, "assistant", parsed.message, actions)

    return {"message": parsed.message, "actions": actions}
