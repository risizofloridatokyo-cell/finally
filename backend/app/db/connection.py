"""SQLite connection management and lazy initialisation."""

from __future__ import annotations

import os
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .schema import SCHEMA_SQL
from .seed import seed_defaults

# app/db/connection.py -> parents[3] is the repo root.
_REPO_ROOT = Path(__file__).resolve().parents[3]
BUSY_TIMEOUT_MS = 5000

_init_lock = threading.Lock()
_initialized: set[str] = set()


def get_db_path() -> Path:
    """Resolve the SQLite path: ``DB_PATH`` env, else ``<repo>/db/finally.db``."""
    raw = os.environ.get("DB_PATH")
    return Path(raw) if raw else _REPO_ROOT / "db" / "finally.db"


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=BUSY_TIMEOUT_MS / 1000, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def init_db(path: str | Path | None = None) -> None:
    """Create tables and seed defaults if missing. Idempotent; never clobbers existing data."""
    db_path = Path(path) if path is not None else get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = _connect(db_path)
    try:
        conn.executescript(SCHEMA_SQL)
        seed_defaults(conn)
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()
    with _init_lock:
        _initialized.add(str(db_path.resolve()))


def _ensure_init(db_path: Path) -> None:
    key = str(db_path.resolve())
    with _init_lock:
        if key in _initialized and db_path.exists():
            return
    init_db(db_path)


@contextmanager
def get_conn(*, immediate: bool = False) -> Iterator[sqlite3.Connection]:
    """Open a connection to ``DB_PATH`` (lazily initialising the DB).

    Commits on clean exit, rolls back on exception, always closes. Use one connection per
    unit of work. ``immediate=True`` takes the write lock up front (``BEGIN IMMEDIATE``) so a
    read-then-write sequence such as a trade cannot be interleaved by another writer.
    """
    db_path = get_db_path()
    _ensure_init(db_path)
    conn = _connect(db_path)
    try:
        if immediate:
            conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def check_db() -> bool:
    """True if the database is reachable (for /api/health)."""
    try:
        with get_conn() as conn:
            conn.execute("SELECT 1").fetchone()
        return True
    except Exception:
        return False
