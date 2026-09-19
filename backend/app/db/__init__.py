"""Database layer (sync sqlite3). See planning/TEAM_CONTRACTS.md for the API contract."""

from .connection import check_db, get_conn, get_db_path, init_db
from .queries import (
    add_watchlist,
    delete_position,
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
from .seed import DEFAULT_TICKERS, DEFAULT_USER

__all__ = [
    "DEFAULT_TICKERS",
    "DEFAULT_USER",
    "add_watchlist",
    "check_db",
    "delete_position",
    "get_conn",
    "get_db_path",
    "get_position",
    "get_profile",
    "init_db",
    "insert_chat_message",
    "insert_snapshot",
    "insert_trade",
    "last_snapshot",
    "list_positions",
    "list_snapshots",
    "list_trades",
    "list_watchlist",
    "prune_snapshots",
    "recent_chat_messages",
    "remove_watchlist",
    "update_profile",
    "upsert_position",
]
