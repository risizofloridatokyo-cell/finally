"""Deterministic market-data stand-in for portfolio / API tests (no background task)."""

from __future__ import annotations

from app.market import MarketDataSource, PriceCache

DEFAULT_PRICES = {
    "AAPL": 100.0,
    "GOOGL": 200.0,
    "MSFT": 300.0,
    "AMZN": 150.0,
    "TSLA": 250.0,
    "NVDA": 500.0,
    "META": 400.0,
    "JPM": 120.0,
    "V": 260.0,
    "NFLX": 600.0,
}


class StubSource(MarketDataSource):
    """Seeds fixed prices into the cache and never moves them on its own.

    `warm=False` tracks tickers without writing a price (the "not warmed" state).
    """

    def __init__(
        self, cache: PriceCache, prices: dict[str, float] | None = None, warm: bool = True
    ) -> None:
        self._cache = cache
        self._prices = dict(DEFAULT_PRICES if prices is None else prices)
        self._warm = warm
        self._tickers: list[str] = []
        self._running = False

    def _seed(self, ticker: str) -> None:
        if self._warm:
            self._cache.update(ticker, self._prices.get(ticker, 50.0))

    def prime(self, tickers: list[str]) -> None:
        """Synchronous start, for tests that do not run an event loop."""
        self._tickers = list(tickers)
        for ticker in self._tickers:
            self._seed(ticker)
        self._running = True

    async def start(self, tickers: list[str]) -> None:
        self.prime(tickers)

    async def stop(self) -> None:
        self._running = False

    async def add_ticker(self, ticker: str) -> None:
        if ticker not in self._tickers:
            self._tickers.append(ticker)
            self._seed(ticker)

    async def remove_ticker(self, ticker: str) -> None:
        if ticker in self._tickers:
            self._tickers.remove(ticker)
        self._cache.remove(ticker)

    def get_tickers(self) -> list[str]:
        return list(self._tickers)

    def is_running(self) -> bool:
        return self._running
