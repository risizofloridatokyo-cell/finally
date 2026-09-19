"""Prompt construction: system prompt, portfolio-context formatting, history, reprompt."""

from __future__ import annotations

import json
from typing import Any

from .schemas import RESPONSE_JSON_SCHEMA

MAX_RAW_ECHO = 4000  # cap on the malformed output echoed back in the reprompt

SYSTEM_PROMPT = """\
You are FinAlly, an AI trading assistant inside a simulated trading workstation. The user trades \
a virtual portfolio with fake money; all orders are market orders that fill instantly at the \
current price with no fees.

Your job:
- Analyze portfolio composition, risk concentration, and P&L.
- Suggest trades with brief reasoning.
- Execute trades when the user asks for them or agrees to your suggestion. Trades you return are \
executed automatically, without a confirmation dialog.
- Manage the watchlist proactively (add tickers the user is interested in, remove ones they no \
longer want).
- Be concise and data-driven.

Rules:
- `trades[].quantity` is ALWAYS a number of shares (fractional shares are allowed), never dollars. \
Convert dollar amounts ("put $2,000 into NVDA") into shares using the live price in the portfolio \
context (dollars / price). Convert relative sizes ("sell half my Tesla", "sell everything") into \
shares using the position quantity in the portfolio context.
- Never invent tickers or prices that are not in the portfolio context. If a ticker has no live \
price ("price unavailable"), do not trade it; tell the user instead.
- Only include a trade when the user asked for it or agreed to it. For pure analysis or questions, \
return empty `trades` and `watchlist_changes`.
- Check affordability before buying (cash balance) and holdings before selling; if a request cannot \
be satisfied, say so in `message` rather than returning an impossible trade. A trade the system \
rejects will be reported to the user as an error.
- Ticker symbols are 1-5 uppercase letters.
- Always respond with valid JSON matching the schema below, and nothing else: no prose outside the \
JSON and no markdown code fences. Use empty arrays when there are no trades or watchlist changes.

JSON schema:
"""


def _money(value: Any) -> str:
    return f"${value:,.2f}" if isinstance(value, (int, float)) else "unavailable"


def _qty(value: Any) -> str:
    if not isinstance(value, (int, float)):
        return "?"
    return f"{value:.6f}".rstrip("0").rstrip(".") or "0"


def _pct(value: Any) -> str:
    return f"{value:+.2f}%" if isinstance(value, (int, float)) else "n/a"


def _signed_money(value: Any) -> str:
    if not isinstance(value, (int, float)):
        return "n/a"
    sign = "-" if value < 0 else "+"
    return f"{sign}${abs(value):,.2f}"


def format_portfolio_context(ctx: dict[str, Any]) -> str:
    """Render `get_portfolio_context()` as text. Unwarmed (null) prices become 'price unavailable'."""
    lines = [
        f"Cash balance: {_money(ctx.get('cash_balance'))}",
        f"Total portfolio value (positions with live prices + cash): {_money(ctx.get('total_value'))}",
        f"Realized P&L (cumulative): {_signed_money(ctx.get('realized_pnl'))}",
        f"Total unrealized P&L: {_signed_money(ctx.get('total_unrealized_pnl'))}",
        "",
        "Positions:",
    ]
    positions = ctx.get("positions") or []
    if not positions:
        lines.append("  (none)")
    for p in positions:
        price = p.get("current_price")
        if price is None:
            lines.append(
                f"  {p.get('ticker')}: {_qty(p.get('quantity'))} shares, avg cost "
                f"{_money(p.get('avg_cost'))}, price unavailable"
            )
            continue
        pct = p.get("unrealized_pnl_percent", p.get("unrealized_pnl_pct"))
        lines.append(
            f"  {p.get('ticker')}: {_qty(p.get('quantity'))} shares, avg cost "
            f"{_money(p.get('avg_cost'))}, current price {_money(price)}, unrealized P&L "
            f"{_signed_money(p.get('unrealized_pnl'))} ({_pct(pct)})"
        )
    lines += ["", "Watchlist (live prices):"]
    watchlist = ctx.get("watchlist") or []
    if not watchlist:
        lines.append("  (empty)")
    for w in watchlist:
        price = w.get("price")
        shown = _money(price) if price is not None else "price unavailable"
        lines.append(f"  {w.get('ticker')}: {shown}")
    return "\n".join(lines)


def build_system_prompt(ctx: dict[str, Any]) -> str:
    schema = json.dumps(RESPONSE_JSON_SCHEMA, indent=2)
    return (
        f"{SYSTEM_PROMPT}{schema}\n\n"
        f"## Current portfolio context (live)\n{format_portfolio_context(ctx)}"
    )


def summarize_actions(actions: dict[str, Any] | None) -> str:
    """One-line record of what an assistant turn executed, so later turns can see it."""
    if not actions:
        return ""
    parts: list[str] = []
    for t in actions.get("trades") or []:
        if t.get("status") == "executed":
            parts.append(
                f"executed {t['side']} {_qty(t['quantity'])} {t['ticker']} @ {_money(t.get('price'))}"
            )
        else:
            parts.append(f"REJECTED {t['side']} {_qty(t['quantity'])} {t['ticker']}")
    for w in actions.get("watchlist_changes") or []:
        parts.append(f"{w['status']} watchlist {w['action']} {w['ticker']}")
    for e in actions.get("errors") or []:
        parts.append(f"error: {e}")
    return f"[System note: {'; '.join(parts)}]" if parts else ""


def build_messages(
    ctx: dict[str, Any], history: list[dict[str, Any]], user_message: str
) -> list[dict[str, str]]:
    """system (instructions + portfolio context), prior turns oldest-first, then the new message."""
    messages: list[dict[str, str]] = [{"role": "system", "content": build_system_prompt(ctx)}]
    for m in history:
        content = m["content"]
        note = summarize_actions(m.get("actions")) if m["role"] == "assistant" else ""
        if note:
            content = f"{content}\n{note}"
        messages.append({"role": m["role"], "content": content})
    messages.append({"role": "user", "content": user_message})
    return messages


def build_reprompt(messages: list[dict[str, str]], raw: str | None, error: str) -> list[dict[str, str]]:
    """Retry conversation: original messages plus a corrective turn carrying the raw bad output."""
    echoed = (raw or "")[:MAX_RAW_ECHO]
    schema = json.dumps(RESPONSE_JSON_SCHEMA)
    correction = (
        "Your previous response could not be parsed. Return valid JSON matching this schema, and "
        f"nothing else.\nSchema: {schema}\nProblem: {error}\nYour raw output was:\n{echoed}"
    )
    return [*messages, {"role": "user", "content": correction}]
