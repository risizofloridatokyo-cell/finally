"""End-to-end chat flow: fake litellm + real temp DB + fake portfolio/watchlist services."""

from __future__ import annotations

import asyncio
import json

import pytest

from app.llm.client import EXTRA_BODY, MODEL, UNAVAILABLE_MESSAGE, UNREADABLE_MESSAGE


def _msgs(temp_db):
    with temp_db.get_conn() as conn:
        return temp_db.recent_chat_messages(conn, 100)


def _ok(message="Hello", trades=(), changes=()):
    return json.dumps(
        {"message": message, "trades": list(trades), "watchlist_changes": list(changes)}
    )


def test_plain_reply_persists_both_messages_with_null_actions(client, fakes, temp_db, fake_llm):
    llm = fake_llm(_ok("You hold 10 AAPL."))
    r = client.post("/api/chat", json={"message": "how am I doing?"})
    assert r.status_code == 200
    assert r.json() == {"message": "You hold 10 AAPL.", "actions": None}
    rows = _msgs(temp_db)
    assert [(m["role"], m["content"], m["actions"]) for m in rows] == [
        ("user", "how am I doing?", None),
        ("assistant", "You hold 10 AAPL.", None),
    ]
    call = llm.calls[0]
    assert call["model"] == MODEL and call["extra_body"] == EXTRA_BODY
    assert call["timeout"] == 30 and call["response_format"]["type"] == "json_schema"


def test_prompt_includes_portfolio_context_and_conversion_rules(client, fakes, fake_llm):
    llm = fake_llm(_ok())
    client.post("/api/chat", json={"message": "put $2,000 into NVDA"})
    messages = llm.calls[0]["messages"]
    system = messages[0]["content"]
    assert "Cash balance: $8,000.00" in system
    assert "AAPL: 10 shares" in system and "price unavailable" in system
    assert "dollars / price" in system and "position quantity" in system
    assert messages[-1] == {"role": "user", "content": "put $2,000 into NVDA"}


def test_trade_and_watchlist_executed_and_recorded(client, fakes, temp_db, fake_llm):
    fake_llm(
        _ok(
            "Buying and adding.",
            trades=[{"ticker": "aapl", "side": "buy", "quantity": 10}],
            changes=[{"ticker": "PYPL", "action": "add"}, {"ticker": "TSLA", "action": "remove"}],
        )
    )
    r = client.post("/api/chat", json={"message": "go"})
    assert r.status_code == 200
    actions = r.json()["actions"]
    assert actions == {
        "trades": [
            {"ticker": "AAPL", "side": "buy", "quantity": 10, "price": 100.0, "status": "executed"}
        ],
        "watchlist_changes": [
            {"ticker": "PYPL", "action": "add", "status": "executed"},
            {"ticker": "TSLA", "action": "remove", "status": "executed"},
        ],
        "errors": [],
    }
    assert fakes.trades == [("AAPL", "buy", 10)]
    assert fakes.watch_calls == [("add", "PYPL"), ("remove", "TSLA")]
    assert _msgs(temp_db)[1]["actions"] == actions


def test_rejected_trade_is_200_with_errors(client, fakes, temp_db, fake_llm):
    fake_llm(_ok("Trying.", trades=[{"ticker": "TSLA", "side": "buy", "quantity": 5000}]))
    r = client.post("/api/chat", json={"message": "buy lots"})
    assert r.status_code == 200
    actions = r.json()["actions"]
    assert actions["trades"] == [
        {"ticker": "TSLA", "side": "buy", "quantity": 5000, "price": None, "status": "rejected"}
    ]
    assert actions["errors"] == ["TSLA buy rejected: Insufficient cash"]
    assert len(_msgs(temp_db)) == 2  # still stored


def test_partial_failure_other_trades_still_execute(client, fakes, fake_llm):
    fake_llm(
        _ok(
            "Two orders.",
            trades=[
                {"ticker": "TSLA", "side": "buy", "quantity": 5000},
                {"ticker": "AAPL", "side": "sell", "quantity": 1},
            ],
        )
    )
    actions = client.post("/api/chat", json={"message": "x"}).json()["actions"]
    assert [t["status"] for t in actions["trades"]] == ["rejected", "executed"]
    assert len(actions["errors"]) == 1


def test_invalid_watchlist_ticker_rejected(client, fakes, fake_llm):
    fake_llm(_ok("Adding.", changes=[{"ticker": "TOOLONGX", "action": "add"}]))
    actions = client.post("/api/chat", json={"message": "x"}).json()["actions"]
    assert actions["watchlist_changes"] == [
        {"ticker": "TOOLONGX", "action": "add", "status": "rejected"}
    ]
    assert actions["errors"] == ["Invalid ticker symbol: TOOLONGX"]


def test_history_window_is_last_20_oldest_first(client, fakes, temp_db, fake_llm):
    with temp_db.get_conn() as conn:
        for i in range(30):
            temp_db.insert_chat_message(conn, "user" if i % 2 == 0 else "assistant", f"m{i}")
    llm = fake_llm(_ok())
    client.post("/api/chat", json={"message": "new"})
    history = llm.calls[0]["messages"][1:-1]
    assert [m["content"] for m in history] == [f"m{i}" for i in range(10, 30)]
    assert len(history) == 20


def test_one_reprompt_then_success(client, fakes, temp_db, fake_llm):
    llm = fake_llm("this is not json", _ok("Recovered."))
    r = client.post("/api/chat", json={"message": "hi"})
    assert r.status_code == 200 and r.json()["message"] == "Recovered."
    assert len(llm.calls) == 2
    retry_msgs = llm.calls[1]["messages"]
    assert "this is not json" in retry_msgs[-1]["content"]
    assert len(retry_msgs) == len(llm.calls[0]["messages"]) + 1
    assert len(_msgs(temp_db)) == 2


def test_schema_invalid_then_success(client, fakes, fake_llm):
    llm = fake_llm('{"trades": []}', _ok("ok"))
    assert client.post("/api/chat", json={"message": "hi"}).status_code == 200
    assert len(llm.calls) == 2


def test_two_malformed_outputs_give_503_and_persist_nothing(client, fakes, temp_db, fake_llm):
    llm = fake_llm("nope", "still nope")
    r = client.post("/api/chat", json={"message": "hi"})
    assert r.status_code == 503 and r.json() == {"detail": UNREADABLE_MESSAGE}
    assert len(llm.calls) == 2  # exactly one reprompt
    assert _msgs(temp_db) == []
    assert fakes.trades == []


@pytest.mark.parametrize(
    "exc",
    [TimeoutError("timed out"), ConnectionError("boom"), RuntimeError("500 upstream")],
)
def test_upstream_failure_gives_503_and_persists_nothing(client, fakes, temp_db, fake_llm, exc):
    fake_llm(exc)
    r = client.post("/api/chat", json={"message": "hi"})
    assert r.status_code == 503 and r.json() == {"detail": UNAVAILABLE_MESSAGE}
    assert _msgs(temp_db) == []


def test_litellm_specific_errors_map_to_503(client, fakes, temp_db, fake_llm):
    import litellm

    fake_llm(litellm.RateLimitError("slow down", "openrouter", MODEL))
    r = client.post("/api/chat", json={"message": "hi"})
    assert r.status_code == 503 and r.json() == {"detail": UNAVAILABLE_MESSAGE}
    assert _msgs(temp_db) == []


def test_failure_on_reprompt_call_is_unavailable_and_persists_nothing(
    client, fakes, temp_db, fake_llm
):
    fake_llm("garbage", TimeoutError())
    r = client.post("/api/chat", json={"message": "hi"})
    assert r.status_code == 503 and r.json() == {"detail": UNAVAILABLE_MESSAGE}
    assert _msgs(temp_db) == []


def test_hard_timeout_enforced(client, fakes, temp_db, monkeypatch):
    async def hang(**_kwargs):
        await asyncio.sleep(10)

    monkeypatch.setattr("app.llm.client.litellm.acompletion", hang)
    monkeypatch.setattr("app.llm.client.TIMEOUT_SECONDS", 0.05)
    r = client.post("/api/chat", json={"message": "hi"})
    assert r.status_code == 503 and r.json() == {"detail": UNAVAILABLE_MESSAGE}
    assert _msgs(temp_db) == []


@pytest.mark.parametrize("body", [{"message": ""}, {"message": "   "}, {}, {"message": 5}])
def test_bad_request_bodies_are_422(client, fakes, body):
    assert client.post("/api/chat", json=body).status_code == 422


def test_sync_watchlist_service_also_supported(client, fakes, temp_db, fake_llm, monkeypatch):
    from types import SimpleNamespace

    from app.llm import service

    calls = []
    sync_watchlist = SimpleNamespace(
        add_ticker=lambda t: calls.append(("add", t)) or True,
        remove_ticker=lambda t: calls.append(("remove", t)) or True,
        InvalidTicker=ValueError,
    )
    monkeypatch.setattr(service, "_watchlist", lambda: sync_watchlist)
    fake_llm(_ok("Adding.", changes=[{"ticker": "PYPL", "action": "add"}]))
    r = client.post("/api/chat", json={"message": "x"})
    assert r.json()["actions"]["watchlist_changes"][0]["status"] == "executed"
    assert calls == [("add", "PYPL")]
