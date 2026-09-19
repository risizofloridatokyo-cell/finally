"""Background task loops."""

from __future__ import annotations

import asyncio

from app import tasks
from app.portfolio import service


async def test_snapshot_loop_calls_snapshotter_repeatedly(env, monkeypatch):
    calls: list[int] = []
    monkeypatch.setattr(service, "snapshot_portfolio", lambda: calls.append(1))

    task = asyncio.create_task(tasks.snapshot_loop(interval=0.01))
    await asyncio.sleep(0.15)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)

    assert len(calls) >= 2


async def test_snapshot_loop_survives_a_failing_snapshot(env, monkeypatch):
    calls: list[int] = []

    def flaky():
        calls.append(1)
        raise RuntimeError("transient")

    monkeypatch.setattr(service, "snapshot_portfolio", flaky)
    task = asyncio.create_task(tasks.snapshot_loop(interval=0.01))
    await asyncio.sleep(0.1)
    assert not task.done()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert len(calls) >= 2


async def test_retention_loop_prunes_on_startup(env, monkeypatch):
    pruned = asyncio.Event()

    def fake_prune() -> int:
        pruned.set()
        return 0

    monkeypatch.setattr(tasks, "prune_old_snapshots", fake_prune)
    task = asyncio.create_task(tasks.retention_loop(interval=3600))
    await asyncio.wait_for(pruned.wait(), timeout=2)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
