"""Watchlist endpoints: `/api/watchlist`."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.watchlist import service

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


class WatchlistAdd(BaseModel):
    ticker: str


def _normalize(raw: str) -> str:
    try:
        return service.normalize_ticker(raw)
    except service.InvalidTicker:
        raise HTTPException(status_code=400, detail="Invalid ticker symbol") from None


@router.get("")
def get_watchlist() -> list[dict]:
    return service.list_watchlist()


@router.post("")
async def add_to_watchlist(req: WatchlistAdd) -> dict:
    """Add a ticker. Idempotent: re-adding an existing ticker also returns 200."""
    ticker = _normalize(req.ticker)
    created = await service.add_ticker(ticker)
    entry = next((e for e in service.list_watchlist() if e["ticker"] == ticker), None)
    return {**(entry or {"ticker": ticker, "added_at": None, "price": None}), "created": created}


@router.delete("/{ticker}")
async def remove_from_watchlist(ticker: str) -> dict:
    symbol = _normalize(ticker)
    if not await service.remove_ticker(symbol):
        raise HTTPException(status_code=404, detail=f"{symbol} is not on the watchlist")
    return {"ticker": symbol, "removed": True}
