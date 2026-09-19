"""Portfolio valuation, context, snapshots and retention."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app import db, tasks
from app.portfolio import service
from app.portfolio.service import execute_trade
from tests.portfolio.conftest import read_state


class TestGetPortfolio:
    def test_fresh_portfolio(self, env):
        p = service.get_portfolio()
        assert p == {
            "cash_balance": 10000.0,
            "realized_pnl": 0.0,
            "positions": [],
            "total_value": 10000.0,
            "total_unrealized_pnl": 0.0,
        }

    def test_positions_report_unrealized_pnl(self, env):
        execute_trade("AAPL", "buy", 10)  # 10 @ 100
        env.cache.update("AAPL", 110.0)
        p = service.get_portfolio()

        pos = p["positions"][0]
        assert pos["ticker"] == "AAPL"
        assert pos["current_price"] == 110.0
        assert pos["market_value"] == 1100.0
        assert pos["unrealized_pnl"] == 100.0
        assert pos["unrealized_pnl_pct"] == 10.0
        assert p["total_unrealized_pnl"] == 100.0
        assert p["total_value"] == 9000.0 + 1100.0

    def test_unwarmed_position_is_null_and_excluded_from_total(self, env):
        execute_trade("AAPL", "buy", 10)
        execute_trade("MSFT", "buy", 1)  # 300
        env.cache.remove("AAPL")

        p = service.get_portfolio()
        by_ticker = {x["ticker"]: x for x in p["positions"]}
        assert by_ticker["AAPL"]["current_price"] is None
        assert by_ticker["AAPL"]["unrealized_pnl"] is None
        assert by_ticker["AAPL"]["unrealized_pnl_pct"] is None
        assert by_ticker["AAPL"]["market_value"] is None
        # cash 8700 + only MSFT market value 300
        assert p["total_value"] == 8700.0 + 300.0
        assert p["total_unrealized_pnl"] == 0.0

    def test_realized_pnl_shows_in_portfolio(self, env):
        execute_trade("AAPL", "buy", 10)
        env.cache.update("AAPL", 110.0)
        execute_trade("AAPL", "sell", 10)
        assert service.get_portfolio()["realized_pnl"] == pytest.approx(100.0)


class TestPortfolioContext:
    def test_context_adds_watchlist_with_prices(self, env):
        ctx = service.get_portfolio_context()
        assert {w["ticker"] for w in ctx["watchlist"]} == set(db.DEFAULT_TICKERS)
        assert all(w["price"] is not None for w in ctx["watchlist"])
        assert "cash_balance" in ctx and "positions" in ctx

    def test_unwarmed_watchlist_ticker_has_null_price(self, env):
        env.cache.remove("NFLX")
        ctx = service.get_portfolio_context()
        assert {w["ticker"]: w["price"] for w in ctx["watchlist"]}["NFLX"] is None


class TestSnapshots:
    def test_first_snapshot_is_recorded(self, env):
        assert service.snapshot_portfolio() is True
        assert len(read_state()["snapshots"]) == 1

    def test_unchanged_value_is_skipped(self, env):
        service.snapshot_portfolio()
        assert service.snapshot_portfolio() is False
        assert len(read_state()["snapshots"]) == 1

    def test_move_under_point_one_percent_is_skipped(self, env):
        execute_trade("AAPL", "buy", 50)  # 5000 in AAPL, snapshot recorded by the trade
        count = len(read_state()["snapshots"])
        env.cache.update("AAPL", 100.05)  # +0.05% of position ~ +2.5 on 10,000 = 0.025%
        assert service.snapshot_portfolio() is False
        assert len(read_state()["snapshots"]) == count

    def test_move_over_point_one_percent_is_recorded(self, env):
        execute_trade("AAPL", "buy", 50)
        count = len(read_state()["snapshots"])
        env.cache.update("AAPL", 101.0)  # +50 on 10,000 = 0.5%
        assert service.snapshot_portfolio() is True
        snaps = read_state()["snapshots"]
        assert len(snaps) == count + 1
        assert snaps[-1]["total_value"] == 10050.0

    def test_force_records_even_when_unchanged(self, env):
        service.snapshot_portfolio()
        assert service.snapshot_portfolio(force=True) is True
        assert len(read_state()["snapshots"]) == 2


class TestRetention:
    def test_prune_deletes_only_rows_older_than_30_days(self, env):
        old = (datetime.now(UTC) - timedelta(days=31)).isoformat()
        recent = (datetime.now(UTC) - timedelta(days=5)).isoformat()
        with db.get_conn() as conn:
            db.insert_snapshot(conn, 111.0, recorded_at=old)
            db.insert_snapshot(conn, 222.0, recorded_at=recent)

        assert tasks.prune_old_snapshots() == 1
        values = [s["total_value"] for s in read_state()["snapshots"]]
        assert values == [222.0]
