"""`/api/portfolio*` route behaviour: status codes and response shapes."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app import db
from app.portfolio import service


def trade(client, ticker="AAPL", quantity=10, side="buy"):
    return client.post(
        "/api/portfolio/trade", json={"ticker": ticker, "quantity": quantity, "side": side}
    )


class TestGetPortfolio:
    def test_fresh_portfolio_shape(self, client):
        body = client.get("/api/portfolio").json()
        assert body == {
            "cash_balance": 10000.0,
            "realized_pnl": 0.0,
            "positions": [],
            "total_value": 10000.0,
            "total_unrealized_pnl": 0.0,
        }

    def test_position_shape_after_buy(self, client):
        trade(client, quantity=10)
        body = client.get("/api/portfolio").json()
        assert body["cash_balance"] == 9000.0
        assert body["positions"] == [
            {
                "ticker": "AAPL",
                "quantity": 10.0,
                "avg_cost": 100.0,
                "current_price": 100.0,
                "market_value": 1000.0,
                "unrealized_pnl": 0.0,
                "unrealized_pnl_pct": 0.0,
            }
        ]
        assert body["total_value"] == 10000.0


class TestTradeRoute:
    def test_buy_then_sell(self, client):
        r = trade(client, quantity=10)
        assert r.status_code == 200
        assert r.json() == {
            "ticker": "AAPL",
            "side": "buy",
            "quantity": 10.0,
            "price": 100.0,
            "status": "executed",
        }
        client.env.cache.update("AAPL", 120.0)
        assert trade(client, quantity=10, side="sell").status_code == 200
        body = client.get("/api/portfolio").json()
        assert body["positions"] == []
        assert body["cash_balance"] == 10200.0
        assert body["realized_pnl"] == 200.0

    def test_insufficient_cash_is_409_with_detail(self, client):
        r = trade(client, quantity=1000)
        assert r.status_code == 409
        assert "Insufficient cash" in r.json()["detail"]

    def test_insufficient_shares_is_409(self, client):
        assert trade(client, quantity=1, side="sell").status_code == 409

    def test_untracked_ticker_is_404(self, client):
        assert trade(client, ticker="ZZZZ").status_code == 404

    def test_bad_inputs_are_400(self, client):
        assert trade(client, quantity=0).status_code == 400
        assert trade(client, quantity=-5).status_code == 400
        assert trade(client, quantity=2e9).status_code == 400
        assert trade(client, side="hold").status_code == 400
        assert trade(client, ticker="not a ticker").status_code == 400

    def test_nan_quantity_is_400(self, client):
        r = client.post(
            "/api/portfolio/trade",
            content='{"ticker":"AAPL","quantity":NaN,"side":"buy"}',
            headers={"content-type": "application/json"},
        )
        assert r.status_code in (400, 422)

    def test_missing_field_is_422(self, client):
        r = client.post("/api/portfolio/trade", json={"ticker": "AAPL"})
        assert r.status_code == 422

    def test_route_and_llm_path_share_execute_trade(self, client, monkeypatch):
        calls = []

        def spy(ticker, side, quantity):
            calls.append((ticker, side, quantity))
            return {"ticker": ticker, "side": side, "quantity": quantity, "price": 1.0,
                    "status": "executed"}

        monkeypatch.setattr(service, "execute_trade", spy)
        assert trade(client, quantity=3).status_code == 200
        assert calls == [("AAPL", "buy", 3.0)]


class TestPortfolioHistory:
    def _seed(self):
        now = datetime.now(UTC)
        with db.get_conn() as conn:
            for i in range(10):
                db.insert_snapshot(
                    conn, 10000.0 + i, recorded_at=(now - timedelta(minutes=10 - i)).isoformat()
                )

    def test_returns_oldest_first_list_of_snapshots(self, client):
        self._seed()
        body = client.get("/api/portfolio/history").json()
        assert isinstance(body, list)
        assert set(body[0]) == {"total_value", "recorded_at"}
        times = [s["recorded_at"] for s in body]
        assert times == sorted(times)

    def test_limit_returns_most_recent_rows(self, client):
        self._seed()
        body = client.get("/api/portfolio/history", params={"limit": 3}).json()
        assert [s["total_value"] for s in body] == [10007.0, 10008.0, 10009.0]

    def test_since_filters(self, client):
        self._seed()
        since = (datetime.now(UTC) - timedelta(minutes=3, seconds=30)).isoformat()
        body = client.get("/api/portfolio/history", params={"since": since}).json()
        assert [s["total_value"] for s in body] == [10007.0, 10008.0, 10009.0]

    def test_since_with_unescaped_plus_offset(self, client):
        self._seed()
        since = (datetime.now(UTC) - timedelta(minutes=3, seconds=30)).isoformat()
        assert "+00:00" in since
        # a raw '+' in a URL decodes to a space; the route must cope
        r = client.get(f"/api/portfolio/history?since={since}")
        assert r.status_code == 200
        assert len(r.json()) == 3

    def test_invalid_since_is_400(self, client):
        assert client.get("/api/portfolio/history?since=yesterday").status_code == 400

    def test_bad_limit_is_422(self, client):
        assert client.get("/api/portfolio/history?limit=0").status_code == 422

    def test_full_series_is_downsampled_to_about_300(self, client):
        base = datetime.now(UTC) - timedelta(days=2)
        with db.get_conn() as conn:
            for i in range(1000):
                db.insert_snapshot(
                    conn, float(i), recorded_at=(base + timedelta(seconds=i)).isoformat()
                )
        body = client.get("/api/portfolio/history").json()
        assert 250 <= len(body) <= 300
        assert body[0]["total_value"] == 0.0
        assert body[-1]["total_value"] == 999.0
