"""Chat flow against the REAL portfolio/watchlist services and a real temp SQLite DB."""

from __future__ import annotations

import json

import pytest

from app import db, state
from app.market import PriceCache


class FakeSource:
    def __init__(self) -> None:
        self.added: list[str] = []
        self.removed: list[str] = []
        self.tracked = ["AAPL", "NFLX"]

    def get_tickers(self) -> list[str]:
        return list(self.tracked)

    async def add_ticker(self, ticker: str) -> None:
        self.added.append(ticker)

    async def remove_ticker(self, ticker: str) -> None:
        self.removed.append(ticker)


@pytest.fixture
def runtime(temp_db):
    cache = PriceCache()
    cache.update("AAPL", 100.0)
    source = FakeSource()
    state.set_runtime(cache, source)
    yield source
    state.set_runtime(None, None)


def _llm_reply(message, trades=(), changes=()):
    return json.dumps(
        {"message": message, "trades": list(trades), "watchlist_changes": list(changes)}
    )


def test_llm_trade_and_watchlist_hit_real_services(client, runtime, fake_llm):
    llm = fake_llm(
        _llm_reply(
            "Buying 5 AAPL and watching PYPL.",
            trades=[{"ticker": "AAPL", "side": "buy", "quantity": 5}],
            changes=[{"ticker": "PYPL", "action": "add"}],
        )
    )
    r = client.post("/api/chat", json={"message": "buy 5 AAPL and watch PYPL"})
    assert r.status_code == 200
    actions = r.json()["actions"]
    assert actions["trades"] == [
        {"ticker": "AAPL", "side": "buy", "quantity": 5, "price": 100.0, "status": "executed"}
    ]
    assert actions["watchlist_changes"] == [{"ticker": "PYPL", "action": "add", "status": "executed"}]
    assert actions["errors"] == []

    with db.get_conn() as conn:
        assert db.get_profile(conn)["cash_balance"] == 9500.0
        assert db.get_position(conn, "AAPL")["quantity"] == 5
        assert "PYPL" in [w["ticker"] for w in db.list_watchlist(conn)]
        assert len(db.recent_chat_messages(conn)) == 2
    assert runtime.added == ["PYPL"]

    # The prompt was built from the real portfolio context.
    system = llm.calls[0]["messages"][0]["content"]
    assert "Cash balance: $10,000.00" in system
    assert "AAPL: price $100.00" not in system  # sanity: formatter uses its own wording
    assert "AAPL: $100.00" in system  # watchlist line with live price
    assert "NFLX: price unavailable" in system  # unwarmed watchlist ticker


def test_oversized_mock_buy_rejected_by_real_validation(client, runtime, monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "true")
    r = client.post("/api/chat", json={"message": "please make an oversized buy"})
    assert r.status_code == 200
    body = r.json()
    assert body["actions"]["trades"][0]["status"] == "rejected"
    assert body["actions"]["errors"] and "AAPL" in body["actions"]["errors"][0]
    with db.get_conn() as conn:
        assert db.get_profile(conn)["cash_balance"] == 10000.0
        assert db.get_position(conn, "AAPL") is None
        assert db.recent_chat_messages(conn)[1]["actions"] == body["actions"]


def test_mock_invalid_watchlist_and_untracked_trade_rejections(client, runtime, fake_llm):
    fake_llm(
        _llm_reply(
            "Trying two bad things.",
            trades=[{"ticker": "NOPE", "side": "buy", "quantity": 1}],
            changes=[{"ticker": "TOOLONGX", "action": "add"}],
        )
    )
    r = client.post("/api/chat", json={"message": "do it"})
    assert r.status_code == 200
    actions = r.json()["actions"]
    assert actions["trades"][0]["status"] == "rejected"
    assert actions["watchlist_changes"][0]["status"] == "rejected"
    assert len(actions["errors"]) == 2
