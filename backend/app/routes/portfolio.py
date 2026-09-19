"""Portfolio endpoints: `/api/portfolio`, `/api/portfolio/trade`, `/api/portfolio/history`."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app import db
from app.portfolio import service

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


class TradeRequest(BaseModel):
    ticker: str
    quantity: float
    side: str


def _parse_since(raw: str) -> str:
    """Parse an ISO-8601 `since` into a UTC ISO string (naive input is taken as UTC)."""
    text = raw.strip()
    # A literal '+' in a query string decodes to a space; restore the UTC offset sign.
    text = re.sub(r"(T[\d:.]+) (\d{2}:\d{2})$", r"\1+\2", text)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid 'since' timestamp") from None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat()


@router.get("")
def get_portfolio() -> dict:
    return service.get_portfolio()


@router.post("/trade")
def post_trade(req: TradeRequest) -> dict:
    try:
        return service.execute_trade(req.ticker, req.side, req.quantity)
    except service.TradeError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from None


@router.get("/history")
def get_history(
    since: str | None = Query(None),
    limit: int | None = Query(None, gt=0),
) -> list[dict]:
    since_iso = _parse_since(since) if since is not None else None
    with db.get_conn() as conn:
        return db.list_snapshots(conn, since=since_iso, limit=limit)
