# Market Data Interface Design

Unified Python interface for market data in FinAlly. Two implementations — the GBM simulator (`MARKET_SIMULATOR.md`) and the Massive API client (`MASSIVE_API.md`) — sit behind one abstract interface, so all downstream code (SSE streaming, `GET /api/history`, portfolio valuation, trade execution) is source-agnostic.

**Status**: The core of this design (`PriceUpdate`, `MarketDataSource`, `PriceCache`, `factory`, both data sources, the SSE router) is already implemented in `backend/app/market/` and documented as built in `MARKET_DATA_SUMMARY.md`. This document describes that implementation as the contract downstream code should rely on, and specifies the two pieces `PLAN.md` calls out as outstanding deltas: the price-history ring buffer (`GET /api/history`) and the SSE keepalive comment. It also folds in one correction to `massive_client.py` identified during Massive API research (see `MASSIVE_API.md` §8).

## 1. Design Principles

- **Strategy pattern.** `SimulatorDataSource` and `MassiveDataSource` implement the same `MarketDataSource` ABC. Nothing outside `app/market/` imports either concrete class directly — everything goes through `create_market_data_source()`.
- **Cache as the single point of truth.** Data sources are *producers*: they push into a shared `PriceCache` on their own schedule (500ms simulator tick, 2–15s Massive poll). Consumers (SSE, portfolio valuation, chat context, `GET /api/history`) only ever *read* the cache — they never call a data source directly for a price.
- **One data model leaves the layer.** `PriceUpdate` is the only shape that crosses the boundary out of `app/market/`. Both sources normalize their very different raw payloads (GBM float vs. Massive `TickerSnapshot`) into the same `PriceUpdate` before it reaches the cache.
- **Unix seconds everywhere, in-layer.** Both sources convert their native timestamp units to Unix seconds (float) before calling `cache.update()`. `MASSIVE_API.md` §7 documents the two different native units (ms for aggregates, ns for trade/quote `sip_timestamp`) that must be normalized on the way in.
- **"Not warmed" is a first-class state, not an error.** Every consumer has a defined fallback for a ticker with no price yet (`PLAN.md` §6). The interface makes this natural: `cache.get(ticker)` returns `None` until the first successful update.

## 2. Core Data Model

```python
# app/market/models.py  (implemented)

from __future__ import annotations
import time
from dataclasses import dataclass, field

@dataclass(frozen=True, slots=True)
class PriceUpdate:
    """Immutable snapshot of a single ticker's price at a point in time."""

    ticker: str
    price: float
    previous_price: float
    timestamp: float = field(default_factory=time.time)  # Unix seconds

    @property
    def change(self) -> float:
        return round(self.price - self.previous_price, 4)

    @property
    def change_percent(self) -> float:
        if self.previous_price == 0:
            return 0.0
        return round((self.price - self.previous_price) / self.previous_price * 100, 4)

    @property
    def direction(self) -> str:
        if self.price > self.previous_price:
            return "up"
        if self.price < self.previous_price:
            return "down"
        return "flat"

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "price": self.price,
            "previous_price": self.previous_price,
            "timestamp": self.timestamp,
            "change": self.change,
            "change_percent": self.change_percent,
            "direction": self.direction,
        }
```

`change`/`change_percent`/`direction` are **computed properties**, not stored fields — `previous_price` (the tick-to-tick prior price, captured by the cache at write time) is the only stored derived value. This keeps `PriceUpdate` trivially correct: there's no way for `direction` to disagree with `price`/`previous_price`.

## 3. Abstract Interface

```python
# app/market/interface.py  (implemented)

from abc import ABC, abstractmethod

class MarketDataSource(ABC):
    """Contract for market data providers.

    Implementations push price updates into a shared PriceCache on their own
    schedule. Downstream code never calls the data source directly for prices —
    it reads from the cache.
    """

    @abstractmethod
    async def start(self, tickers: list[str]) -> None:
        """Begin producing price updates for the given tickers. Call exactly once."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop the background task. Safe to call multiple times."""

    @abstractmethod
    async def add_ticker(self, ticker: str) -> None:
        """Add a ticker to the active set. No-op if already present."""

    @abstractmethod
    async def remove_ticker(self, ticker: str) -> None:
        """Remove a ticker from the active set. Also evicts it from the PriceCache."""

    @abstractmethod
    def get_tickers(self) -> list[str]:
        """Return the currently tracked tickers."""
```

Lifecycle:
```python
source = create_market_data_source(cache)
await source.start(["AAPL", "GOOGL", ...])   # watchlist ∪ position tickers, see §8
...
await source.add_ticker("TSLA")
await source.remove_ticker("GOOGL")
...
await source.stop()
```

## 4. Price Cache

Thread-safe (the simulator's asyncio task and any sync code calling in from a thread pool both touch it), single shared instance per process.

```python
# app/market/cache.py  (implemented)

import time
from threading import Lock
from .models import PriceUpdate

class PriceCache:
    def __init__(self) -> None:
        self._prices: dict[str, PriceUpdate] = {}
        self._lock = Lock()
        self._version: int = 0  # bumped on every update; SSE change detection

    def update(self, ticker: str, price: float, timestamp: float | None = None) -> PriceUpdate:
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
            self._version += 1
            return update

    def get(self, ticker: str) -> PriceUpdate | None: ...
    def get_all(self) -> dict[str, PriceUpdate]: ...
    def get_price(self, ticker: str) -> float | None: ...
    def remove(self, ticker: str) -> None: ...

    @property
    def version(self) -> int: ...  # monotonic counter for push-on-change SSE
```

The `version` counter is what lets the SSE endpoint push only when something actually changed (`PLAN.md` §6) instead of polling the whole cache into JSON every 500ms regardless.

## 5. History Ring Buffer — `GET /api/history` (delta, not yet implemented)

`PLAN.md` §6/§8/§10 calls for a bounded in-memory history of recent prices per ticker, so sparklines and the detail chart can backfill on load instead of starting empty and waiting for SSE ticks to accumulate. This slots into the cache layer alongside the latest-price map.

### Design

Extend `PriceCache` with a bounded ring buffer per ticker, filled from the exact same `update()` call that maintains the latest-price map — one write path, two read paths.

```python
# app/market/cache.py  (addition)

from collections import deque

class PriceCache:
    HISTORY_CAPACITY = 300  # ~2.5 min at 500ms ticks; also the default GET /api/history limit

    def __init__(self) -> None:
        self._prices: dict[str, PriceUpdate] = {}
        self._history: dict[str, deque[tuple[float, float]]] = {}  # ticker -> deque[(price, ts)]
        self._lock = Lock()
        self._version: int = 0

    def update(self, ticker: str, price: float, timestamp: float | None = None) -> PriceUpdate:
        with self._lock:
            ts = timestamp or time.time()
            ...  # as above
            self._prices[ticker] = update
            buf = self._history.setdefault(ticker, deque(maxlen=self.HISTORY_CAPACITY))
            buf.append((update.price, ts))
            self._version += 1
            return update

    def get_history(self, ticker: str, limit: int | None = None) -> list[dict] | None:
        """Oldest-first points for a ticker, or None if the ticker has never been tracked.

        Returns an EMPTY list (not None) for a tracked-but-not-yet-warmed ticker —
        the caller distinguishes "never seen this ticker" (404) from "seen it,
        no prices yet" (empty backfill, SSE will fill it in).
        """
        with self._lock:
            buf = self._history.get(ticker)
            if buf is None:
                return None
            points = list(buf)
            if limit is not None:
                points = points[-limit:]
            return [{"price": p, "timestamp": t} for p, t in points]

    def remove(self, ticker: str) -> None:
        with self._lock:
            self._prices.pop(ticker, None)
            self._history.pop(ticker, None)
```

Notes:
- `deque(maxlen=N)` gives O(1) bounded-size append with automatic eviction of the oldest point — no manual trimming, no unbounded growth in a long-lived process (this was flagged as a real risk in `PLAN.md` §13.B).
- A ticker only gets a `_history` entry once `update()` has been called for it at least once — i.e. once `add_ticker`/`start` has seeded it. `get_history()` returning `None` vs `[]` is what lets the route below tell "unknown ticker" (`404`) apart from "known ticker, zero points so far" (`200` with an empty list).
- `_history` entries must be created/removed in lockstep with `_prices` — `remove()` pops both, so a de-registered ticker doesn't leak a stale buffer.

### Route

```python
# app/market/history.py or the watchlist/market route module

from fastapi import APIRouter, HTTPException, Query

def create_history_router(price_cache: PriceCache) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["market"])

    @router.get("/history")
    async def get_history(
        ticker: str,
        limit: int = Query(default=300, le=PriceCache.HISTORY_CAPACITY, gt=0),
    ):
        points = price_cache.get_history(ticker.upper(), limit=limit)
        if points is None:
            raise HTTPException(status_code=404, detail=f"Ticker '{ticker}' is not tracked")
        return {"ticker": ticker.upper(), "points": points}

    return router
```

Matches `PLAN.md` §8: `GET /api/history?ticker=SYM&limit=N`, default 300, capped at buffer size, oldest-first, `404` for an untracked ticker.

## 6. Factory

```python
# app/market/factory.py  (implemented)

import os

def create_market_data_source(price_cache: PriceCache) -> MarketDataSource:
    """MASSIVE_API_KEY set and non-empty -> MassiveDataSource. Otherwise -> SimulatorDataSource.

    Returns an unstarted source. Caller must await source.start(tickers).
    """
    api_key = os.environ.get("MASSIVE_API_KEY", "").strip()
    if api_key:
        return MassiveDataSource(api_key=api_key, price_cache=price_cache)
    return SimulatorDataSource(price_cache=price_cache)
```

This one `if` statement is the entire seam between "demo mode" and "real data mode" — nothing else in the app branches on `MASSIVE_API_KEY`.

## 7. Massive Implementation (summary — full detail in `MASSIVE_API.md`)

```python
# app/market/massive_client.py  (implemented; one bug to fix per MASSIVE_API.md §8)

class MassiveDataSource(MarketDataSource):
    def __init__(self, api_key: str, price_cache: PriceCache, poll_interval: float = 15.0):
        self._client = RESTClient(api_key=api_key)
        self._cache = price_cache
        self._interval = poll_interval
        self._tickers: list[str] = []
        self._task: asyncio.Task | None = None

    async def start(self, tickers: list[str]) -> None:
        self._tickers = list(tickers)
        await self._poll_once()  # immediate first poll so the cache isn't empty
        self._task = asyncio.create_task(self._poll_loop())

    async def _poll_once(self) -> None:
        if not self._tickers:
            return
        snapshots = await asyncio.to_thread(
            self._client.get_snapshot_all, "stocks", self._tickers,
        )
        for snap in snapshots:
            if snap.last_trade is None or snap.last_trade.price is None:
                continue  # present in response but no trade yet -> stays "not warmed"
            self._cache.update(
                ticker=snap.ticker,
                price=snap.last_trade.price,
                # sip_timestamp is NANOSECONDS -- see MASSIVE_API.md §7-8
                timestamp=(snap.last_trade.sip_timestamp or 0) / 1_000_000_000,
            )
```

Key contract: **one API call per poll cycle, for the full ticker set**, via `get_snapshot_all`. A ticker absent from the response, or present with no `last_trade`, is left alone in the cache for that cycle — it never gets a synthetic/default price. If it was never warmed at all, every consumer's "not warmed" fallback applies (`PLAN.md` §6): `null` price in `GET /api/watchlist`, excluded from `total_value`, "price unavailable" in chat context, `—` in the UI.

`add_ticker`/`remove_ticker` just mutate `self._tickers`; the next poll cycle picks up additions, and `remove_ticker` also evicts the ticker (and its history buffer) from the cache immediately rather than waiting for a poll.

## 8. Simulator Implementation (summary — full detail in `MARKET_SIMULATOR.md`)

```python
# app/market/simulator.py  (implemented)

class SimulatorDataSource(MarketDataSource):
    def __init__(self, price_cache: PriceCache, update_interval: float = 0.5, event_probability: float = 0.001):
        self._cache = price_cache
        self._interval = update_interval
        self._sim: GBMSimulator | None = None
        self._task: asyncio.Task | None = None

    async def start(self, tickers: list[str]) -> None:
        self._sim = GBMSimulator(tickers=tickers, event_probability=self._event_prob)
        for ticker in tickers:
            price = self._sim.get_price(ticker)
            if price is not None:
                self._cache.update(ticker=ticker, price=price)  # seed immediately, no 500ms wait
        self._task = asyncio.create_task(self._run_loop())

    async def _run_loop(self) -> None:
        while True:
            for ticker, price in self._sim.step().items():
                self._cache.update(ticker=ticker, price=price)
            await asyncio.sleep(self._interval)
```

The simulator seeds the cache synchronously in `start()` (and in `add_ticker()`), so a brand-new ticker has a price immediately rather than waiting for the first 500ms tick — this matters for `GET /api/history` returning a non-empty buffer right after a ticker is added, and for the SSE connect-time snapshot below.

## 9. SSE Streaming

```python
# app/market/stream.py  (implemented; keepalive is the one delta)

async def _generate_events(price_cache: PriceCache, request: Request, interval: float = 0.5):
    yield "retry: 1000\n\n"
    last_version = -1
    last_keepalive = time.monotonic()

    while True:
        if await request.is_disconnected():
            break

        current_version = price_cache.version
        if current_version != last_version:
            last_version = current_version
            prices = price_cache.get_all()
            if prices:
                data = {ticker: update.to_dict() for ticker, update in prices.items()}
                yield f"data: {json.dumps(data)}\n\n"
                last_keepalive = time.monotonic()  # a real event also resets the keepalive clock
        elif time.monotonic() - last_keepalive >= 15.0:
            yield ": keepalive\n\n"              # NEW — comment line, ignored by EventSource
            last_keepalive = time.monotonic()

        await asyncio.sleep(interval)
```

`price_cache.version` already makes this push-on-change rather than push-every-tick — the only piece missing per `PLAN.md` §6 is the `~15s` keepalive comment (`: keepalive\n\n`) so a quiet stream (no price movement, or an inactive ticker with no market data) doesn't look indistinguishable from a stalled/dead connection. `EventSource` ignores comment lines (`:`-prefixed) entirely — they exist purely to keep the TCP connection visibly alive and let the frontend's connection dot distinguish "connected but quiet" from "stalled" (`PLAN.md` §10).

The connect-time behavior (immediate full snapshot, `retry: 1000` directive) is already correct and unchanged by this delta.

## 10. Startup Sequence

Per `PLAN.md` §6, on every boot (fresh DB or persisted volume):

```python
# app startup (FastAPI lifespan)

price_cache = PriceCache()
await init_db()  # 1. create tables + seed defaults only if missing

watchlist_tickers = await get_watchlist_tickers()      # 2. current DB state
position_tickers = await get_position_tickers()
initial_tickers = sorted(set(watchlist_tickers) | set(position_tickers))

source = create_market_data_source(price_cache)
await source.start(initial_tickers)                     # 3. union, never the hardcoded default 10

# 4. background tasks: portfolio snapshotter (60s), snapshot retention (daily)
```

This is why `MarketDataSource.start()` takes a ticker list rather than reading a hardcoded default internally — the union is computed once, by the caller, from live DB state.

## 11. Consumer Contract — "Not Yet Warmed"

Every reader of `PriceCache` has one defined fallback, restated here as the interface's actual contract (source: `PLAN.md` §6):

| Consumer | Behavior when `cache.get(ticker)` is `None` |
|---|---|
| `GET /api/watchlist` | `price: null` for that entry |
| Portfolio valuation | Position excluded from `total_value`; its `current_price` / P&L reported as `null` |
| Chat portfolio context | Ticker annotated `"price unavailable"` in the prompt context |
| `GET /api/history` | Ticker known but never updated → `points: []` (not `404`); ticker never registered at all → `404` |
| Frontend | Renders `—` |

This table is the same one in `PLAN.md` §6 with the `GET /api/history` row added, since that endpoint didn't exist when the original table was written.

## 12. File Structure

```
backend/
  app/
    market/
      __init__.py          # public exports
      models.py             # PriceUpdate
      interface.py           # MarketDataSource ABC
      cache.py               # PriceCache (+ history ring buffer, delta)
      history.py             # GET /api/history route factory (new, delta)
      seed_prices.py         # SEED_PRICES, TICKER_PARAMS, correlation groups
      simulator.py           # GBMSimulator + SimulatorDataSource
      massive_client.py      # MassiveDataSource
      factory.py              # create_market_data_source()
      stream.py               # SSE router (+ keepalive, delta)
```

`history.py` is a natural new module rather than folding the route into `stream.py` — it's a plain REST GET, not a streaming endpoint, and keeps `stream.py` focused on SSE.

## 13. Public API (`app/market/__init__.py`)

```python
from .cache import PriceCache
from .factory import create_market_data_source
from .history import create_history_router   # new
from .interface import MarketDataSource
from .models import PriceUpdate
from .stream import create_stream_router

__all__ = [
    "PriceUpdate",
    "PriceCache",
    "MarketDataSource",
    "create_market_data_source",
    "create_stream_router",
    "create_history_router",
]
```

## 14. Lifecycle Summary

1. **App startup**: `PriceCache()` → `create_market_data_source(cache)` → `await source.start(watchlist ∪ positions)` (§10).
2. **Watchlist changes**: `POST /api/watchlist` / LLM `watchlist_changes` → `source.add_ticker()`; `DELETE /api/watchlist/{ticker}` → `source.remove_ticker()` **only if no position holds that ticker** (`PLAN.md` §8) — otherwise the feed stays pinned.
3. **SSE streaming**: reads `PriceCache` every 500ms, pushes only on version change, sends a keepalive comment every ~15s of quiet.
4. **History backfill**: `GET /api/history?ticker=` reads the bounded ring buffer for sparkline/detail-chart seeding.
5. **Trade execution**: reads the current price via `PriceCache.get(ticker)` under the shared trade lock (`PLAN.md` §8).
6. **App shutdown**: `await source.stop()`.
