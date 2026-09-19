import sqlite3
import threading

import pytest

from app.db import (
    DEFAULT_TICKERS,
    add_watchlist,
    check_db,
    get_conn,
    get_db_path,
    get_profile,
    init_db,
    list_watchlist,
    remove_watchlist,
    update_profile,
)

TABLES = {
    "users_profile",
    "watchlist",
    "positions",
    "trades",
    "portfolio_snapshots",
    "chat_messages",
}


def _tables(path):
    conn = sqlite3.connect(path)
    try:
        return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()


def test_db_path_uses_env(db_path):
    assert get_db_path() == db_path


def test_db_path_default_is_repo_db(monkeypatch):
    monkeypatch.delenv("DB_PATH", raising=False)
    path = get_db_path()
    assert path.name == "finally.db"
    assert path.parent.name == "db"


def test_init_creates_parent_dir_tables_and_seed(db_path):
    assert not db_path.parent.exists()
    init_db()
    assert TABLES <= _tables(db_path)
    with get_conn() as conn:
        profile = get_profile(conn)
        assert profile["cash_balance"] == 10000.0
        assert profile["realized_pnl"] == 0.0
        assert profile["created_at"].endswith("+00:00")
        assert [w["ticker"] for w in list_watchlist(conn)] == list(DEFAULT_TICKERS)


def test_init_accepts_explicit_path(tmp_path):
    target = tmp_path / "explicit.db"
    init_db(target)
    assert TABLES <= _tables(target)


def test_lazy_init_on_first_get_conn(db_path):
    assert not db_path.exists()
    with get_conn() as conn:
        assert len(list_watchlist(conn)) == 10
    assert db_path.exists()


def test_lazy_init_recovers_if_file_deleted(db_path):
    with get_conn() as conn:
        update_profile(conn, cash_balance=5.0)
    for suffix in ("", "-wal", "-shm"):
        p = db_path.with_name(db_path.name + suffix)
        if p.exists():
            p.unlink()
    with get_conn() as conn:
        assert get_profile(conn)["cash_balance"] == 10000.0


def test_init_is_idempotent_and_keeps_data(db_path):
    init_db()
    with get_conn() as conn:
        update_profile(conn, cash_balance=1234.56, realized_pnl=7.5)
        remove_watchlist(conn, "AAPL")
        add_watchlist(conn, "PYPL")
    init_db()
    init_db()
    with get_conn() as conn:
        profile = get_profile(conn)
        assert profile["cash_balance"] == 1234.56
        assert profile["realized_pnl"] == 7.5
        tickers = [w["ticker"] for w in list_watchlist(conn)]
        assert "AAPL" not in tickers  # user's deletion is not undone by restart
        assert "PYPL" in tickers
        assert len(tickers) == 10


def test_pragmas(db_path):
    with get_conn() as conn:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] >= 1000
        assert conn.row_factory is sqlite3.Row


def test_commit_on_clean_exit(db_path):
    with get_conn() as conn:
        update_profile(conn, cash_balance=42.0)
    with get_conn() as conn:
        assert get_profile(conn)["cash_balance"] == 42.0


def test_rollback_on_exception(db_path):
    with pytest.raises(RuntimeError):
        with get_conn() as conn:
            update_profile(conn, cash_balance=1.0)
            add_watchlist(conn, "ZZZ")
            raise RuntimeError("boom")
    with get_conn() as conn:
        assert get_profile(conn)["cash_balance"] == 10000.0
        assert "ZZZ" not in [w["ticker"] for w in list_watchlist(conn)]


def test_immediate_rolls_back_too(db_path):
    with pytest.raises(RuntimeError):
        with get_conn(immediate=True) as conn:
            update_profile(conn, cash_balance=1.0)
            raise RuntimeError("boom")
    with get_conn() as conn:
        assert get_profile(conn)["cash_balance"] == 10000.0


def test_immediate_serialises_concurrent_writers(db_path):
    init_db()
    n_threads, n_incr = 4, 10

    def worker():
        for _ in range(n_incr):
            with get_conn(immediate=True) as conn:
                cash = get_profile(conn)["cash_balance"]
                update_profile(conn, cash_balance=cash + 1)

    threads = [threading.Thread(target=worker) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    with get_conn() as conn:
        assert get_profile(conn)["cash_balance"] == 10000.0 + n_threads * n_incr


def test_check_db(db_path):
    assert check_db() is True


def test_check_db_false_when_unreachable(tmp_path, monkeypatch):
    # A directory path cannot be opened as a database file.
    monkeypatch.setenv("DB_PATH", str(tmp_path))
    assert check_db() is False
