"""Tests for the SSE streaming generator, including the keepalive comment."""

import pytest

from app.market.cache import PriceCache
from app.market.stream import _generate_events


class FakeClient:
    host = "testclient"


class FakeRequest:
    """Minimal stand-in for fastapi.Request that disconnects after N checks."""

    def __init__(self, disconnect_after: int):
        self.client = FakeClient()
        self._checks = 0
        self._disconnect_after = disconnect_after

    async def is_disconnected(self) -> bool:
        self._checks += 1
        return self._checks > self._disconnect_after


@pytest.mark.asyncio
class TestGenerateEvents:
    """Unit tests for _generate_events."""

    async def test_yields_retry_directive_first(self):
        cache = PriceCache()
        request = FakeRequest(disconnect_after=0)
        events = [event async for event in _generate_events(cache, request, interval=0.01)]
        assert events[0] == "retry: 1000\n\n"

    async def test_sends_snapshot_on_first_change(self):
        cache = PriceCache()
        cache.update("AAPL", 190.00)
        request = FakeRequest(disconnect_after=1)
        events = [event async for event in _generate_events(cache, request, interval=0.01)]

        data_events = [e for e in events if e.startswith("data:")]
        assert len(data_events) == 1
        assert "AAPL" in data_events[0]

    async def test_no_new_event_when_nothing_changes(self):
        cache = PriceCache()
        cache.update("AAPL", 190.00)
        request = FakeRequest(disconnect_after=5)
        events = [
            event
            async for event in _generate_events(
                cache, request, interval=0.01, keepalive_interval=100.0
            )
        ]

        data_events = [e for e in events if e.startswith("data:")]
        assert len(data_events) == 1  # Just the initial snapshot
        assert not any(e == ": keepalive\n\n" for e in events)

    async def test_keepalive_sent_when_idle(self):
        cache = PriceCache()
        cache.update("AAPL", 190.00)
        request = FakeRequest(disconnect_after=20)
        events = [
            event
            async for event in _generate_events(
                cache, request, interval=0.01, keepalive_interval=0.03
            )
        ]

        keepalives = [e for e in events if e == ": keepalive\n\n"]
        assert len(keepalives) >= 1

    async def test_no_event_when_cache_empty(self):
        """An empty cache never has a change, so no data events are sent."""
        cache = PriceCache()
        request = FakeRequest(disconnect_after=3)
        events = [
            event
            async for event in _generate_events(
                cache, request, interval=0.01, keepalive_interval=100.0
            )
        ]
        assert not any(e.startswith("data:") for e in events)
