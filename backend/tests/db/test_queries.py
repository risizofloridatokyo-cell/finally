import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from app.db import (
    add_watchlist,
    delete_position,
    get_conn,
    get_position,
    get_profile,
    insert_chat_message,
    insert_snapshot,
    insert_trade,
    last_snapshot,
    list_positions,
    list_snapshots,
    list_trades,
    list_watchlist,
    prune_snapshots,
    recent_chat_messages,
    remove_watchlist,
    update_profile,
    upsert_position,
)


@pytest.fixture
def conn(db_path):
    with get_conn() as c:
        yield c


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat()


# --- profile ---------------------------------------------------------------------------------


def test_update_profile_rounds_cash_to_cents(conn):
    update_profile(conn, cash_balance=1234.5678)
    assert get_profile(conn)["cash_balance"] == 1234.57


def test_update_profile_partial_updates(conn):
    update_profile(conn, cash_balance=500.0)
    update_profile(conn, realized_pnl=12.34)
    profile = get_profile(conn)
    assert profile["cash_balance"] == 500.0
    assert profile["realized_pnl"] == 12.34
    update_profile(conn)  # no-op
    assert get_profile(conn)["cash_balance"] == 500.0


def test_no_cash_drift_over_many_cycles(conn):
    cash = 10000.0
    for _ in range(1000):
        update_profile(conn, cash_balance=cash - 0.1)
        cash = get_profile(conn)["cash_balance"]
        update_profile(conn, cash_balance=cash + 0.1)
        cash = get_profile(conn)["cash_balance"]
    assert cash == 10000.0


# --- watchlist -------------------------------------------------------------------------------


def test_watchlist_add_remove_and_uniqueness(conn):
    assert add_watchlist(conn, "PYPL") is True
    assert add_watchlist(conn, "PYPL") is False
    assert add_watchlist(conn, "AAPL") is False  # seeded
    assert [w["ticker"] for w in list_watchlist(conn)].count("PYPL") == 1
    assert remove_watchlist(conn, "PYPL") is True
    assert remove_watchlist(conn, "PYPL") is False


def test_watchlist_oldest_first(conn):
    add_watchlist(conn, "AAA")
    add_watchlist(conn, "BBB")
    tickers = [w["ticker"] for w in list_watchlist(conn)]
    assert tickers[-2:] == ["AAA", "BBB"]
    assert set(list_watchlist(conn)[0]) == {"ticker", "added_at"}


def test_watchlist_unique_constraint_enforced_by_schema(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO watchlist (id, user_id, ticker, added_at) "
            "VALUES ('x', 'default', 'AAPL', 'now')"
        )


# --- positions -------------------------------------------------------------------------------


def test_position_upsert_get_delete(conn):
    assert get_position(conn, "AAPL") is None
    upsert_position(conn, "AAPL", 10, 190.0)
    pos = get_position(conn, "AAPL")
    assert pos["quantity"] == 10
    assert pos["avg_cost"] == 190.0
    assert pos["updated_at"].endswith("+00:00")

    upsert_position(conn, "AAPL", 15.5, 191.25)
    pos = get_position(conn, "AAPL")
    assert (pos["quantity"], pos["avg_cost"]) == (15.5, 191.25)
    assert len(list_positions(conn)) == 1  # upsert, not a duplicate row

    delete_position(conn, "AAPL")
    assert get_position(conn, "AAPL") is None
    delete_position(conn, "AAPL")  # deleting a missing row is a no-op


def test_list_positions_sorted_by_ticker(conn):
    upsert_position(conn, "TSLA", 1, 1)
    upsert_position(conn, "AAPL", 1, 1)
    assert [p["ticker"] for p in list_positions(conn)] == ["AAPL", "TSLA"]
    assert set(list_positions(conn)[0]) == {"ticker", "quantity", "avg_cost", "updated_at"}


# --- trades ----------------------------------------------------------------------------------


def test_insert_trade_returns_stored_row_and_lists_newest_first(conn):
    t1 = insert_trade(conn, "AAPL", "buy", 10, 190.0)
    t2 = insert_trade(conn, "AAPL", "sell", 4, 200.0)
    assert t1["ticker"] == "AAPL" and t1["side"] == "buy"
    assert t1["quantity"] == 10 and t1["price"] == 190.0
    assert t1["id"] and t1["executed_at"].endswith("+00:00")
    trades = list_trades(conn)
    assert [t["id"] for t in trades] == [t2["id"], t1["id"]]
    assert list_trades(conn, limit=1)[0]["id"] == t2["id"]


def test_insert_trade_rejects_bad_side(conn):
    with pytest.raises(sqlite3.IntegrityError):
        insert_trade(conn, "AAPL", "hold", 1, 1.0)


# --- snapshots -------------------------------------------------------------------------------


def _seed_snapshots(conn, n, *, start=None, step=timedelta(minutes=1)):
    start = start or datetime.now(UTC) - step * n
    for i in range(n):
        insert_snapshot(conn, 10000.0 + i, _iso(start + step * i))


def test_snapshot_insert_and_last(conn):
    assert last_snapshot(conn) is None
    insert_snapshot(conn, 10000.0)
    insert_snapshot(conn, 10050.0)
    assert last_snapshot(conn)["total_value"] == 10050.0
    assert set(last_snapshot(conn)) == {"total_value", "recorded_at"}


def test_last_snapshot_uses_recorded_at_not_insert_order(conn):
    now = datetime.now(UTC)
    insert_snapshot(conn, 2.0, _iso(now))
    insert_snapshot(conn, 1.0, _iso(now - timedelta(hours=1)))
    assert last_snapshot(conn)["total_value"] == 2.0


def test_list_snapshots_small_series_is_returned_whole_oldest_first(conn):
    _seed_snapshots(conn, 50)
    rows = list_snapshots(conn)
    assert len(rows) == 50
    assert [r["total_value"] for r in rows] == [10000.0 + i for i in range(50)]


def test_list_snapshots_downsamples_keeping_first_and_last(conn):
    _seed_snapshots(conn, 1000)
    rows = list_snapshots(conn)
    assert 295 <= len(rows) <= 300
    assert rows[0]["total_value"] == 10000.0
    assert rows[-1]["total_value"] == 10999.0
    stamps = [r["recorded_at"] for r in rows]
    assert stamps == sorted(stamps)
    assert len(set(stamps)) == len(stamps)


def test_list_snapshots_exactly_at_limit_not_downsampled(conn):
    _seed_snapshots(conn, 300)
    assert len(list_snapshots(conn)) == 300


def test_list_snapshots_limit_returns_most_recent_oldest_first(conn):
    _seed_snapshots(conn, 20)
    rows = list_snapshots(conn, limit=5)
    assert [r["total_value"] for r in rows] == [10015.0, 10016.0, 10017.0, 10018.0, 10019.0]
    assert list_snapshots(conn, limit=0) == []


def test_list_snapshots_since_filters_inclusive_without_downsampling(conn):
    base = datetime.now(UTC) - timedelta(hours=10)
    _seed_snapshots(conn, 500, start=base)
    cutoff = base + timedelta(minutes=100)
    rows = list_snapshots(conn, since=_iso(cutoff))
    assert len(rows) == 400  # minutes 100..499 inclusive, all returned
    assert rows[0]["total_value"] == 10100.0


def test_list_snapshots_since_and_limit_combine(conn):
    base = datetime.now(UTC) - timedelta(hours=1)
    _seed_snapshots(conn, 30, start=base)
    rows = list_snapshots(conn, since=_iso(base + timedelta(minutes=10)), limit=3)
    assert [r["total_value"] for r in rows] == [10027.0, 10028.0, 10029.0]


def test_list_snapshots_since_accepts_z_suffix_and_naive(conn):
    ts = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    insert_snapshot(conn, 1.0, _iso(ts))
    assert len(list_snapshots(conn, since="2026-01-01T12:00:00Z")) == 1
    assert len(list_snapshots(conn, since="2026-01-01T12:00:00")) == 1
    assert len(list_snapshots(conn, since="2026-01-01T12:00:01Z")) == 0
    # non-UTC offset is converted, not string-compared
    assert len(list_snapshots(conn, since="2026-01-01T21:00:00+09:00")) == 1


def test_list_snapshots_since_invalid_raises_value_error(conn):
    with pytest.raises(ValueError):
        list_snapshots(conn, since="not-a-date")


def test_near_identical_timestamps_are_tolerated(conn):
    ts = _iso(datetime.now(UTC))
    insert_snapshot(conn, 1.0, ts)
    insert_snapshot(conn, 2.0, ts)
    assert [r["total_value"] for r in list_snapshots(conn)] == [1.0, 2.0]


def test_prune_snapshots_removes_only_old_rows(conn):
    now = datetime.now(UTC)
    insert_snapshot(conn, 1.0, _iso(now - timedelta(days=45)))
    insert_snapshot(conn, 2.0, _iso(now - timedelta(days=31)))
    insert_snapshot(conn, 3.0, _iso(now - timedelta(days=29)))
    insert_snapshot(conn, 4.0, _iso(now))
    assert prune_snapshots(conn) == 2
    assert [r["total_value"] for r in list_snapshots(conn)] == [3.0, 4.0]
    assert prune_snapshots(conn) == 0


def test_prune_snapshots_custom_days(conn):
    now = datetime.now(UTC)
    insert_snapshot(conn, 1.0, _iso(now - timedelta(days=3)))
    insert_snapshot(conn, 2.0, _iso(now))
    assert prune_snapshots(conn, older_than_days=2) == 1


# --- chat ------------------------------------------------------------------------------------


def test_chat_actions_round_trip(conn):
    actions = {
        "trades": [
            {"ticker": "AAPL", "side": "buy", "quantity": 10, "price": 190.12, "status": "executed"}
        ],
        "watchlist_changes": [{"ticker": "PYPL", "action": "add", "status": "executed"}],
        "errors": ["Insufficient cash for TSLA buy"],
    }
    stored = insert_chat_message(conn, "assistant", "Done — bought 10 AAPL.", actions)
    assert stored["actions"] == actions
    assert stored["id"]
    [msg] = recent_chat_messages(conn)
    assert msg["actions"] == actions
    assert msg["role"] == "assistant"
    assert msg["content"] == "Done — bought 10 AAPL."
    assert msg["created_at"].endswith("+00:00")


def test_chat_user_message_has_none_actions(conn):
    stored = insert_chat_message(conn, "user", "hello")
    assert stored["actions"] is None
    assert recent_chat_messages(conn)[0]["actions"] is None


def test_chat_empty_actions_dict_round_trips_as_dict(conn):
    insert_chat_message(conn, "assistant", "hi", {})
    assert recent_chat_messages(conn)[0]["actions"] == {}


def test_chat_recent_is_last_n_oldest_first(conn):
    for i in range(30):
        insert_chat_message(conn, "user" if i % 2 == 0 else "assistant", f"m{i}")
    msgs = recent_chat_messages(conn)
    assert [m["content"] for m in msgs] == [f"m{i}" for i in range(10, 30)]
    assert [m["content"] for m in recent_chat_messages(conn, limit=3)] == ["m27", "m28", "m29"]
    assert set(msgs[0]) == {"role", "content", "actions", "created_at"}


def test_chat_rejects_bad_role(conn):
    with pytest.raises(sqlite3.IntegrityError):
        insert_chat_message(conn, "system", "nope")


def test_chat_content_survives_unicode_and_quotes(conn):
    text = 'He said "buy" — ünïcode 📈 \'quoted\''
    insert_chat_message(conn, "user", text, {"errors": [text]})
    msg = recent_chat_messages(conn)[0]
    assert msg["content"] == text
    assert msg["actions"] == {"errors": [text]}
