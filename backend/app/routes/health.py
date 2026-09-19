"""`GET /api/health`."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app import db, state

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
def health() -> JSONResponse:
    """200 when the DB is reachable and the market-data task is running, else 503."""
    if not db.check_db():
        return JSONResponse(
            status_code=503, content={"status": "degraded", "detail": "database unreachable"}
        )
    try:
        running = state.get_source().is_running()
    except RuntimeError:
        running = False
    if not running:
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "detail": "market data task is not running"},
        )
    return JSONResponse(status_code=200, content={"status": "ok"})
