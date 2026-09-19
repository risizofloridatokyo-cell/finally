"""`/api/watchlist` routes and service semantics."""

from __future__ import annotations

import pytest

from app import db


def tickers(client) -> list[str]:
    return [w["ticker"] for w in client.get("/api/watchlist").json()]


class TestList:
    def test_default_ten_with_prices(self, client):
        body = client.get("/api/watchlist").json()
        assert [w["ticker"] for w in body] == list(db.DEFAULT_TICKERS)
        assert all(set(w) == {"ticker", "added_at", "price"} for w in body)
        assert body[0]["price"] == 100.0

    def test_price_is_null_until_warmed(self, client):
        client.env.cache.remove("AAPL")
        by = {w["ticker"]: w["price"] for w in client.get("/api/watchlist").json()}
        assert by["AAPL"] is None
        assert by["GOOGL"] == 200.0


class TestAdd:
    def test_add_registers_with_source_and_returns_entry(self, client):
        r = client.post("/api/watchlist", json={"ticker": "PYPL"})
        assert r.status_code == 200
        body = r.json()
        assert body["ticker"] == "PYPL" and body["created"] is True
        assert body["price"] == 50.0 and body["added_at"]
        assert "PYPL" in tickers(client)
        assert "PYPL" in client.env.source.get_tickers()

    def test_add_normalises_case_and_whitespace(self, client):
        assert client.post("/api/watchlist", json={"ticker": "  pypl "}).status_code == 200
        assert "PYPL" in tickers(client)

    def test_add_is_idempotent(self, client):
        client.post("/api/watchlist", json={"ticker": "PYPL"})
        r = client.post("/api/watchlist", json={"ticker": "PYPL"})
        assert r.status_code == 200
        assert r.json()["created"] is False
        assert tickers(client).count("PYPL") == 1

    def test_readding_default_ticker_is_ok(self, client):
        r = client.post("/api/watchlist", json={"ticker": "AAPL"})
        assert r.status_code == 200 and r.json()["created"] is False

    @pytest.mark.parametrize("bad", ["", "  ", "TOOLONG", "AB1", "A.B", "BRK-B", "123"])
    def test_invalid_ticker_is_400(self, client, bad):
        r = client.post("/api/watchlist", json={"ticker": bad})
        assert r.status_code == 400
        assert r.json() == {"detail": "Invalid ticker symbol"}
        assert tickers(client) == list(db.DEFAULT_TICKERS)

    def test_missing_ticker_is_422(self, client):
        assert client.post("/api/watchlist", json={}).status_code == 422


class TestRemove:
    def test_remove_drops_row_feed_and_cache(self, client):
        r = client.delete("/api/watchlist/NFLX")
        assert r.status_code == 200
        assert r.json() == {"ticker": "NFLX", "removed": True}
        assert "NFLX" not in tickers(client)
        assert "NFLX" not in client.env.source.get_tickers()
        assert client.env.cache.get_price("NFLX") is None

    def test_remove_is_case_insensitive(self, client):
        assert client.delete("/api/watchlist/nflx").status_code == 200

    def test_remove_keeps_feed_when_position_is_held(self, client):
        client.post(
            "/api/portfolio/trade", json={"ticker": "TSLA", "quantity": 2, "side": "buy"}
        )
        assert client.delete("/api/watchlist/TSLA").status_code == 200

        assert "TSLA" not in tickers(client)
        assert "TSLA" in client.env.source.get_tickers()
        assert client.env.cache.get_price("TSLA") == 250.0
        # the held position can still be valued
        pos = client.get("/api/portfolio").json()["positions"][0]
        assert pos["ticker"] == "TSLA" and pos["current_price"] == 250.0

    def test_closing_the_last_position_drops_an_unwatched_feed(self, client):
        """hold X, remove X from watchlist -> feed retained; sell all -> feed dropped."""
        buy = {"ticker": "TSLA", "quantity": 2, "side": "buy"}
        assert client.post("/api/portfolio/trade", json=buy).status_code == 200
        client.delete("/api/watchlist/TSLA")
        assert "TSLA" in client.env.source.get_tickers()  # retained: still held

        # a partial sell keeps the position, so the feed stays
        sell_one = {"ticker": "TSLA", "quantity": 1, "side": "sell"}
        assert client.post("/api/portfolio/trade", json=sell_one).status_code == 200
        assert "TSLA" in client.env.source.get_tickers()

        assert client.post("/api/portfolio/trade", json=sell_one).status_code == 200
        assert "TSLA" not in client.env.source.get_tickers()
        assert client.env.cache.get_price("TSLA") is None
        assert client.get("/api/history", params={"ticker": "TSLA"}).status_code == 404

    def test_closing_a_position_keeps_the_feed_when_still_watched(self, client):
        client.post("/api/portfolio/trade", json={"ticker": "TSLA", "quantity": 2, "side": "buy"})
        client.post("/api/portfolio/trade", json={"ticker": "TSLA", "quantity": 2, "side": "sell"})
        assert "TSLA" in client.env.source.get_tickers()
        assert client.env.cache.get_price("TSLA") == 250.0

    def test_remove_unknown_is_404(self, client):
        assert client.delete("/api/watchlist/PYPL").status_code == 404

    def test_remove_invalid_is_400(self, client):
        assert client.delete("/api/watchlist/AB1").status_code == 400
