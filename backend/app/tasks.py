"""Background tasks: portfolio snapshotter and snapshot retention."""

from __future__ import annotations

import asyncio
import logging

from app import db
from app.config import RETENTION_DAYS, RETENTION_INTERVAL_SECONDS, SNAPSHOT_INTERVAL_SECONDS
from app.portfolio import service as portfolio_service

logger = logging.getLogger(__name__)


def prune_old_snapshots() -> int:
    with db.get_conn() as conn:
        return db.prune_snapshots(conn, older_than_days=RETENTION_DAYS)


async def snapshot_loop(interval: float = SNAPSHOT_INTERVAL_SECONDS) -> None:
    """Snapshot total portfolio value every `interval`s (skipped when it barely moved)."""
    while True:
        await asyncio.sleep(interval)
        try:
            await asyncio.to_thread(portfolio_service.snapshot_portfolio)
        except Exception:
            logger.exception("Portfolio snapshot failed")


async def retention_loop(interval: float = RETENTION_INTERVAL_SECONDS) -> None:
    """Delete old snapshots on startup and then once per `interval`."""
    while True:
        try:
            deleted = await asyncio.to_thread(prune_old_snapshots)
            if deleted:
                logger.info("Pruned %d old portfolio snapshots", deleted)
        except Exception:
            logger.exception("Snapshot retention prune failed")
        await asyncio.sleep(interval)
