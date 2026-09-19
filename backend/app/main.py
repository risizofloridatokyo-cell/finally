"""FastAPI application: `uvicorn app.main:app`."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.staticfiles import StaticFiles

from app import db, state, tasks
from app.config import get_static_dir
from app.market import (
    MarketDataSource,
    PriceCache,
    create_history_router,
    create_market_data_source,
    create_stream_router,
)
from app.portfolio import service as portfolio_service
from app.routes import health, portfolio, watchlist

logger = logging.getLogger(__name__)


def _load_chat_router() -> APIRouter | None:
    """Import the chat router from `app.llm`, tolerating its absence."""
    try:
        from app.llm import router as chat_router
    except ImportError as exc:
        if getattr(exc, "name", None) != "app.llm":
            raise  # a real import failure inside app.llm - do not hide it
        logger.warning("app.llm chat router not available; /api/chat disabled")
        return None
    return chat_router


def create_app(
    *,
    cache: PriceCache | None = None,
    source: MarketDataSource | None = None,
    start_background_tasks: bool = True,
) -> FastAPI:
    """Build the app. Arguments exist so tests can inject a cache / market source."""
    # Explicit None checks: an empty PriceCache is falsy (it defines __len__).
    price_cache = cache if cache is not None else PriceCache()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # 1. init DB (idempotent: creates tables and seeds only if missing)
        db.init_db()

        # 2. current watchlist and positions - never the hardcoded default 10
        with db.get_conn() as conn:
            watched = [w["ticker"] for w in db.list_watchlist(conn)]
            held = [p["ticker"] for p in db.list_positions(conn)]
        tickers = list(dict.fromkeys(watched + held))

        # 3. market data on the union of watchlist and position tickers
        market = source if source is not None else create_market_data_source(price_cache)
        await market.start(tickers)
        state.set_runtime(price_cache, market, asyncio.get_running_loop())

        # 4. background tasks
        background: list[asyncio.Task] = []
        if start_background_tasks:
            try:
                await asyncio.to_thread(portfolio_service.snapshot_portfolio)
            except Exception:
                logger.exception("Initial portfolio snapshot failed")
            background = [
                asyncio.create_task(tasks.snapshot_loop(), name="portfolio-snapshotter"),
                asyncio.create_task(tasks.retention_loop(), name="snapshot-retention"),
            ]

        try:
            yield
        finally:
            for task in background:
                task.cancel()
            await asyncio.gather(*background, return_exceptions=True)
            await market.stop()
            state.set_runtime(None, None)

    app = FastAPI(title="FinAlly", lifespan=lifespan)

    app.include_router(health.router)
    app.include_router(portfolio.router)
    app.include_router(watchlist.router)
    app.include_router(create_stream_router(price_cache))
    app.include_router(create_history_router(price_cache, lambda: state.get_source().get_tickers()))
    chat_router = _load_chat_router()
    if chat_router is not None:
        app.include_router(chat_router)

    # Static frontend last, so it never shadows an /api route.
    static_dir = get_static_dir()
    if static_dir is not None:
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
    else:
        logger.info("No static frontend directory found; serving API only")

    return app


app = create_app()
