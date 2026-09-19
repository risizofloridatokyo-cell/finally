from app.llm.prompts import (
    build_messages,
    build_reprompt,
    format_portfolio_context,
    summarize_actions,
)

from .conftest import CONTEXT


def test_context_formatting_includes_data_and_unavailable_annotation():
    text = format_portfolio_context(CONTEXT)
    assert "$8,000.00" in text and "$10,120.00" in text
    assert "AAPL: 10 shares" in text and "current price $200.00" in text
    assert "ZZZZ: 2 shares" in text and "price unavailable" in text
    assert "NVDA: price unavailable" in text


def test_context_formatting_empty_portfolio():
    text = format_portfolio_context({"cash_balance": 10000.0, "positions": [], "watchlist": []})
    assert "(none)" in text and "(empty)" in text


def test_system_prompt_has_guidance_and_context():
    msgs = build_messages(CONTEXT, [], "put $2000 into NVDA")
    system = msgs[0]["content"]
    assert msgs[0]["role"] == "system"
    assert msgs[-1] == {"role": "user", "content": "put $2000 into NVDA"}
    assert "FinAlly, an AI trading assistant" in system
    assert "dollars / price" in system and "sell half my Tesla" in system  # conversions
    assert "Never invent tickers or prices" in system
    assert "valid JSON" in system and '"watchlist_changes"' in system
    assert "Cash balance: $8,000.00" in system


def test_history_order_and_action_notes():
    history = [
        {"role": "user", "content": "buy aapl", "actions": None},
        {
            "role": "assistant",
            "content": "Done.",
            "actions": {
                "trades": [
                    {
                        "ticker": "AAPL",
                        "side": "buy",
                        "quantity": 5,
                        "price": 100.0,
                        "status": "executed",
                    }
                ],
                "watchlist_changes": [],
                "errors": [],
            },
        },
    ]
    msgs = build_messages(CONTEXT, history, "next")
    assert [m["role"] for m in msgs] == ["system", "user", "assistant", "user"]
    assert "executed buy 5 AAPL @ $100.00" in msgs[2]["content"]
    assert msgs[1]["content"] == "buy aapl"


def test_summarize_actions_rejections():
    note = summarize_actions(
        {
            "trades": [
                {"ticker": "TSLA", "side": "buy", "quantity": 9, "price": None, "status": "rejected"}
            ],
            "watchlist_changes": [],
            "errors": ["TSLA buy rejected: Insufficient cash"],
        }
    )
    assert "REJECTED buy 9 TSLA" in note and "Insufficient cash" in note
    assert summarize_actions(None) == ""


def test_reprompt_carries_raw_output_and_schema():
    base = [{"role": "user", "content": "hi"}]
    out = build_reprompt(base, "garbage {", "not JSON")
    assert out[:-1] == base and out[-1]["role"] == "user"
    assert "garbage {" in out[-1]["content"]
    assert "valid JSON matching this schema" in out[-1]["content"]
