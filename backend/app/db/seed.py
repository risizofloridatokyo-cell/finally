"""Default seed data (PLAN §7): one user profile and the 10 default watchlist tickers."""

from __future__ import annotations

import sqlite3
import uuid

from .timeutil import utc_now_iso

DEFAULT_USER = "default"
DEFAULT_CASH = 10000.0
DEFAULT_TICKERS = ("AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "NFLX")


def seed_defaults(conn: sqlite3.Connection) -> None:
    """Insert the default profile and watchlist if they are missing (never overwrites)."""
    now = utc_now_iso()
    cur = conn.execute(
        "INSERT OR IGNORE INTO users_profile (id, cash_balance, realized_pnl, created_at) "
        "VALUES (?, ?, 0.0, ?)",
        (DEFAULT_USER, DEFAULT_CASH, now),
    )
    # Only seed the watchlist on a truly fresh database, so a user who deliberately
    # emptied or edited their watchlist does not get the defaults back on restart.
    if cur.rowcount == 1:
        for ticker in DEFAULT_TICKERS:
            conn.execute(
                "INSERT OR IGNORE INTO watchlist (id, user_id, ticker, added_at) "
                "VALUES (?, ?, ?, ?)",
                (str(uuid.uuid4()), DEFAULT_USER, ticker, now),
            )
