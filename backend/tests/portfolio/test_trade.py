"""Trade execution: validation order, avg-cost, realized P&L, atomicity, locking."""

from __future__ import annotations

import asyncio
import threading

import pytest

from app import db
from app.portfolio import service
from app.portfolio.service import TradeError, execute_trade
from tests.portfolio.conftest import read_state


def set_price(env, ticker: str, price: float) -> None:
    env.cache.update(ticker, price)


class TestBuy:
    def test_buy_creates_position_and_updates_cash(self, env):
        result = execute_trade("AAPL", "buy", 10)

        assert result == {
            "ticker": "AAPL",
            "side": "buy",
            "quantity": 10.0,
            "price": 100.0,
            "status": "executed",
        }
        st = read_state()
        assert st["profile"]["cash_balance"] == 9000.0
        assert st["positions"]["AAPL"]["quantity"] == 10.0
        assert st["positions"]["AAPL"]["avg_cost"] == 100.0
        assert len(st["trades"]) == 1
        assert st["trades"][0]["side"] == "buy"

    def test_ticker_is_normalised(self, env):
        assert execute_trade(" aapl ", "BUY", 1)["ticker"] == "AAPL"

    def test_avg_cost_is_weighted_average_on_buys(self, env):
        execute_trade("AAPL", "buy", 10)  # 10 @ 100
        set_price(env, "AAPL", 130.0)
        execute_trade("AAPL", "buy", 20)  # 20 @ 130

        pos = read_state()["positions"]["AAPL"]
        assert pos["quantity"] == 30.0
        assert pos["avg_cost"] == pytest.approx((10 * 100 + 20 * 130) / 30)

    def test_fractional_shares(self, env):
        execute_trade("AAPL", "buy", 2.5)
        st = read_state()
        assert st["positions"]["AAPL"]["quantity"] == 2.5
        assert st["profile"]["cash_balance"] == 9750.0

    def test_buy_using_exactly_all_cash_is_allowed(self, env):
        execute_trade("AAPL", "buy", 100)  # 100 * 100 = 10,000
        assert read_state()["profile"]["cash_balance"] == 0.0

    def test_trade_writes_a_forced_snapshot(self, env):
        before = len(read_state()["snapshots"])
        execute_trade("AAPL", "buy", 10)
        snaps = read_state()["snapshots"]
        assert len(snaps) == before + 1
        assert snaps[-1]["total_value"] == 10000.0


class TestSell:
    def test_sell_keeps_avg_cost_and_reduces_quantity(self, env):
        execute_trade("AAPL", "buy", 10)
        set_price(env, "AAPL", 120.0)
        execute_trade("AAPL", "sell", 4)

        st = read_state()
        assert st["positions"]["AAPL"]["quantity"] == 6.0
        assert st["positions"]["AAPL"]["avg_cost"] == 100.0
        assert st["profile"]["cash_balance"] == 9000.0 + 4 * 120.0

    def test_realized_pnl_accumulates_across_buy_partial_sell_sell(self, env):
        execute_trade("AAPL", "buy", 10)  # 10 @ 100
        set_price(env, "AAPL", 120.0)
        execute_trade("AAPL", "sell", 4)  # +80
        assert read_state()["profile"]["realized_pnl"] == pytest.approx(80.0)

        set_price(env, "AAPL", 90.0)
        execute_trade("AAPL", "sell", 6)  # -60 -> total +20
        st = read_state()
        assert st["profile"]["realized_pnl"] == pytest.approx(20.0)
        assert "AAPL" not in st["positions"]

    def test_sell_at_a_loss_reduces_realized_pnl(self, env):
        execute_trade("AAPL", "buy", 10)
        set_price(env, "AAPL", 80.0)
        execute_trade("AAPL", "sell", 10)
        assert read_state()["profile"]["realized_pnl"] == pytest.approx(-200.0)

    def test_realized_pnl_uses_weighted_avg_cost_after_two_buys(self, env):
        execute_trade("AAPL", "buy", 10)  # @100
        set_price(env, "AAPL", 200.0)
        execute_trade("AAPL", "buy", 10)  # @200 -> avg 150
        execute_trade("AAPL", "sell", 20)  # @200 -> (200-150)*20 = 1000
        assert read_state()["profile"]["realized_pnl"] == pytest.approx(1000.0)

    def test_position_row_deleted_when_fully_sold(self, env):
        execute_trade("AAPL", "buy", 10)
        execute_trade("AAPL", "sell", 10)
        assert "AAPL" not in read_state()["positions"]

    def test_dust_below_epsilon_deletes_the_row(self, env):
        execute_trade("AAPL", "buy", 10)
        execute_trade("AAPL", "sell", 10 - 5e-7)  # leaves 5e-7 of a share
        assert "AAPL" not in read_state()["positions"]

    def test_sell_overshoot_within_epsilon_is_clamped(self, env):
        execute_trade("AAPL", "buy", 10)
        result = execute_trade("AAPL", "sell", 10 + 5e-7)
        assert result["quantity"] == 10.0
        st = read_state()
        assert "AAPL" not in st["positions"]
        assert st["profile"]["cash_balance"] == 10000.0

    def test_sell_more_than_held_is_rejected(self, env):
        execute_trade("AAPL", "buy", 5)
        with pytest.raises(TradeError) as exc:
            execute_trade("AAPL", "sell", 6)
        assert exc.value.status_code == 409
        assert read_state()["positions"]["AAPL"]["quantity"] == 5.0

    def test_sell_without_position_is_rejected(self, env):
        with pytest.raises(TradeError) as exc:
            execute_trade("AAPL", "sell", 1)
        assert exc.value.status_code == 409


class TestFeedReleaseOnClose:
    @staticmethod
    def _unwatch(ticker: str) -> None:
        with db.get_conn() as conn:
            db.remove_watchlist(conn, ticker)

    def test_sync_caller_drops_feed_for_closed_unwatched_position(self, env):
        execute_trade("TSLA", "buy", 2)
        self._unwatch("TSLA")
        execute_trade("TSLA", "sell", 1)
        assert "TSLA" in env.source.get_tickers()  # still held

        execute_trade("TSLA", "sell", 1)
        assert "TSLA" not in env.source.get_tickers()
        assert env.cache.get_price("TSLA") is None

    def test_watched_ticker_keeps_its_feed_after_close(self, env):
        execute_trade("TSLA", "buy", 2)
        execute_trade("TSLA", "sell", 2)
        assert "TSLA" in env.source.get_tickers()
        assert env.cache.get_price("TSLA") is not None

    async def test_event_loop_caller_schedules_the_release(self, env):
        execute_trade("TSLA", "buy", 2)
        self._unwatch("TSLA")
        execute_trade("TSLA", "sell", 2)  # called on the loop thread: fire-and-forget
        for _ in range(20):
            if "TSLA" not in env.source.get_tickers():
                break
            await asyncio.sleep(0.01)
        assert "TSLA" not in env.source.get_tickers()

    def test_release_failure_never_fails_the_trade(self, env, monkeypatch):
        async def boom(ticker):
            raise RuntimeError("source exploded")

        monkeypatch.setattr(service, "release_feed_if_unused", boom)
        execute_trade("TSLA", "buy", 2)
        self._unwatch("TSLA")
        assert execute_trade("TSLA", "sell", 2)["status"] == "executed"
        assert "TSLA" not in read_state()["positions"]


class TestValidation:
    @pytest.mark.parametrize("qty", [0, -1, -0.0001])
    def test_non_positive_quantity_rejected(self, env, qty):
        with pytest.raises(TradeError) as exc:
            execute_trade("AAPL", "buy", qty)
        assert exc.value.status_code == 400

    @pytest.mark.parametrize("qty", [float("nan"), float("inf"), float("-inf")])
    def test_non_finite_quantity_rejected(self, env, qty):
        with pytest.raises(TradeError) as exc:
            execute_trade("AAPL", "buy", qty)
        assert exc.value.status_code == 400

    def test_quantity_above_cap_rejected(self, env):
        with pytest.raises(TradeError) as exc:
            execute_trade("AAPL", "buy", 1e9 + 1)
        assert exc.value.status_code == 400

    def test_non_numeric_quantity_rejected(self, env):
        with pytest.raises(TradeError) as exc:
            execute_trade("AAPL", "buy", "lots")
        assert exc.value.status_code == 400

    @pytest.mark.parametrize("side", ["hold", "", None, 3])
    def test_bad_side_rejected(self, env, side):
        with pytest.raises(TradeError) as exc:
            execute_trade("AAPL", side, 1)
        assert exc.value.status_code == 400

    @pytest.mark.parametrize("ticker", ["", "TOOLONG", "AA1", "A-B", None])
    def test_malformed_ticker_rejected(self, env, ticker):
        with pytest.raises(TradeError) as exc:
            execute_trade(ticker, "buy", 1)
        assert exc.value.status_code == 400

    def test_untracked_ticker_is_404(self, env):
        with pytest.raises(TradeError) as exc:
            execute_trade("ZZZZ", "buy", 1)
        assert exc.value.status_code == 404

    def test_unwarmed_price_is_rejected(self, env):
        env.cache.remove("AAPL")  # still tracked by the source, but no price yet
        with pytest.raises(TradeError) as exc:
            execute_trade("AAPL", "buy", 1)
        assert exc.value.status_code == 409
        assert "not available" in exc.value.message

    def test_ticker_is_checked_before_side_and_quantity(self, env):
        with pytest.raises(TradeError) as exc:
            execute_trade("ZZZZ", "bogus", -5)
        assert exc.value.status_code == 404

    def test_side_is_checked_before_quantity(self, env):
        with pytest.raises(TradeError) as exc:
            execute_trade("AAPL", "bogus", -5)
        assert "Side" in exc.value.message

    def test_insufficient_cash_rejected_and_nothing_changes(self, env):
        with pytest.raises(TradeError) as exc:
            execute_trade("AAPL", "buy", 101)  # 10,100 > 10,000
        assert exc.value.status_code == 409
        assert "Insufficient cash" in exc.value.message
        st = read_state()
        assert st["profile"]["cash_balance"] == 10000.0
        assert st["positions"] == {}
        assert st["trades"] == []


class TestAtomicityAndPrecision:
    def test_failure_mid_transaction_rolls_everything_back(self, env, monkeypatch):
        def boom(*args, **kwargs):
            raise RuntimeError("disk on fire")

        monkeypatch.setattr(db, "insert_trade", boom)
        with pytest.raises(RuntimeError):
            execute_trade("AAPL", "buy", 10)

        st = read_state()
        assert st["profile"]["cash_balance"] == 10000.0
        assert st["positions"] == {}

    def test_no_cash_drift_over_many_buy_sell_cycles(self, env):
        prices = [101.37, 87.91, 233.33, 19.99, 0.37, 1234.56]
        quantities = [0.333, 1.5, 7.0, 0.01, 12.345, 0.1]
        set_price(env, "AAPL", 101.37)
        for i in range(300):
            p = prices[i % len(prices)]
            q = quantities[i % len(quantities)]
            set_price(env, "AAPL", p)
            if q * p > 9000:
                q = 1.0
            execute_trade("AAPL", "buy", q)
            execute_trade("AAPL", "sell", q)

            cash = read_state()["profile"]["cash_balance"]
            assert cash == round(cash, 2)

        # every round trip fills at one price, so cash must come back exactly
        assert read_state()["profile"]["cash_balance"] == 10000.0
        assert read_state()["positions"] == {}

    def test_concurrent_buys_cannot_double_spend(self, env):
        results: list[str] = []
        lock = threading.Lock()

        def buy():
            try:
                execute_trade("AAPL", "buy", 50)  # 5,000 each; only two fit in 10,000
                outcome = "ok"
            except TradeError:
                outcome = "rejected"
            with lock:
                results.append(outcome)

        threads = [threading.Thread(target=buy) for _ in range(12)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert results.count("ok") == 2
        st = read_state()
        assert st["profile"]["cash_balance"] == 0.0
        assert st["positions"]["AAPL"]["quantity"] == 100.0

    def test_trade_function_is_guarded_by_a_lock(self, env):
        assert hasattr(service._trade_lock, "acquire")
        with service._trade_lock:
            blocked = threading.Event()

            def attempt():
                execute_trade("AAPL", "buy", 1)
                blocked.set()

            t = threading.Thread(target=attempt)
            t.start()
            t.join(timeout=0.3)
            assert t.is_alive() and not blocked.is_set()  # waiting on the lock
        t.join(timeout=5)
        assert blocked.is_set()
