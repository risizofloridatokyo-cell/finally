import json

import pytest

from app.llm.schemas import ChatRequest, parse_llm_output


def test_message_only():
    r = parse_llm_output('{"message": "hi"}')
    assert r.message == "hi" and r.trades == [] and r.watchlist_changes == []


def test_all_fields():
    raw = json.dumps(
        {
            "message": "ok",
            "trades": [{"ticker": "AAPL", "side": "buy", "quantity": 10}],
            "watchlist_changes": [{"ticker": "PYPL", "action": "add"}],
        }
    )
    r = parse_llm_output(raw)
    assert (r.trades[0].ticker, r.trades[0].side, r.trades[0].quantity) == ("AAPL", "buy", 10)
    assert (r.watchlist_changes[0].ticker, r.watchlist_changes[0].action) == ("PYPL", "add")


def test_null_lists_and_fractional_qty_and_normalisation():
    r = parse_llm_output(
        '{"message":"m","trades":[{"ticker":" nvda ","side":"SELL","quantity":0.25}],'
        '"watchlist_changes":null}'
    )
    assert r.trades[0].ticker == "NVDA" and r.trades[0].side == "sell"
    assert r.trades[0].quantity == 0.25 and r.watchlist_changes == []


def test_code_fence_tolerated():
    assert parse_llm_output('```json\n{"message": "x"}\n```').message == "x"


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "",
        "not json",
        "[1, 2]",
        '{"trades": []}',
        '{"message": "m", "trades": [{"ticker": "A", "side": "hold", "quantity": 1}]}',
        '{"message": "m", "trades": [{"ticker": "A", "side": "buy"}]}',
        '{"message": "m", "watchlist_changes": [{"ticker": "A", "action": "pin"}]}',
    ],
)
def test_invalid_raises_value_error(raw):
    with pytest.raises(ValueError):
        parse_llm_output(raw)


def test_chat_request_strips_and_rejects_blank():
    assert ChatRequest(message="  hello ").message == "hello"
    with pytest.raises(ValueError):
        ChatRequest(message="   ")
