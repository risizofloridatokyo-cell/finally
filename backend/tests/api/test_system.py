"""History, health, startup sequence, static serving and SSE wiring."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app import db, state
from app.main import create_app
from app.market.cache import HISTORY_MAXLEN
from tests.portfolio.stubs import StubSource


class TestHistory:
    def test_history_is_oldest_first(self, client):
        for price in (101.0, 102.0, 103.0):
            client.env.cache.update("AAPL", price)
        body = client.get("/api/history", params={"ticker": "AAPL"}).json()
        assert body["ticker"] == "AAPL"
        assert [p["price"] for p in body["points"]] == [100.0, 101.0, 102.0, 103.0]
        assert set(body["points"][0]) == {"price", "timestamp"}

    def test_history_limit_returns_most_recent(self, client):
        for price in (101.0, 102.0, 103.0):
            client.env.cache.update("AAPL", price)
        body = client.get("/api/history", params={"ticker": "AAPL", "limit": 2}).json()
        assert [p["price"] for p in body["points"]] == [102.0, 103.0]

    def test_history_is_bounded_by_ring_buffer(self, client):
        for i in range(HISTORY_MAXLEN + 50):
            client.env.cache.update("AAPL", 100.0 + i)
        body = client.get("/api/history", params={"ticker": "AAPL", "limit": 10_000}).json()
        assert len(body["points"]) == HISTORY_MAXLEN
        assert body["points"][-1]["price"] == 100.0 + HISTORY_MAXLEN + 49

    def test_history_unknown_ticker_is_404(self, client):
        assert client.get("/api/history", params={"ticker": "ZZZZ"}).status_code == 404

    def test_history_is_case_insensitive(self, client):
        assert client.get("/api/history", params={"ticker": "aapl"}).status_code == 200

    def test_history_requires_ticker(self, client):
        assert client.get("/api/history").status_code == 422

    def test_tracked_but_unwarmed_ticker_is_empty_200(self, client):
        client.env.cache.remove("AAPL")
        r = client.get("/api/history", params={"ticker": "AAPL"})
        assert r.status_code == 200 and r.json()["points"] == []


class TestHealth:
    def test_ok(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}

    def test_503_when_market_task_is_down(self, client):
        client.env.source._running = False
        r = client.get("/api/health")
        assert r.status_code == 503
        assert r.json()["status"] == "degraded"
        assert "market" in r.json()["detail"]

    def test_503_when_db_is_unreachable(self, client, monkeypatch):
        monkeypatch.setattr(db, "check_db", lambda: False)
        r = client.get("/api/health")
        assert r.status_code == 503
        assert r.json()["status"] == "degraded"
        assert "database" in r.json()["detail"]


class TestStartupSequence:
    def _start(self, api_env):
        app = create_app(cache=api_env.cache, source=api_env.source, start_background_tasks=False)
        return TestClient(app)

    def test_default_ten_on_fresh_db(self, api_env):
        with self._start(api_env):
            assert sorted(api_env.source.get_tickers()) == sorted(db.DEFAULT_TICKERS)

    def test_uses_watchlist_union_positions_not_the_default_ten(self, api_env):
        db.init_db()
        with db.get_conn() as conn:
            for t in db.DEFAULT_TICKERS:
                if t != "MSFT":
                    db.remove_watchlist(conn, t)  # watchlist is now just MSFT
            db.add_watchlist(conn, "PYPL")
            db.upsert_position(conn, "TSLA", 3.0, 200.0)  # held but not watched
            db.upsert_position(conn, "MSFT", 1.0, 250.0)  # held and watched (dedupe)

        with self._start(api_env):
            assert sorted(api_env.source.get_tickers()) == ["MSFT", "PYPL", "TSLA"]
            assert api_env.cache.get_price("TSLA") is not None

    def test_runtime_singletons_set_during_lifespan_and_cleared_after(self, api_env):
        with self._start(api_env):
            assert state.get_cache() is api_env.cache
            assert state.get_source() is api_env.source
        assert api_env.source.is_running() is False
        try:
            state.get_cache()
        except RuntimeError:
            pass
        else:
            raise AssertionError("state should be cleared after shutdown")

    def test_initial_snapshot_recorded_on_startup(self, api_env):
        app = create_app(cache=api_env.cache, source=StubSource(api_env.cache))
        with TestClient(app) as c:
            body = c.get("/api/portfolio/history").json()
        assert len(body) == 1 and body[0]["total_value"] == 10000.0


class TestStaticAndRouting:
    def test_missing_static_dir_does_not_crash(self, client):
        assert client.get("/api/health").status_code == 200
        assert client.get("/").status_code == 404

    def test_static_served_at_root_but_api_wins(self, api_env, monkeypatch):
        static = api_env.tmp_path / "static"
        static.mkdir()
        (static / "index.html").write_text("<html>FinAlly</html>", encoding="utf-8")
        monkeypatch.setenv("STATIC_DIR", str(static))

        app = create_app(cache=api_env.cache, source=api_env.source, start_background_tasks=False)
        with TestClient(app) as c:
            assert "FinAlly" in c.get("/").text
            assert c.get("/api/health").json() == {"status": "ok"}
            assert c.get("/api/watchlist").status_code == 200

    def test_expected_api_routes_are_registered(self, client):
        paths = {getattr(r, "path", None) for r in client.app.routes}
        for expected in (
            "/api/stream/prices",
            "/api/history",
            "/api/health",
            "/api/portfolio",
            "/api/portfolio/trade",
            "/api/portfolio/history",
            "/api/watchlist",
            "/api/watchlist/{ticker}",
        ):
            assert expected in paths
