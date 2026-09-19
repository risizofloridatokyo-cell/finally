"""Data-access primitives. Every function takes an open connection first; business rules live elsewhere."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime, timedelta

from .seed import DEFAULT_USER, seed_defaults
from .timeutil import normalize_iso, utc_now_iso

SNAPSHOT_DOWNSAMPLE_POINTS = 300


def _round_cents(value: float) -> float:
    return round(float(value), 2)


def _rows(cursor: sqlite3.Cursor) -> list[dict]:
    return [dict(r) for r in cursor.fetchall()]


# --- profile ---------------------------------------------------------------------------------


def get_profile(conn: sqlite3.Connection) -> dict:
    row = conn.execute(
        "SELECT cash_balance, realized_pnl, created_at FROM users_profile WHERE id = ?",
        (DEFAULT_USER,),
    ).fetchone()
    if row is None:  # profile row deleted out-of-band; restore the seed rather than crash
        seed_defaults(conn)
        return get_profile(conn)
    return dict(row)


def update_profile(
    conn: sqlite3.Connection,
    *,
    cash_balance: float | None = None,
    realized_pnl: float | None = None,
) -> None:
    if cash_balance is not None:
        conn.execute(
            "UPDATE users_profile SET cash_balance = ? WHERE id = ?",
            (_round_cents(cash_balance), DEFAULT_USER),
        )
    if realized_pnl is not None:
        conn.execute(
            "UPDATE users_profile SET realized_pnl = ? WHERE id = ?",
            (float(realized_pnl), DEFAULT_USER),
        )


# --- watchlist -------------------------------------------------------------------------------


def list_watchlist(conn: sqlite3.Connection) -> list[dict]:
    return _rows(
        conn.execute(
            "SELECT ticker, added_at FROM watchlist WHERE user_id = ? ORDER BY added_at, rowid",
            (DEFAULT_USER,),
        )
    )


def add_watchlist(conn: sqlite3.Connection, ticker: str) -> bool:
    cur = conn.execute(
        "INSERT OR IGNORE INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
        (str(uuid.uuid4()), DEFAULT_USER, ticker, utc_now_iso()),
    )
    return cur.rowcount == 1


def remove_watchlist(conn: sqlite3.Connection, ticker: str) -> bool:
    cur = conn.execute(
        "DELETE FROM watchlist WHERE user_id = ? AND ticker = ?", (DEFAULT_USER, ticker)
    )
    return cur.rowcount > 0


# --- positions -------------------------------------------------------------------------------


def list_positions(conn: sqlite3.Connection) -> list[dict]:
    return _rows(
        conn.execute(
            "SELECT ticker, quantity, avg_cost, updated_at FROM positions "
            "WHERE user_id = ? ORDER BY ticker",
            (DEFAULT_USER,),
        )
    )


def get_position(conn: sqlite3.Connection, ticker: str) -> dict | None:
    row = conn.execute(
        "SELECT ticker, quantity, avg_cost, updated_at FROM positions "
        "WHERE user_id = ? AND ticker = ?",
        (DEFAULT_USER, ticker),
    ).fetchone()
    return dict(row) if row else None


def upsert_position(conn: sqlite3.Connection, ticker: str, quantity: float, avg_cost: float) -> None:
    conn.execute(
        "INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (user_id, ticker) DO UPDATE SET "
        "quantity = excluded.quantity, avg_cost = excluded.avg_cost, "
        "updated_at = excluded.updated_at",
        (str(uuid.uuid4()), DEFAULT_USER, ticker, float(quantity), float(avg_cost), utc_now_iso()),
    )


def delete_position(conn: sqlite3.Connection, ticker: str) -> None:
    conn.execute("DELETE FROM positions WHERE user_id = ? AND ticker = ?", (DEFAULT_USER, ticker))


# --- trades ----------------------------------------------------------------------------------


def insert_trade(
    conn: sqlite3.Connection, ticker: str, side: str, quantity: float, price: float
) -> dict:
    row = {
        "id": str(uuid.uuid4()),
        "user_id": DEFAULT_USER,
        "ticker": ticker,
        "side": side,
        "quantity": float(quantity),
        "price": float(price),
        "executed_at": utc_now_iso(),
    }
    conn.execute(
        "INSERT INTO trades (id, user_id, ticker, side, quantity, price, executed_at) "
        "VALUES (:id, :user_id, :ticker, :side, :quantity, :price, :executed_at)",
        row,
    )
    return row


def list_trades(conn: sqlite3.Connection, limit: int = 100) -> list[dict]:
    return _rows(
        conn.execute(
            "SELECT id, ticker, side, quantity, price, executed_at FROM trades "
            "WHERE user_id = ? ORDER BY executed_at DESC, rowid DESC LIMIT ?",
            (DEFAULT_USER, limit),
        )
    )


# --- portfolio snapshots ---------------------------------------------------------------------


def insert_snapshot(
    conn: sqlite3.Connection, total_value: float, recorded_at: str | None = None
) -> None:
    conn.execute(
        "INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at) "
        "VALUES (?, ?, ?, ?)",
        (
            str(uuid.uuid4()),
            DEFAULT_USER,
            float(total_value),
            normalize_iso(recorded_at) if recorded_at else utc_now_iso(),
        ),
    )


def last_snapshot(conn: sqlite3.Connection) -> dict | None:
    row = conn.execute(
        "SELECT total_value, recorded_at FROM portfolio_snapshots WHERE user_id = ? "
        "ORDER BY recorded_at DESC, rowid DESC LIMIT 1",
        (DEFAULT_USER,),
    ).fetchone()
    return dict(row) if row else None


def _downsample(rows: list[dict], target: int) -> list[dict]:
    """Pick ``target`` evenly-spaced rows, always keeping the first and last."""
    n = len(rows)
    if n <= target:
        return rows
    indices = sorted({round(i * (n - 1) / (target - 1)) for i in range(target)})
    return [rows[i] for i in indices]


def list_snapshots(
    conn: sqlite3.Connection, since: str | None = None, limit: int | None = None
) -> list[dict]:
    """Oldest-first snapshots.

    ``since`` keeps ``recorded_at >= since`` (raises ValueError if unparseable). ``limit`` returns
    the most recent ``limit`` rows. With neither, the full series is downsampled to ~300 points.
    """
    sql = "SELECT total_value, recorded_at FROM portfolio_snapshots WHERE user_id = ?"
    params: list = [DEFAULT_USER]
    if since is not None:
        sql += " AND recorded_at >= ?"
        params.append(normalize_iso(since))
    if limit is not None:
        sql += " ORDER BY recorded_at DESC, rowid DESC LIMIT ?"
        params.append(max(int(limit), 0))
        rows = _rows(conn.execute(sql, params))
        rows.reverse()
        return rows
    sql += " ORDER BY recorded_at, rowid"
    rows = _rows(conn.execute(sql, params))
    if since is None:
        rows = _downsample(rows, SNAPSHOT_DOWNSAMPLE_POINTS)
    return rows


def prune_snapshots(conn: sqlite3.Connection, older_than_days: int = 30) -> int:
    cutoff = (datetime.now(UTC) - timedelta(days=older_than_days)).isoformat(
        timespec="microseconds"
    )
    cur = conn.execute("DELETE FROM portfolio_snapshots WHERE recorded_at < ?", (cutoff,))
    return cur.rowcount


# --- chat ------------------------------------------------------------------------------------


def _chat_row(row: sqlite3.Row | dict) -> dict:
    d = dict(row)
    raw = d.get("actions")
    d["actions"] = json.loads(raw) if raw else None
    return d


def insert_chat_message(
    conn: sqlite3.Connection, role: str, content: str, actions: dict | None = None
) -> dict:
    row = {
        "id": str(uuid.uuid4()),
        "user_id": DEFAULT_USER,
        "role": role,
        "content": content,
        "actions": json.dumps(actions) if actions is not None else None,
        "created_at": utc_now_iso(),
    }
    conn.execute(
        "INSERT INTO chat_messages (id, user_id, role, content, actions, created_at) "
        "VALUES (:id, :user_id, :role, :content, :actions, :created_at)",
        row,
    )
    return _chat_row(row)


def recent_chat_messages(conn: sqlite3.Connection, limit: int = 20) -> list[dict]:
    rows = conn.execute(
        "SELECT role, content, actions, created_at FROM chat_messages WHERE user_id = ? "
        "ORDER BY created_at DESC, rowid DESC LIMIT ?",
        (DEFAULT_USER, limit),
    ).fetchall()
    return [_chat_row(r) for r in reversed(rows)]
