"""Fixtures for the LLM tests: real temp SQLite DB, fake portfolio/watchlist services, fake litellm."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.llm import service


class FakeTradeError(Exception):
    def __init__(self, message: str, status_code: int = 409):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class FakeInvalidTickerError(ValueError):
    pass


CONTEXT: dict[str, Any] = {
    "cash_balance": 8000.0,
    "realized_pnl": 12.5,
    "total_value": 10120.0,
    "total_unrealized_pnl": 107.5,
    "positions": [
        {
            "ticker": "AAPL",
            "quantity": 10,
            "avg_cost": 190.0,
            "current_price": 200.0,
            "unrealized_pnl": 100.0,
            "unrealized_pnl_pct": 5.26,
        },
        {
            "ticker": "ZZZZ",
            "quantity": 2,
            "avg_cost": 50.0,
            "current_price": None,
            "unrealized_pnl": None,
            "unrealized_pnl_pct": None,
        },
    ],
    "watchlist": [{"ticker": "AAPL", "price": 200.0}, {"ticker": "NVDA", "price": None}],
}


class FakeServices:
    """Records calls; behaviour is scriptable per test."""

    def __init__(self) -> None:
        self.trades: list[tuple[str, str, float]] = []
        self.watch_calls: list[tuple[str, str]] = []
        self.context = CONTEXT
        self.reject_trades_with: str | None = None
        self.max_buy_qty = 1_000

    def execute_trade(self, ticker: str, side: str, quantity: float) -> dict:
        if self.reject_trades_with or quantity > self.max_buy_qty:
            raise FakeTradeError(self.reject_trades_with or "Insufficient cash")
        self.trades.append((ticker, side, quantity))
        return {
            "ticker": ticker,
            "side": side,
            "quantity": quantity,
            "price": 100.0,
            "status": "executed",
        }

    def get_portfolio_context(self) -> dict:
        return self.context

    async def add_ticker(self, raw: str) -> bool:
        if not raw.isalpha() or len(raw) > 5:
            raise FakeInvalidTickerError(raw)
        self.watch_calls.append(("add", raw))
        return True

    async def remove_ticker(self, raw: str) -> bool:
        if not raw.isalpha() or len(raw) > 5:
            raise FakeInvalidTickerError(raw)
        self.watch_calls.append(("remove", raw))
        return True


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    from app import db

    db.init_db()
    return db


@pytest.fixture
def fakes(temp_db, monkeypatch) -> FakeServices:
    fake = FakeServices()
    portfolio = SimpleNamespace(
        execute_trade=fake.execute_trade,
        get_portfolio_context=fake.get_portfolio_context,
        TradeError=FakeTradeError,
    )
    watchlist = SimpleNamespace(
        add_ticker=fake.add_ticker,
        remove_ticker=fake.remove_ticker,
        InvalidTicker=FakeInvalidTickerError,
    )
    monkeypatch.setattr(service, "_portfolio", lambda: portfolio)
    monkeypatch.setattr(service, "_watchlist", lambda: watchlist)
    return fake


@pytest.fixture(autouse=True)
def _no_mock_by_default(monkeypatch):
    monkeypatch.delenv("LLM_MOCK", raising=False)


class FakeLiteLLM:
    """Replaces litellm.acompletion; feed it outputs (str) or exceptions, in order."""

    def __init__(self, outputs: list[Any]):
        self.outputs = list(outputs)
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, **kwargs: Any):
        self.calls.append(kwargs)
        out = self.outputs.pop(0)
        if isinstance(out, BaseException):
            raise out
        msg = SimpleNamespace(content=out)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


@pytest.fixture
def fake_llm(monkeypatch):
    def install(*outputs: Any) -> FakeLiteLLM:
        fake = FakeLiteLLM(list(outputs))
        monkeypatch.setattr("app.llm.client.litellm.acompletion", fake)
        return fake

    return install


@pytest.fixture
def client() -> TestClient:
    from app.llm import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)
