"""Fixtures: temp SQLite DB + stub market source wired into `app.state`."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app import db, state
from app.market import PriceCache
from tests.portfolio.stubs import StubSource


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Initialised temp DB, a primed stub source (default 10 tickers) and price cache."""
    monkeypatch.setenv("DB_PATH", str(tmp_path / "finally.db"))
    monkeypatch.setenv("STATIC_DIR", str(tmp_path / "no-static"))
    db.init_db()
    cache = PriceCache()
    source = StubSource(cache)
    with db.get_conn() as conn:
        source.prime([w["ticker"] for w in db.list_watchlist(conn)])
    state.set_runtime(cache, source)
    yield SimpleNamespace(cache=cache, source=source)
    state.set_runtime(None, None)


def read_state() -> dict:
    """Profile + positions + trades straight from the DB."""
    with db.get_conn() as conn:
        return {
            "profile": db.get_profile(conn),
            "positions": {p["ticker"]: p for p in db.list_positions(conn)},
            "trades": db.list_trades(conn),
            "snapshots": db.list_snapshots(conn, limit=1000),
        }
