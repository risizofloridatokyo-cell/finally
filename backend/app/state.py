"""Runtime singletons (price cache, market data source), set by the app lifespan."""

from __future__ import annotations

import asyncio

from .market import MarketDataSource, PriceCache

_cache: PriceCache | None = None
_source: MarketDataSource | None = None
_loop: asyncio.AbstractEventLoop | None = None


def set_runtime(
    cache: PriceCache | None,
    source: MarketDataSource | None,
    loop: asyncio.AbstractEventLoop | None = None,
) -> None:
    """Install (or clear, with None) the process-wide cache, market source and event loop.

    The loop lets synchronous service code running in a worker thread call the source's
    async API (see `portfolio.service`).
    """
    global _cache, _source, _loop
    _cache = cache
    _source = source
    _loop = loop


def get_cache() -> PriceCache:
    if _cache is None:
        raise RuntimeError("Price cache is not initialised (app not started)")
    return _cache


def get_source() -> MarketDataSource:
    if _source is None:
        raise RuntimeError("Market data source is not initialised (app not started)")
    return _source


def get_loop() -> asyncio.AbstractEventLoop | None:
    return _loop
