"""Watchlist service: persistence plus keeping the market-data source in sync.

Usable without a FastAPI request context (LLM router and tests call it directly).
`add_ticker` / `remove_ticker` are async because the market data source API is async.
"""

from __future__ import annotations

import re

from app import db, state

_TICKER_RE = re.compile(r"^[A-Z]{1,5}$")


class InvalidTicker(ValueError):  # noqa: N818 - name fixed by the team contract
    """Raised when a ticker fails the `^[A-Z]{1,5}$` format check."""


def normalize_ticker(raw: str) -> str:
    """Strip + upper-case a ticker and validate its format."""
    if not isinstance(raw, str):
        raise InvalidTicker("Invalid ticker symbol")
    ticker = raw.strip().upper()
    if not _TICKER_RE.fullmatch(ticker):
        raise InvalidTicker("Invalid ticker symbol")
    return ticker


def list_watchlist() -> list[dict]:
    """Watchlist entries as `{ticker, added_at, price}`; `price` is None until warmed."""
    cache = state.get_cache()
    with db.get_conn() as conn:
        rows = db.list_watchlist(conn)
    return [{**row, "price": cache.get_price(row["ticker"])} for row in rows]


async def add_ticker(raw: str) -> bool:
    """Add a ticker to the watchlist and the price feed. Returns True if newly added."""
    ticker = normalize_ticker(raw)
    with db.get_conn() as conn:
        created = db.add_watchlist(conn, ticker)
    # Idempotent on the source side, so this also repairs a feed that lost the ticker.
    await state.get_source().add_ticker(ticker)
    return created


async def release_feed_if_unused(ticker: str) -> bool:
    """Drop a ticker from the market source and cache unless it is watched or held.

    Returns True if the feed was dropped. The check reads the DB at call time, so a
    ticker that was re-added or re-bought in the meantime is kept.
    """
    with db.get_conn() as conn:
        watched = any(w["ticker"] == ticker for w in db.list_watchlist(conn))
        held = db.get_position(conn, ticker) is not None
    if watched or held:
        return False
    await state.get_source().remove_ticker(ticker)
    return True


async def remove_ticker(raw: str) -> bool:
    """Remove a ticker from the watchlist. Returns True if a row was removed.

    The price feed is kept when a position in the ticker is still held, so it can
    always be valued; otherwise the ticker is dropped from the source and cache.
    (When a held position is later closed, `execute_trade` releases the feed.)
    """
    ticker = normalize_ticker(raw)
    with db.get_conn() as conn:
        removed = db.remove_watchlist(conn, ticker)
    await release_feed_if_unused(ticker)
    return removed
