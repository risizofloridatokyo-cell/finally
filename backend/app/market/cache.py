"""Thread-safe in-memory price cache."""

from __future__ import annotations

import time
from collections import deque
from threading import Lock

from .models import PriceUpdate

# Ring buffer size per ticker: ~300 points ≈ 2.5 minutes at 500ms ticks.
HISTORY_MAXLEN = 300


class PriceCache:
    """Thread-safe in-memory cache of the latest price for each ticker.

    Writers: SimulatorDataSource or MassiveDataSource (one at a time).
    Readers: SSE streaming endpoint, portfolio valuation, trade execution,
    the /api/history endpoint.
    """

    def __init__(self) -> None:
        self._prices: dict[str, PriceUpdate] = {}
        self._history: dict[str, deque[dict[str, float]]] = {}
        self._lock = Lock()
        self._version: int = 0  # Monotonically increasing; bumped on every update

    def update(self, ticker: str, price: float, timestamp: float | None = None) -> PriceUpdate:
        """Record a new price for a ticker. Returns the created PriceUpdate.

        Automatically computes direction and change from the previous price.
        If this is the first update for the ticker, previous_price == price (direction='flat').
        Also appends the point to the ticker's bounded history ring buffer.
        """
        with self._lock:
            ts = timestamp or time.time()
            prev = self._prices.get(ticker)
            previous_price = prev.price if prev else price

            update = PriceUpdate(
                ticker=ticker,
                price=round(price, 2),
                previous_price=round(previous_price, 2),
                timestamp=ts,
            )
            self._prices[ticker] = update
            self._history.setdefault(ticker, deque(maxlen=HISTORY_MAXLEN)).append(
                {"price": update.price, "timestamp": update.timestamp}
            )
            self._version += 1
            return update

    def get_history(self, ticker: str, limit: int | None = None) -> list[dict[str, float]]:
        """Recent price points for a ticker, oldest-first.

        Returns an empty list if the ticker has no recorded points yet.
        `limit` caps the number of most-recent points returned; it is
        naturally capped at the ring buffer size (HISTORY_MAXLEN).
        """
        with self._lock:
            buffer = self._history.get(ticker)
            points = list(buffer) if buffer else []
        if limit is not None:
            points = points[-limit:]
        return points

    def get(self, ticker: str) -> PriceUpdate | None:
        """Get the latest price for a single ticker, or None if unknown."""
        with self._lock:
            return self._prices.get(ticker)

    def get_all(self) -> dict[str, PriceUpdate]:
        """Snapshot of all current prices. Returns a shallow copy."""
        with self._lock:
            return dict(self._prices)

    def get_price(self, ticker: str) -> float | None:
        """Convenience: get just the price float, or None."""
        update = self.get(ticker)
        return update.price if update else None

    def remove(self, ticker: str) -> None:
        """Remove a ticker from the cache (e.g., when removed from watchlist)."""
        with self._lock:
            self._prices.pop(ticker, None)
            self._history.pop(ticker, None)

    @property
    def version(self) -> int:
        """Current version counter. Useful for SSE change detection."""
        return self._version

    def __len__(self) -> int:
        with self._lock:
            return len(self._prices)

    def __contains__(self, ticker: str) -> bool:
        with self._lock:
            return ticker in self._prices
