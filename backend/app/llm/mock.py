"""Deterministic LLM stand-in for LLM_MOCK=true (TEAM_CONTRACTS.md trigger table)."""

from __future__ import annotations

import os

from .schemas import LLMResponse, TradeInstruction, WatchlistChange


def is_mock_enabled() -> bool:
    return os.environ.get("LLM_MOCK", "").strip().lower() == "true"


def mock_response(user_message: str) -> LLMResponse:
    """First matching trigger (case-insensitive substring) wins."""
    text = user_message.lower()
    if "oversized" in text:
        return LLMResponse(
            message="Mock: attempting an oversized buy of 1000000 AAPL.",
            trades=[TradeInstruction(ticker="AAPL", side="buy", quantity=1_000_000)],
        )
    if "buy" in text:
        return LLMResponse(
            message="Mock: buying 5 shares of AAPL.",
            trades=[TradeInstruction(ticker="AAPL", side="buy", quantity=5)],
        )
    if "sell" in text:
        return LLMResponse(
            message="Mock: selling 1 share of AAPL.",
            trades=[TradeInstruction(ticker="AAPL", side="sell", quantity=1)],
        )
    if "add" in text:
        return LLMResponse(
            message="Mock: adding PYPL to your watchlist.",
            watchlist_changes=[WatchlistChange(ticker="PYPL", action="add")],
        )
    if "remove" in text:
        return LLMResponse(
            message="Mock: removing PYPL from your watchlist.",
            watchlist_changes=[WatchlistChange(ticker="PYPL", action="remove")],
        )
    return LLMResponse(message="Mock: I'm FinAlly, your AI trading assistant. No action taken.")
