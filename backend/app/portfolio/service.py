"""Portfolio service: the single trade path, valuation and snapshots.

Both `POST /api/portfolio/trade` and LLM-issued trades go through `execute_trade`.
Everything here is synchronous and usable without a FastAPI request context.
"""

from __future__ import annotations

import asyncio
import logging
import math
import sqlite3
import threading
from collections.abc import Coroutine

from app import db, state
from app.config import SNAPSHOT_MIN_CHANGE
from app.market import PriceCache
from app.watchlist.service import InvalidTicker, normalize_ticker, release_feed_if_unused

logger = logging.getLogger(__name__)

FEED_RELEASE_TIMEOUT = 5.0
_pending_tasks: set[asyncio.Task] = set()  # keeps fire-and-forget tasks alive

QTY_EPSILON = 1e-6  # quantities within this of zero count as zero
MAX_QUANTITY = 1e9

# One process-level lock serialises every trade so a trade-bar submit and an LLM
# trade can never interleave and double-spend cash.
_trade_lock = threading.Lock()


class TradeError(Exception):
    """A trade rejected by validation.

    `status_code`: 400 invalid input, 404 untracked ticker, 409 business-rule conflict
    (price not warmed, insufficient cash / shares).
    """

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


# --- valuation -------------------------------------------------------------------------------


def _value_positions(positions: list[dict], cache: PriceCache) -> tuple[list[dict], float, float]:
    """Attach live valuation to raw position rows.

    Returns (rows, market_value_total, unrealized_total). A position whose price is not
    warmed reports null price / P&L and is excluded from both totals.
    """
    rows: list[dict] = []
    market_total = 0.0
    unrealized_total = 0.0
    for pos in positions:
        qty, avg_cost = pos["quantity"], pos["avg_cost"]
        price = cache.get_price(pos["ticker"])
        row = {
            "ticker": pos["ticker"],
            "quantity": qty,
            "avg_cost": avg_cost,
            "current_price": price,
            "market_value": None,
            "unrealized_pnl": None,
            "unrealized_pnl_pct": None,
        }
        if price is not None:
            market_value = qty * price
            cost_basis = qty * avg_cost
            pnl = market_value - cost_basis
            market_total += market_value
            unrealized_total += pnl
            row["market_value"] = round(market_value, 2)
            row["unrealized_pnl"] = round(pnl, 2)
            row["unrealized_pnl_pct"] = round(pnl / cost_basis * 100, 2) if cost_basis else 0.0
        rows.append(row)
    return rows, market_total, unrealized_total


def _total_value(conn: sqlite3.Connection, cache: PriceCache) -> float:
    cash = db.get_profile(conn)["cash_balance"]
    _, market_total, _ = _value_positions(db.list_positions(conn), cache)
    return round(cash + market_total, 2)


def get_portfolio() -> dict:
    """Body of `GET /api/portfolio`."""
    cache = state.get_cache()
    with db.get_conn() as conn:
        profile = db.get_profile(conn)
        positions = db.list_positions(conn)
    rows, market_total, unrealized_total = _value_positions(positions, cache)
    return {
        "cash_balance": profile["cash_balance"],
        "realized_pnl": profile["realized_pnl"],
        "positions": rows,
        "total_value": round(profile["cash_balance"] + market_total, 2),
        "total_unrealized_pnl": round(unrealized_total, 2),
    }


def get_portfolio_context() -> dict:
    """Portfolio plus watchlist with live prices, for the LLM prompt.

    Same shape as `get_portfolio()` with an extra `watchlist: [{ticker, price|None}]`.
    """
    cache = state.get_cache()
    context = get_portfolio()
    with db.get_conn() as conn:
        watchlist = db.list_watchlist(conn)
    context["watchlist"] = [
        {"ticker": w["ticker"], "price": cache.get_price(w["ticker"])} for w in watchlist
    ]
    return context


# --- snapshots -------------------------------------------------------------------------------


def snapshot_portfolio(*, force: bool = False) -> bool:
    """Record a `portfolio_snapshots` row. Returns True if one was written.

    Unless `force`, skips when total value moved less than SNAPSHOT_MIN_CHANGE (0.1%)
    since the last snapshot.
    """
    cache = state.get_cache()
    with db.get_conn() as conn:
        total = _total_value(conn, cache)
        if not force:
            last = db.last_snapshot(conn)
            if last is not None and last["total_value"]:
                change = abs(total - last["total_value"]) / abs(last["total_value"])
                if change < SNAPSHOT_MIN_CHANGE:
                    return False
        db.insert_snapshot(conn, total)
    return True


# --- trade execution -------------------------------------------------------------------------


def _validate_side_quantity(side: str, quantity: float) -> tuple[str, float]:
    """Steps 2 and 3 of the PLAN §8 validation; returns the normalised (side, quantity)."""
    if not isinstance(side, str) or side.strip().lower() not in ("buy", "sell"):
        raise TradeError("Side must be 'buy' or 'sell'", 400)
    side = side.strip().lower()

    try:
        qty = float(quantity)
    except (TypeError, ValueError):
        raise TradeError("Quantity must be a number", 400) from None
    if not math.isfinite(qty):
        raise TradeError("Quantity must be a finite number", 400)
    if qty <= 0:
        raise TradeError("Quantity must be greater than zero", 400)
    if qty > MAX_QUANTITY:
        raise TradeError("Quantity is too large", 400)
    return side, qty


def _run_source_coroutine(coro: Coroutine) -> None:
    """Run a market-source coroutine from synchronous code, wherever it is called from.

    - On the event-loop thread itself we cannot block, so schedule it fire-and-forget.
    - From a worker thread (route handler, `asyncio.to_thread`) run it on the app loop and wait.
    - With no loop at all (plain sync callers / tests) just run it to completion.
    """
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None
    if running is not None:
        task = running.create_task(coro)
        _pending_tasks.add(task)
        task.add_done_callback(_pending_tasks.discard)
        return
    loop = state.get_loop()
    if loop is not None and loop.is_running():
        asyncio.run_coroutine_threadsafe(coro, loop).result(timeout=FEED_RELEASE_TIMEOUT)
    else:
        asyncio.run(coro)


def _release_feed(ticker: str) -> None:
    """After a position closes, stop pricing the ticker unless it is still on the watchlist."""
    try:
        _run_source_coroutine(release_feed_if_unused(ticker))
    except Exception:  # the trade is already committed; never fail it over feed cleanup
        logger.exception("Could not release price feed for %s", ticker)


def execute_trade(ticker: str, side: str, quantity: float) -> dict:
    """Execute a market order at the current cached price. THE single trade path.

    Validation order (first failure wins): ticker tracked with a warmed price, side,
    quantity, then cash (buy) / shares (sell). Raises `TradeError`; on success returns
    `{"ticker","side","quantity","price","status":"executed"}`.
    """
    cache = state.get_cache()
    source = state.get_source()
    closed = False

    with _trade_lock:
        # 1. ticker is tracked and has a warmed price (normalised first to look it up)
        try:
            symbol = normalize_ticker(ticker)
        except InvalidTicker:
            raise TradeError("Invalid ticker symbol", 400) from None
        if symbol not in source.get_tickers():
            raise TradeError(f"Unknown ticker: {symbol}", 404)
        price = cache.get_price(symbol)
        if price is None:
            raise TradeError(f"Price not available yet for {symbol}", 409)

        # 2-3. side and quantity
        side, qty = _validate_side_quantity(side, quantity)

        with db.get_conn(immediate=True) as conn:
            profile = db.get_profile(conn)
            cash = round(profile["cash_balance"], 2)
            position = db.get_position(conn, symbol)

            if side == "buy":
                cost = round(qty * price, 2)
                # 4. buy: cost must fit in cash (both in cents)
                if cost > cash:
                    raise TradeError(
                        f"Insufficient cash for {symbol} buy: need ${cost:,.2f}, "
                        f"have ${cash:,.2f}",
                        409,
                    )
                old_qty = position["quantity"] if position else 0.0
                old_cost = position["avg_cost"] if position else 0.0
                new_qty = old_qty + qty
                new_avg = (old_qty * old_cost + qty * price) / new_qty
                db.upsert_position(conn, symbol, new_qty, new_avg)
                db.update_profile(conn, cash_balance=cash - cost)
            else:
                held = position["quantity"] if position else 0.0
                # 5. sell: cannot sell more than held (within epsilon)
                if qty > held + QTY_EPSILON:
                    raise TradeError(
                        f"Insufficient shares of {symbol}: trying to sell {qty:g}, "
                        f"holding {held:g}",
                        409,
                    )
                qty = min(qty, held)  # absorb epsilon overshoot so we never go negative
                proceeds = round(qty * price, 2)
                remaining = held - qty
                if remaining <= QTY_EPSILON:
                    db.delete_position(conn, symbol)
                    closed = True
                else:
                    db.upsert_position(conn, symbol, remaining, position["avg_cost"])
                realized = profile["realized_pnl"] + (price - position["avg_cost"]) * qty
                db.update_profile(
                    conn, cash_balance=cash + proceeds, realized_pnl=round(realized, 6)
                )

            db.insert_trade(conn, symbol, side, qty, price)
            db.insert_snapshot(conn, _total_value(conn, cache))

    if closed:
        # Outside the trade lock: a worker thread waits on the event loop here, and the
        # loop thread may itself be blocked acquiring the lock.
        _release_feed(symbol)

    logger.info("Trade executed: %s %s x%s @ %s", side, symbol, qty, price)
    return {
        "ticker": symbol,
        "side": side,
        "quantity": qty,
        "price": price,
        "status": "executed",
    }
