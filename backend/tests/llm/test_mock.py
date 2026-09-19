"""LLM_MOCK=true: deterministic table from planning/TEAM_CONTRACTS.md, zero network."""

from __future__ import annotations

import pytest

from app.llm.mock import is_mock_enabled, mock_response


@pytest.fixture
def mock_on(monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "true")


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    async def boom(**_kwargs):
        raise AssertionError("litellm must not be called in mock mode")

    monkeypatch.setattr("app.llm.client.litellm.acompletion", boom)


def test_flag_parsing(monkeypatch):
    monkeypatch.delenv("LLM_MOCK", raising=False)
    assert not is_mock_enabled()
    for value, expected in [("true", True), ("TRUE", True), ("false", False), ("", False)]:
        monkeypatch.setenv("LLM_MOCK", value)
        assert is_mock_enabled() is expected


@pytest.mark.parametrize(
    "text,trade,change",
    [
        ("Please BUY something", ("AAPL", "buy", 5), None),
        ("sell some", ("AAPL", "sell", 1), None),
        ("add a ticker", None, ("PYPL", "add")),
        ("remove it", None, ("PYPL", "remove")),
        ("oversized order", ("AAPL", "buy", 1_000_000), None),
        ("buy an oversized position", ("AAPL", "buy", 1_000_000), None),  # oversized wins over buy
        ("buy and sell", ("AAPL", "buy", 5), None),  # first match wins
        ("hello there", None, None),
    ],
)
def test_trigger_table(text, trade, change):
    r = mock_response(text)
    assert "Mock:" in r.message
    got_trade = (r.trades[0].ticker, r.trades[0].side, r.trades[0].quantity) if r.trades else None
    got_change = (
        (r.watchlist_changes[0].ticker, r.watchlist_changes[0].action)
        if r.watchlist_changes
        else None
    )
    assert (got_trade, got_change) == (trade, change)


def test_mock_buy_via_endpoint_needs_no_context_or_network(client, fakes, temp_db, mock_on):
    r = client.post("/api/chat", json={"message": "buy some apple"})
    assert r.status_code == 200
    body = r.json()
    assert "Mock:" in body["message"] and "AAPL" in body["message"]
    assert body["actions"]["trades"][0]["status"] == "executed"
    assert fakes.trades == [("AAPL", "buy", 5)]
    with temp_db.get_conn() as conn:
        assert len(temp_db.recent_chat_messages(conn)) == 2


def test_mock_oversized_buy_is_rejected_inline(client, fakes, mock_on):
    r = client.post("/api/chat", json={"message": "try an oversized buy"})
    assert r.status_code == 200
    actions = r.json()["actions"]
    assert actions["trades"][0]["status"] == "rejected"
    assert actions["trades"][0]["quantity"] == 1_000_000
    assert len(actions["errors"]) == 1 and "AAPL" in actions["errors"][0]


def test_mock_watchlist_add_and_plain(client, fakes, mock_on):
    r = client.post("/api/chat", json={"message": "add PYPL"})
    assert r.json()["actions"]["watchlist_changes"] == [
        {"ticker": "PYPL", "action": "add", "status": "executed"}
    ]
    plain = client.post("/api/chat", json={"message": "hello"}).json()
    assert plain["actions"] is None and plain["message"].startswith("Mock:")
