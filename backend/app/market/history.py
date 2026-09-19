"""REST endpoint for historical price data (sparkline / detail-chart backfill)."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from fastapi import APIRouter, HTTPException, Query

from .cache import HISTORY_MAXLEN, PriceCache

router = APIRouter(prefix="/api", tags=["market-data"])


def create_history_router(
    price_cache: PriceCache,
    get_tracked_tickers: Callable[[], Iterable[str]],
) -> APIRouter:
    """Create the /api/history router.

    `get_tracked_tickers` (typically `MarketDataSource.get_tickers`) is used
    to distinguish an unknown ticker (404) from a tracked-but-not-yet-warmed
    one (200 with an empty points list).
    """

    @router.get("/history")
    async def get_history(
        ticker: str = Query(...),
        limit: int = Query(HISTORY_MAXLEN, gt=0),
    ) -> dict:
        return _build_history_response(ticker, limit, price_cache, get_tracked_tickers)

    return router


def _build_history_response(
    ticker: str,
    limit: int,
    price_cache: PriceCache,
    get_tracked_tickers: Callable[[], Iterable[str]],
) -> dict:
    """Build the /api/history response body, or raise 404 for an unknown ticker."""
    ticker = ticker.upper().strip()
    if ticker not in set(get_tracked_tickers()):
        raise HTTPException(status_code=404, detail=f"Unknown ticker: {ticker}")

    points = price_cache.get_history(ticker, limit=limit)
    return {"ticker": ticker, "points": points}
