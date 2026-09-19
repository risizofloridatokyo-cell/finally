# Market Data Backend — Detailed Design

Single, implementation-ready design for FinAlly's market data subsystem: the unified `MarketDataSource` interface, the `PriceCache`, the GBM simulator, the Massive API client, SSE streaming, and how the rest of the backend (routes, DB, LLM chat) is meant to integrate with all of it. This document supersedes and consolidates `MASSIVE_API.md`, `MARKET_INTERFACE.md`, and `MARKET_SIMULATOR.md` into one place with runnable code, and folds in the corrections raised in `REVIEW.md`.

## Status

Most of this is **already implemented** in `backend/app/market/` (models, cache minus history, interface, factory, simulator, Massive client, SSE stream — see `MARKET_DATA_SUMMARY.md`). What's still design-only, called out explicitly throughout as **NEW**, is:

- The history ring buffer in `PriceCache` + `GET /api/history`
- `reconcile_tracked_tickers()` and its call sites in the watchlist/trade routes
- FastAPI lifespan wiring (no `app/main.py` exists yet — the rest of the platform, including this, is still to be built per `PLAN.md`)
- A two-line fix to `massive_client.py`'s timestamp handling (real bug, found during Massive API research — see §7.4)
- A correction to the SSE keepalive's actual purpose (§9.3) — it does **not** do what the original plan claimed

## Table of Contents

1. [Architecture](#1-architecture)
2. [File Structure](#2-file-structure)
3. [Data Model — `PriceUpdate`](#3-data-model--priceupdate)
4. [Price Cache](#4-price-cache)
5. [Abstract Interface — `MarketDataSource`](#5-abstract-interface--marketdatasource)
6. [Seed Prices & Ticker Parameters](#6-seed-prices--ticker-parameters)
7. [Massive API Client](#7-massive-api-client)
8. [GBM Simulator](#8-gbm-simulator)
9. [SSE Streaming Endpoint](#9-sse-streaming-endpoint)
10. [`GET /api/history`](#10-get-apihistory)
11. [Factory](#11-factory)
12. [FastAPI Lifecycle Integration](#12-fastapi-lifecycle-integration)
13. [Watchlist / Position Coordination](#13-watchlist--position-coordination)
14. [The "Not Yet Warmed" Contract](#14-the-not-yet-warmed-contract)
15. [Testing Strategy](#15-testing-strategy)
16. [Configuration Summary](#16-configuration-summary)
17. [Known Issues to Fix](#17-known-issues-to-fix)

---

## 1. Architecture

```
                    ┌──────────────────────────┐
                    │   create_market_data_source()   (factory)
                    └────────────┬─────────────┘
                                 │  MASSIVE_API_KEY set?
                 ┌───────────────┴───────────────┐
                 │ no (default)                  │ yes
                 ▼                                ▼
      SimulatorDataSource                MassiveDataSource
      (GBM, 500ms tick)                  (REST poll, 2–15s)
                 │                                │
                 └───────────────┬────────────────┘
                                 ▼
                          PriceCache
                (latest price + version counter
                 + bounded history ring buffer)
                                 │
        ┌────────────────┬──────┼──────────────┬─────────────────┐
        ▼                ▼      ▼               ▼                 ▼
 SSE /api/stream/   GET /api/    Portfolio    Chat portfolio   Trade execution
     prices          history     valuation       context        (fill price)
```

One writer at a time (whichever source is active), many readers. Nothing outside `app/market/` imports `SimulatorDataSource` or `MassiveDataSource` directly — every consumer goes through `PriceCache` or the factory.

---

## 2. File Structure

```
backend/
  app/
    market/
      __init__.py          # public exports
      models.py             # PriceUpdate                                   [implemented]
      interface.py           # MarketDataSource ABC                          [implemented]
      cache.py               # PriceCache (latest price)                    [implemented]
                              #   + history ring buffer                     [NEW]
      history.py             # GET /api/history route factory               [NEW]
      seed_prices.py         # SEED_PRICES, TICKER_PARAMS, correlations      [implemented]
      simulator.py           # GBMSimulator + SimulatorDataSource           [implemented]
      massive_client.py      # MassiveDataSource                            [implemented, 1 bug]
      factory.py              # create_market_data_source()                 [implemented]
      stream.py               # SSE router                                  [implemented]
                              #   + keepalive comment                       [NEW]
    watchlist.py             # POST/DELETE /api/watchlist, reconcile call    [NEW — this doc's §13]
    main.py                  # FastAPI app, lifespan, router mounting        [NEW — this doc's §12]
  tests/
    market/
      test_models.py         # [implemented]
      test_cache.py          # [implemented] + history buffer tests [NEW]
      test_interface.py      # (implicit, via subclass tests)
      test_simulator.py      # [implemented]
      test_simulator_source.py  # [implemented]
      test_massive.py        # [implemented]
      test_factory.py        # [implemented]
      test_history.py        # [NEW]
      test_stream.py         # [NEW — currently 31% covered, no dedicated tests]
```

---

## 3. Data Model — `PriceUpdate`

```python
# app/market/models.py

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
        """Absolute price change from previous update."""
        return round(self.price - self.previous_price, 4)

    @property
    def change_percent(self) -> float:
        """Percentage change from previous update."""
        if self.previous_price == 0:
            return 0.0
        return round((self.price - self.previous_price) / self.previous_price * 100, 4)

    @property
    def direction(self) -> str:
        """'up', 'down', or 'flat'."""
        if self.price > self.previous_price:
            return "up"
        if self.price < self.previous_price:
            return "down"
        return "flat"

    def to_dict(self) -> dict:
        """Serialize for JSON / SSE transmission."""
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

### Design decisions

- **`frozen=True, slots=True`** — immutable (no accidental mutation once published to consumers) and memory-efficient (no `__dict__` per instance; this object is created multiple times per second, per ticker).
- **`change`/`change_percent`/`direction` are computed properties, not stored fields.** There is exactly one source of truth (`price`, `previous_price`) — a stored `direction` field could theoretically drift out of sync with the prices it describes; a computed property cannot.
- **`timestamp` is always Unix seconds (float), everywhere in this layer.** Both data sources are responsible for converting their native units before calling `PriceCache.update()` — Massive's aggregate bars are milliseconds, its trade/quote `sip_timestamp` is **nanoseconds** (see §7.4). Normalizing at the boundary means nothing downstream of the cache ever needs to know which source produced a given `PriceUpdate`.
- **This is the only shape that leaves `app/market/`.** SSE, `GET /api/history`, portfolio valuation, and chat context all consume `PriceUpdate` (or `.to_dict()` of it) — never a raw `TickerSnapshot` or GBM float.

---

## 4. Price Cache

```python
# app/market/cache.py

from __future__ import annotations

import time
from collections import deque
from threading import Lock

from .models import PriceUpdate


class PriceCache:
    """Thread-safe in-memory cache of the latest price + recent history for each ticker.

    Writers: SimulatorDataSource or MassiveDataSource (one at a time, one process).
    Readers: SSE endpoint, GET /api/history, portfolio valuation, trade execution,
             chat portfolio context.
    """

    HISTORY_CAPACITY = 300  # ~2.5 min at 500ms ticks; also GET /api/history's default limit

    def __init__(self) -> None:
        self._prices: dict[str, PriceUpdate] = {}
        self._history: dict[str, deque[tuple[float, float]]] = {}  # ticker -> deque[(price, ts)]
        self._lock = Lock()
        self._version: int = 0  # monotonically increasing; bumped on every update

    def update(self, ticker: str, price: float, timestamp: float | None = None) -> PriceUpdate:
        """Record a new price for a ticker. Returns the created PriceUpdate.

        Computes direction/change implicitly (via PriceUpdate's properties) from the
        previous cached price. First update for a ticker: previous_price == price
        (direction == 'flat'). Also appends to that ticker's bounded history buffer —
        one write path feeds both the latest-price map and the history ring buffer.
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

            buf = self._history.get(ticker)
            if buf is None:
                buf = deque(maxlen=self.HISTORY_CAPACITY)
                self._history[ticker] = buf
            buf.append((update.price, ts))

            self._version += 1
            return update

    def get(self, ticker: str) -> PriceUpdate | None:
        """Get the latest price for a single ticker, or None if unknown/not warmed."""
        with self._lock:
            return self._prices.get(ticker)

    def get_all(self) -> dict[str, PriceUpdate]:
        """Snapshot of all current prices. Returns a shallow copy (safe to iterate)."""
        with self._lock:
            return dict(self._prices)

    def get_price(self, ticker: str) -> float | None:
        """Convenience: just the price float, or None."""
        update = self._prices.get(ticker)  # single dict read; no lock needed for one get()
        return update.price if update else None

    def get_history(self, ticker: str, limit: int | None = None) -> list[dict] | None:
        """Oldest-first recent price points for a ticker.

        Returns:
          - None            if the ticker has never been registered (never updated)
          - []               if registered but no points yet (shouldn't normally happen —
                              update() always appends — but kept for a ticker added via
                              add_ticker() with no seed price available)
          - [{"price", "timestamp"}, ...]   oldest first, most recent `limit` points

        The None/[] distinction is what lets the route return 404 for an unknown ticker
        vs. 200 with an empty backfill for a known-but-quiet one.
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
        """Remove a ticker from the cache (both latest price and history)."""
        with self._lock:
            self._prices.pop(ticker, None)
            self._history.pop(ticker, None)

    @property
    def version(self) -> int:
        """Current version counter. Used by SSE for push-on-change detection."""
        with self._lock:
            return self._version

    def __len__(self) -> int:
        with self._lock:
            return len(self._prices)

    def __contains__(self, ticker: str) -> bool:
        with self._lock:
            return ticker in self._prices
```

### Why a version counter?

The SSE endpoint polls the cache every 500ms but should only *send* when something actually changed — otherwise every connected client gets a full JSON payload 2×/second even during a dead-quiet market. A single integer, bumped once per `update()` call and compared by the SSE loop (`current_version != last_sent_version`), makes "did anything change since I last sent?" an O(1) check instead of a value-by-value diff of the whole price map.

### Thread safety rationale

The simulator's asyncio task and the Massive client's `asyncio.to_thread`-wrapped poll both ultimately call `cache.update()` from different execution contexts (an event-loop callback vs. a thread-pool thread). A plain `threading.Lock` around all mutating/reading operations is correct and cheap here — updates are infrequent enough (at most one source active at a time, ticks every 500ms–15s) that lock contention is a non-issue.

### `version` under lock (delta from the reviewed implementation)

The implemented `cache.py` reads `self._version` in the `version` property **without** acquiring the lock, reasoning that a single `int` read is atomic under CPython's GIL. `MARKET_DATA_REVIEW.md` flagged this as fine today but a latent risk on a no-GIL Python build (PEP 703, 3.13t+). The snippet above takes the lock — it's a single extra `with self._lock:` on a rarely-contended lock, cheap insurance, and keeps every method in the class consistently locked rather than one silent exception to the rule.

---

## 5. Abstract Interface — `MarketDataSource`

```python
# app/market/interface.py

from __future__ import annotations

from abc import ABC, abstractmethod


class MarketDataSource(ABC):
    """Contract for market data providers.

    Implementations push price updates into a shared PriceCache on their own
    schedule. Downstream code never calls the data source directly for prices —
    it always reads from the cache.

    Lifecycle:
        source = create_market_data_source(cache)
        await source.start(["AAPL", "GOOGL", ...])
        # ... app runs ...
        await source.add_ticker("TSLA")
        await source.remove_ticker("GOOGL")
        # ... app shutting down ...
        await source.stop()
    """

    @abstractmethod
    async def start(self, tickers: list[str]) -> None:
        """Begin producing price updates for the given tickers.

        Starts a background task that periodically writes to the PriceCache.
        Must be called exactly once. Calling start() twice is undefined behavior.
        """

    @abstractmethod
    async def stop(self) -> None:
        """Stop the background task and release resources. Safe to call multiple times."""

    @abstractmethod
    async def add_ticker(self, ticker: str) -> None:
        """Add a ticker to the active set. No-op if already present."""

    @abstractmethod
    async def remove_ticker(self, ticker: str) -> None:
        """Remove a ticker from the active set. Also evicts it from the PriceCache."""

    @abstractmethod
    def get_tickers(self) -> list[str]:
        """Return the current list of actively tracked tickers."""
```

### Why the source writes to the cache instead of returning prices

If `MarketDataSource` instead exposed a `get_price(ticker) -> float` pull API, every caller would need to know which concrete source is active and how fresh its data is (does calling it block on a network round-trip?). Push-to-cache means:

- The simulator can tick at 500ms and Massive at 15s **without either concern leaking to callers** — a caller always just reads the cache, which is always in-memory and instant.
- Trade execution, SSE, and chat context all read the *same* cached value at a given instant — no risk of two reads racing two different live API calls and getting inconsistent prices for a single trade.
- Switching sources (simulator ↔ Massive) via `MASSIVE_API_KEY` requires touching exactly one function (`create_market_data_source`, §11) — nothing else in the codebase branches on which source is active.

---

## 6. Seed Prices & Ticker Parameters

```python
# app/market/seed_prices.py

# Realistic starting prices for the default watchlist (as of project creation)
SEED_PRICES: dict[str, float] = {
    "AAPL": 190.00,
    "GOOGL": 175.00,
    "MSFT": 420.00,
    "AMZN": 185.00,
    "TSLA": 250.00,
    "NVDA": 800.00,
    "META": 500.00,
    "JPM": 195.00,
    "V": 280.00,
    "NFLX": 600.00,
}

# Per-ticker GBM parameters
# sigma: annualized volatility (higher = more price movement)
# mu: annualized drift / expected return
TICKER_PARAMS: dict[str, dict[str, float]] = {
    "AAPL": {"sigma": 0.22, "mu": 0.05},
    "GOOGL": {"sigma": 0.25, "mu": 0.05},
    "MSFT": {"sigma": 0.20, "mu": 0.05},
    "AMZN": {"sigma": 0.28, "mu": 0.05},
    "TSLA": {"sigma": 0.50, "mu": 0.03},  # High volatility
    "NVDA": {"sigma": 0.40, "mu": 0.08},  # High volatility, strong drift
    "META": {"sigma": 0.30, "mu": 0.05},
    "JPM": {"sigma": 0.18, "mu": 0.04},  # Low volatility (bank)
    "V": {"sigma": 0.17, "mu": 0.04},  # Low volatility (payments)
    "NFLX": {"sigma": 0.35, "mu": 0.05},
}

# Default parameters for tickers not in the list above (dynamically added, e.g. via chat)
DEFAULT_PARAMS: dict[str, float] = {"sigma": 0.25, "mu": 0.05}

# Correlation groups for the simulator's Cholesky decomposition.
# Tickers in the same group have higher intra-group correlation.
CORRELATION_GROUPS: dict[str, set[str]] = {
    "tech": {"AAPL", "GOOGL", "MSFT", "AMZN", "META", "NVDA", "NFLX"},
    "finance": {"JPM", "V"},
}

# Correlation coefficients
INTRA_TECH_CORR = 0.6      # Tech stocks move together
INTRA_FINANCE_CORR = 0.5   # Finance stocks move together
CROSS_GROUP_CORR = 0.3     # Between sectors / unknown tickers — also the fallback for
                            # any ticker (seeded or dynamically added) not in either group
TSLA_CORR = 0.3             # TSLA does its own thing, even though it's nominally in "tech"
```

A ticker added at runtime that isn't in `SEED_PRICES`/`TICKER_PARAMS` gets a random seed price (`random.uniform(50.0, 300.0)`, chosen in `simulator.py` at add-time, not stored here) and `DEFAULT_PARAMS`. It automatically falls into `CROSS_GROUP_CORR` (0.3) with everything else via the pairwise-correlation fallback in §8 — no special-casing needed in this module.

*(Naming note: an earlier draft also defined an unused `DEFAULT_CORR` constant that duplicated `CROSS_GROUP_CORR`'s value; it's omitted here per `MARKET_DATA_REVIEW.md` §4.3 — keep exactly one named constant for the 0.3 fallback.)*

---

## 7. Massive API Client

Full endpoint/schema research lives in `MASSIVE_API.md`; this section is the implementation.

### 7.1 Plan/rate-limit reality (drives the interval default)

| Tier | Calls | Freshness |
|---|---|---|
| Free | 5/min | **EOD only** |
| Starter ($29/mo) | Unlimited | 15-min delayed |
| Advanced ($199/mo) | Unlimited | Real-time |

FinAlly polls on a fixed timer regardless of tier — it does not detect or adapt to plan freshness, since there's no API signal for that. Free tier: **15s** interval (4 calls/min, safely under 5/min). Paid tiers: 2–15s at the operator's discretion via the `poll_interval` constructor argument.

### 7.2 Client

```python
# app/market/massive_client.py

from __future__ import annotations

import asyncio
import logging

from massive import RESTClient

from .cache import PriceCache
from .interface import MarketDataSource

logger = logging.getLogger(__name__)


class MassiveDataSource(MarketDataSource):
    """MarketDataSource backed by the Massive (formerly Polygon.io) REST API.

    Polls GET /v2/snapshot/locale/us/markets/stocks/tickers for all watched
    tickers in a single API call, then writes results to the PriceCache.

    Rate limits:
      - Free tier: 5 req/min, EOD data only -> poll every 15s (default)
      - Paid tiers: unlimited calls, 15-min-delayed or real-time -> poll every 2-15s
    """

    def __init__(
        self,
        api_key: str,
        price_cache: PriceCache,
        poll_interval: float = 15.0,
    ) -> None:
        self._api_key = api_key
        self._cache = price_cache
        self._interval = poll_interval
        self._tickers: list[str] = []
        self._task: asyncio.Task | None = None
        self._client: RESTClient | None = None

    async def start(self, tickers: list[str]) -> None:
        self._client = RESTClient(api_key=self._api_key)
        self._tickers = list(tickers)

        # Immediate first poll so the cache has data right away, not after
        # a full interval of waiting.
        await self._poll_once()

        self._task = asyncio.create_task(self._poll_loop(), name="massive-poller")
        logger.info(
            "Massive poller started: %d tickers, %.1fs interval",
            len(tickers),
            self._interval,
        )

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        self._client = None
        logger.info("Massive poller stopped")

    async def add_ticker(self, ticker: str) -> None:
        ticker = ticker.upper().strip()
        if ticker not in self._tickers:
            self._tickers.append(ticker)
            logger.info("Massive: added ticker %s (will appear on next poll)", ticker)

    async def remove_ticker(self, ticker: str) -> None:
        ticker = ticker.upper().strip()
        self._tickers = [t for t in self._tickers if t != ticker]
        self._cache.remove(ticker)
        logger.info("Massive: removed ticker %s", ticker)

    def get_tickers(self) -> list[str]:
        return list(self._tickers)

    # --- Internal ---

    async def _poll_loop(self) -> None:
        """Poll on interval. First poll already happened in start()."""
        while True:
            await asyncio.sleep(self._interval)
            await self._poll_once()

    async def _poll_once(self) -> None:
        """Execute one poll cycle: fetch snapshots, update cache."""
        if not self._tickers or not self._client:
            return

        try:
            # The Massive RESTClient is synchronous -- run in a thread pool to
            # avoid blocking the event loop.
            snapshots = await asyncio.to_thread(self._fetch_snapshots)
            processed = 0
            for snap in snapshots:
                if snap.last_trade is None or snap.last_trade.price is None:
                    # Ticker came back in the response but has no trade yet
                    # (e.g. pre-market on a thinly traded symbol). Leave it
                    # "not warmed" for this cycle rather than writing a bogus price.
                    continue
                try:
                    self._cache.update(
                        ticker=snap.ticker,
                        price=snap.last_trade.price,
                        # sip_timestamp is NANOSECONDS since epoch -- see §7.4.
                        timestamp=(snap.last_trade.sip_timestamp or 0) / 1_000_000_000,
                    )
                    processed += 1
                except (AttributeError, TypeError) as e:
                    logger.warning(
                        "Skipping snapshot for %s: %s",
                        getattr(snap, "ticker", "???"),
                        e,
                    )
            logger.debug("Massive poll: updated %d/%d tickers", processed, len(self._tickers))

        except Exception as e:
            logger.error("Massive poll failed: %s", e)
            # Don't re-raise -- the loop retries on the next interval.
            # Common failures: 401 (bad key), 429 (rate limit), network errors.
            # A ticker that never appears in a successful response simply stays
            # "not warmed" -- see §14.

    def _fetch_snapshots(self) -> list:
        """Synchronous call to the Massive REST API. Runs in a thread."""
        return self._client.get_snapshot_all("stocks", self._tickers)
```

### 7.3 Error handling philosophy

`_poll_once` catches broadly (`except Exception`) around the whole network call, because a poll cycle failing (rate limit, transient network blip, momentary auth hiccup) must never crash the long-lived background task — the *entire app's* live prices depend on this task staying alive. The narrower `except (AttributeError, TypeError)` around individual snapshot processing means one malformed snapshot (unexpected shape from the API) skips just that ticker instead of aborting the whole poll cycle's remaining tickers.

An invalid/unknown ticker doesn't raise at all — Massive's snapshot-all endpoint simply omits it from the response list (see `MASSIVE_API.md` §4.1). It stays in `self._tickers` (so it's retried every cycle, in case it becomes valid — e.g. after a market open) but never gets a cache entry, i.e. it's permanently "not warmed" until removed.

### 7.4 Timestamp bug — fix required before real API use

The snippet above already has the fix applied; flagging it explicitly because it's a real, confirmed defect against the actual Massive SDK, discovered during the `MASSIVE_API.md` research:

```python
# WRONG (what an earlier draft of massive_client.py had):
price = snap.last_trade.price
timestamp = snap.last_trade.timestamp / 1000.0   # ms -> seconds

# CORRECT:
price = snap.last_trade.price
timestamp = (snap.last_trade.sip_timestamp or 0) / 1_000_000_000   # ns -> seconds
```

`LastTrade` has no `.timestamp` attribute at all in the real SDK (`massive/rest/models/trades.py`) — only `sip_timestamp`, `participant_timestamp`, `trf_timestamp`, all in **nanoseconds**. The old code would raise `AttributeError` on the very first live poll against a real API key. It went uncaught because `test_massive.py` mocks the snapshot objects itself, and the mock apparently defined a `.timestamp` attribute that doesn't exist on the real class — a case of the test faithfully verifying the mock instead of the contract. Note by contrast that `Agg.timestamp` (used for `day`/`prev_day`/aggregate bars, not touched by this poller) genuinely is milliseconds — the inconsistency between fields is what makes this easy to get wrong.

### 7.5 Lazy vs. core dependency

`pyproject.toml` declares `massive>=1.0.0` as a **core** dependency (not optional), so `from massive import RESTClient` at module top level is safe — no `massive` package missing at simulator-only runtime, since it's always installed. This was a deliberate choice recorded in `MARKET_DATA_SUMMARY.md`'s fix list: an earlier draft lazy-imported `massive` inside methods specifically to make it optional, but that broke test mocking (`patch("app.market.massive_client.RESTClient")` needs the name to exist at module level) for no real benefit, since the package is small and always installed anyway.

---

## 8. GBM Simulator

Full math derivation and rationale is in `MARKET_SIMULATOR.md`; reproduced here as the authoritative code.

### 8.1 `GBMSimulator` — pure math engine

```python
# app/market/simulator.py

from __future__ import annotations

import asyncio
import logging
import math
import random

import numpy as np

from .cache import PriceCache
from .interface import MarketDataSource
from .seed_prices import (
    CORRELATION_GROUPS,
    CROSS_GROUP_CORR,
    DEFAULT_PARAMS,
    INTRA_FINANCE_CORR,
    INTRA_TECH_CORR,
    SEED_PRICES,
    TICKER_PARAMS,
    TSLA_CORR,
)

logger = logging.getLogger(__name__)


class GBMSimulator:
    """Geometric Brownian Motion simulator for correlated stock prices.

    Math:
        S(t+dt) = S(t) * exp((mu - sigma^2/2) * dt + sigma * sqrt(dt) * Z)

    Where:
        S(t)   = current price
        mu     = annualized drift (expected return)
        sigma  = annualized volatility
        dt     = time step as a fraction of a trading year
        Z      = correlated standard normal random variable

    The tiny dt (~8.5e-8 for 500ms ticks over 252 trading days * 6.5h/day)
    produces sub-cent moves per tick that accumulate naturally over time.
    """

    TRADING_SECONDS_PER_YEAR = 252 * 6.5 * 3600  # 5,896,800
    DEFAULT_DT = 0.5 / TRADING_SECONDS_PER_YEAR  # ~8.48e-8

    def __init__(
        self,
        tickers: list[str],
        dt: float = DEFAULT_DT,
        event_probability: float = 0.001,
    ) -> None:
        self._dt = dt
        self._event_prob = event_probability

        self._tickers: list[str] = []
        self._prices: dict[str, float] = {}
        self._params: dict[str, dict[str, float]] = {}
        self._cholesky: np.ndarray | None = None

        for ticker in tickers:
            self._add_ticker_internal(ticker)
        self._rebuild_cholesky()

    # --- Public API ---

    def step(self) -> dict[str, float]:
        """Advance all tickers by one time step. Returns {ticker: new_price}.

        Hot path -- called every 500ms. Keep it fast.
        """
        n = len(self._tickers)
        if n == 0:
            return {}

        z_independent = np.random.standard_normal(n)
        z_correlated = self._cholesky @ z_independent if self._cholesky is not None else z_independent

        result: dict[str, float] = {}
        for i, ticker in enumerate(self._tickers):
            params = self._params[ticker]
            mu = params["mu"]
            sigma = params["sigma"]

            drift = (mu - 0.5 * sigma**2) * self._dt
            diffusion = sigma * math.sqrt(self._dt) * z_correlated[i]
            self._prices[ticker] *= math.exp(drift + diffusion)

            # Random event: ~0.1% chance per tick per ticker.
            # 10 tickers @ 2 ticks/sec -> a visible event roughly every ~50s.
            if random.random() < self._event_prob:
                shock_magnitude = random.uniform(0.02, 0.05)
                shock_sign = random.choice([-1, 1])
                self._prices[ticker] *= 1 + shock_magnitude * shock_sign
                logger.debug(
                    "Random event on %s: %.1f%% %s",
                    ticker,
                    shock_magnitude * 100,
                    "up" if shock_sign > 0 else "down",
                )

            result[ticker] = round(self._prices[ticker], 2)

        return result

    def add_ticker(self, ticker: str) -> None:
        """Add a ticker mid-session. Rebuilds the correlation matrix."""
        if ticker in self._prices:
            return
        self._add_ticker_internal(ticker)
        self._rebuild_cholesky()

    def remove_ticker(self, ticker: str) -> None:
        """Remove a ticker. Rebuilds the correlation matrix."""
        if ticker not in self._prices:
            return
        self._tickers.remove(ticker)
        del self._prices[ticker]
        del self._params[ticker]
        self._rebuild_cholesky()

    def get_price(self, ticker: str) -> float | None:
        return self._prices.get(ticker)

    def get_tickers(self) -> list[str]:
        """Public accessor -- SimulatorDataSource must use this, not `_tickers`."""
        return list(self._tickers)

    # --- Internals ---

    def _add_ticker_internal(self, ticker: str) -> None:
        """Add without rebuilding Cholesky -- for batch init in __init__."""
        if ticker in self._prices:
            return
        self._tickers.append(ticker)
        self._prices[ticker] = SEED_PRICES.get(ticker, random.uniform(50.0, 300.0))
        self._params[ticker] = TICKER_PARAMS.get(ticker, dict(DEFAULT_PARAMS))

    def _rebuild_cholesky(self) -> None:
        """Rebuild the Cholesky decomposition of the ticker correlation matrix.

        Called on every add/remove. O(n^2) matrix build + O(n^3) decomposition,
        but n stays small (tens of tickers) in any realistic session.
        """
        n = len(self._tickers)
        if n <= 1:
            self._cholesky = None
            return

        corr = np.eye(n)
        for i in range(n):
            for j in range(i + 1, n):
                rho = self._pairwise_correlation(self._tickers[i], self._tickers[j])
                corr[i, j] = rho
                corr[j, i] = rho

        self._cholesky = np.linalg.cholesky(corr)

    @staticmethod
    def _pairwise_correlation(t1: str, t2: str) -> float:
        """Correlation between two tickers based on sector grouping.

        - TSLA with anything:    0.3 (checked first -- it's nominally in "tech"
                                  but should not inherit the 0.6 intra-tech rate)
        - Same tech sector:       0.6
        - Same finance sector:    0.5
        - Cross-sector/unknown:   0.3
        """
        tech = CORRELATION_GROUPS["tech"]
        finance = CORRELATION_GROUPS["finance"]

        if t1 == "TSLA" or t2 == "TSLA":
            return TSLA_CORR
        if t1 in tech and t2 in tech:
            return INTRA_TECH_CORR
        if t1 in finance and t2 in finance:
            return INTRA_FINANCE_CORR
        return CROSS_GROUP_CORR
```

`GBMSimulator` is pure, synchronous, allocation-light on the hot path, and touches nothing outside its own state — this is what makes it trivially unit-testable (17 tests, 98% coverage) independent of asyncio scheduling or the price cache.

### 8.2 `SimulatorDataSource` — async wrapper

```python
class SimulatorDataSource(MarketDataSource):
    """MarketDataSource backed by the GBM simulator.

    Runs a background asyncio task that calls GBMSimulator.step() every
    `update_interval` seconds and writes results to the PriceCache.
    """

    def __init__(
        self,
        price_cache: PriceCache,
        update_interval: float = 0.5,
        event_probability: float = 0.001,
    ) -> None:
        self._cache = price_cache
        self._interval = update_interval
        self._event_prob = event_probability
        self._sim: GBMSimulator | None = None
        self._task: asyncio.Task | None = None

    async def start(self, tickers: list[str]) -> None:
        self._sim = GBMSimulator(tickers=tickers, event_probability=self._event_prob)
        # Seed the cache immediately so SSE/history have data with no visible delay.
        for ticker in tickers:
            price = self._sim.get_price(ticker)
            if price is not None:
                self._cache.update(ticker=ticker, price=price)
        self._task = asyncio.create_task(self._run_loop(), name="simulator-loop")
        logger.info("Simulator started with %d tickers", len(tickers))

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.info("Simulator stopped")

    async def add_ticker(self, ticker: str) -> None:
        if self._sim:
            self._sim.add_ticker(ticker)
            price = self._sim.get_price(ticker)
            if price is not None:
                self._cache.update(ticker=ticker, price=price)
            logger.info("Simulator: added ticker %s", ticker)

    async def remove_ticker(self, ticker: str) -> None:
        if self._sim:
            self._sim.remove_ticker(ticker)
        self._cache.remove(ticker)
        logger.info("Simulator: removed ticker %s", ticker)

    def get_tickers(self) -> list[str]:
        return self._sim.get_tickers() if self._sim else []

    async def _run_loop(self) -> None:
        """Core loop: step the simulation, write to cache, sleep."""
        while True:
            try:
                if self._sim:
                    prices = self._sim.step()
                    for ticker, price in prices.items():
                        self._cache.update(ticker=ticker, price=price)
            except Exception:
                logger.exception("Simulator step failed")
            await asyncio.sleep(self._interval)
```

### Key behaviors

- **Seed-on-add.** Both `start()` and `add_ticker()` write an initial price synchronously rather than waiting for the next 500ms tick — a ticker is never "not warmed" for longer than necessary.
- **`_run_loop` survives a bad step.** `except Exception` around `self._sim.step()` means one arithmetic edge case logs and skips a tick rather than silently killing the loop (and freezing every price in the app — this task is the only writer).
- **`get_tickers()` goes through `GBMSimulator.get_tickers()`**, not `self._sim._tickers` — `MARKET_DATA_REVIEW.md` flagged reaching into the private attribute as a boundary violation; the public method exists specifically to avoid it.

---

## 9. SSE Streaming Endpoint

### 9.1 Router

```python
# app/market/stream.py

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from .cache import PriceCache

logger = logging.getLogger(__name__)


def create_stream_router(price_cache: PriceCache) -> APIRouter:
    """Create the SSE streaming router with a reference to the price cache.

    Factory pattern (rather than a module-level router with a route registered
    via closure) so calling this twice -- e.g. once per test -- doesn't register
    the same route twice on a shared router object.
    """
    router = APIRouter(prefix="/api/stream", tags=["streaming"])

    @router.get("/prices")
    async def stream_prices(request: Request) -> StreamingResponse:
        """SSE endpoint for live price updates.

        Streams all tracked ticker prices, pushed only when something changed
        (via the cache's version counter), plus a periodic keepalive comment.
        Client connects with the native EventSource API.
        """
        return StreamingResponse(
            _generate_events(price_cache, request),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # disable nginx buffering if proxied
            },
        )

    return router


async def _generate_events(
    price_cache: PriceCache,
    request: Request,
    interval: float = 0.5,
    keepalive_interval: float = 15.0,
) -> AsyncGenerator[str, None]:
    """Yield SSE-formatted price events. Stops when the client disconnects."""
    yield "retry: 1000\n\n"  # tell EventSource to reconnect after 1s if dropped

    last_version = -1
    last_sent = time.monotonic()
    client_ip = request.client.host if request.client else "unknown"
    logger.info("SSE client connected: %s", client_ip)

    try:
        while True:
            if await request.is_disconnected():
                logger.info("SSE client disconnected: %s", client_ip)
                break

            current_version = price_cache.version
            if current_version != last_version:
                last_version = current_version
                prices = price_cache.get_all()
                if prices:
                    data = {ticker: update.to_dict() for ticker, update in prices.items()}
                    yield f"data: {json.dumps(data)}\n\n"
                    last_sent = time.monotonic()
            elif time.monotonic() - last_sent >= keepalive_interval:
                yield ": keepalive\n\n"  # comment line -- see §9.3 for what this can/can't do
                last_sent = time.monotonic()

            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        logger.info("SSE stream cancelled for: %s", client_ip)
```

### 9.2 On-connect snapshot

The first loop iteration after `retry: 1000\n\n` always sees `current_version != last_version` (since `last_version` starts at `-1`, an impossible real version), so a newly connected client gets a full price snapshot on its very first poll of the loop — no waiting for the next actual price change. This satisfies `PLAN.md` §6's "server emits an immediate full snapshot on connect."

### 9.3 What the keepalive comment actually does (correction from `REVIEW.md`)

The original plan asserted the ~15s `: keepalive` comment lets frontend JavaScript "distinguish connected-but-quiet from stalled," feeding the three-state connection dot. **`REVIEW.md` correctly flags this as impossible**: the native `EventSource` API does not expose received SSE comment lines to JavaScript at all — `onmessage` only fires for actual `data:` events, never for `:`-prefixed comments. There is no client-side hook a comment can trigger.

What the keepalive comment **is** genuinely good for:
- Keeping the underlying TCP connection visibly active across any intermediary (a reverse proxy, a corporate firewall, a load balancer) that would otherwise time out and silently drop an idle-looking connection after some quiet period.
- A cheap, low-overhead heartbeat that costs one line of bytes every 15s regardless of how "quiet" the market is (i.e., it fires whenever a full keepalive interval passes with zero price changes — a genuinely idle simulator/Massive feed, not just idle in-between-ticks).

What it does **not** do, and what the frontend must not be built to expect:
- It cannot reset a client-side JS heartbeat/staleness timer, because JS never sees it.
- It is not the mechanism behind the three-state connection dot.

**Corrected contract** (supersedes `PLAN.md` §10's "keepalive keeps a quiet stream green" framing): the connection dot is derived **purely from `EventSource`'s own connection state**, independent of payload content:
- **Green** — `onopen` has fired and `readyState === EventSource.OPEN`.
- **Yellow** — `onerror` fired while `readyState === EventSource.CONNECTING` (browser is auto-reconnecting).
- **Red** — `readyState === EventSource.CLOSED`.

A quiet market (no price changes, only keepalive comments on the wire) stays green under this model for the right reason: the TCP connection and `EventSource` object are still open, not because a comment told the frontend "still alive." The keepalive's job is entirely at the transport layer (stopping infrastructure from killing the socket); the UI's job is entirely at the `EventSource` API layer. If a future requirement needs the *frontend* to detect "no price movement for N seconds" as a distinct state from "connection is open," that requires an actual parsed `data:` heartbeat event (e.g. `data: {"type": "heartbeat"}`), not a comment — out of scope unless that requirement is explicitly added.

### 9.4 Why poll-and-push instead of purely event-driven

The generator sleeps `interval` (500ms) between checks rather than being woken directly by `cache.update()` (e.g. via an `asyncio.Event` or pub/sub). This is a deliberate simplicity trade-off: with N connected SSE clients all polling the same in-memory cache every 500ms, the cost is N cheap dict-copy-and-compare operations per tick — trivial at FinAlly's scale (single-user, an in-process cache, no network round-trip per poll). An event-driven push would remove a bounded ~500ms worst-case latency between a price change and clients seeing it, at the cost of meaningfully more plumbing (fan-out to N waiting coroutines) for a benefit that doesn't matter at this scale.

---

## 10. `GET /api/history`

```python
# app/market/history.py

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from .cache import PriceCache


def create_history_router(price_cache: PriceCache) -> APIRouter:
    """GET /api/history?ticker=SYM&limit=N -- ring-buffer backfill for
    sparklines and the detail chart.
    """
    router = APIRouter(prefix="/api", tags=["market"])

    @router.get("/history")
    async def get_history(
        ticker: str,
        limit: int = Query(default=PriceCache.HISTORY_CAPACITY, gt=0, le=PriceCache.HISTORY_CAPACITY),
    ):
        symbol = ticker.upper().strip()
        points = price_cache.get_history(symbol, limit=limit)
        if points is None:
            raise HTTPException(status_code=404, detail=f"Ticker '{symbol}' is not tracked")
        return {"ticker": symbol, "points": points}

    return router
```

Contract (matches `PLAN.md` §8, with the capacity/response-shape ambiguity `REVIEW.md` flagged now pinned down):

- `limit` optional, default **300**, capped at `PriceCache.HISTORY_CAPACITY` (also 300) via FastAPI's `Query(..., le=...)` validation — a request for more than the buffer holds gets clamped by the framework itself, not silently truncated server-side.
- Response: `{"ticker": "AAPL", "points": [{"price": 190.12, "timestamp": 1735689600.0}, ...]}`, **oldest-first**.
- `ticker` is upper-cased and trimmed before lookup, matching the format normalization used everywhere else tickers are accepted (`PLAN.md` §6).
- **`404`** only for a ticker that has genuinely never been tracked (`get_history` returns `None`). A tracked-but-momentarily-quiet ticker returns `200` with whatever points exist (possibly `[]` for the instant right after `add_ticker` before the first `update()` call lands — though in practice both data sources seed a price synchronously at add-time, so this window is effectively zero).
- Every point records the price **as stored** (already rounded to 2 decimals by `PriceCache.update()`), so the frontend does no additional rounding.

This route is mounted separately from `stream.py`'s router — it's a plain request/response GET, not a streaming endpoint, and keeping it in its own module keeps `stream.py` focused purely on the SSE contract.

---

## 11. Factory

```python
# app/market/factory.py

from __future__ import annotations

import logging
import os

from .cache import PriceCache
from .interface import MarketDataSource
from .massive_client import MassiveDataSource
from .simulator import SimulatorDataSource

logger = logging.getLogger(__name__)


def create_market_data_source(price_cache: PriceCache) -> MarketDataSource:
    """Create the appropriate market data source based on environment variables.

    - MASSIVE_API_KEY set and non-empty -> MassiveDataSource (real market data)
    - Otherwise                          -> SimulatorDataSource (GBM simulation)

    Returns an UNSTARTED source. Caller must await source.start(tickers).
    """
    api_key = os.environ.get("MASSIVE_API_KEY", "").strip()

    if api_key:
        logger.info("Market data source: Massive API (real data)")
        return MassiveDataSource(api_key=api_key, price_cache=price_cache)

    logger.info("Market data source: GBM Simulator")
    return SimulatorDataSource(price_cache=price_cache)
```

This one `if` is the entire seam between "demo mode" and "real data mode." No other module in the codebase should ever check `os.environ["MASSIVE_API_KEY"]` directly — everything downstream operates on the `MarketDataSource` interface, blind to which concrete class it got.

### Public exports

```python
# app/market/__init__.py

from .cache import PriceCache
from .factory import create_market_data_source
from .history import create_history_router
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

---

## 12. FastAPI Lifecycle Integration

No `app/main.py` exists yet — this is genuinely new design, since the rest of the platform (DB, portfolio, watchlist, chat routes) is still to be built per `PLAN.md`. This section makes the startup order authoritative, resolving the contradiction `REVIEW.md` flagged between "DB lazily initializes on first request" (`PLAN.md` §4) and "market data starts from the DB's current watchlist ∪ positions on every boot" (`PLAN.md` §6) — those cannot both be true as stated. **Application-lifespan startup is authoritative**; any lazy-init path (e.g. a test helper that touches the DB before the app's lifespan has run) is explicitly out of scope for the normal run path.

```python
# app/main.py

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.market import PriceCache, create_history_router, create_market_data_source, create_stream_router
from app.db import init_db, get_watchlist_tickers, get_position_tickers
from app.snapshots import start_snapshot_tasks, stop_snapshot_tasks


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. DB: create tables + seed defaults if missing/empty. Authoritative point
    #    of DB readiness -- nothing before this touches the DB.
    await init_db()

    # 2. Read CURRENT state, not the hardcoded default 10 -- the user may have
    #    edited the watchlist in a prior run against a persisted volume.
    watchlist_tickers = await get_watchlist_tickers()
    position_tickers = await get_position_tickers()
    initial_tickers = sorted(set(watchlist_tickers) | set(position_tickers))

    # 3. Start market data on that union.
    price_cache = PriceCache()
    market_source = create_market_data_source(price_cache)
    await market_source.start(initial_tickers)

    app.state.price_cache = price_cache
    app.state.market_source = market_source

    # 4. Background tasks: portfolio snapshotter (60s) + snapshot retention (daily).
    await start_snapshot_tasks(app)

    yield  # ---- app runs ----

    # Shutdown, reverse order.
    await stop_snapshot_tasks(app)
    await market_source.stop()


app = FastAPI(lifespan=lifespan)

app.include_router(create_stream_router(price_cache=None))  # see note below
app.include_router(create_history_router(price_cache=None))
```

The router-mounting lines above are illustrative of intent only — `create_stream_router`/`create_history_router` need the *actual* `price_cache` instance, which only exists once `lifespan` has run. The clean way to resolve this in FastAPI is a dependency that reads from `app.state` rather than capturing `price_cache` in a closure at import time:

```python
# app/dependencies.py

from fastapi import Request

from app.market import PriceCache, MarketDataSource


def get_price_cache(request: Request) -> PriceCache:
    return request.app.state.price_cache


def get_market_source(request: Request) -> MarketDataSource:
    return request.app.state.market_source
```

```python
# app/market/history.py -- revised to take a dependency instead of a closed-over cache

from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies import get_price_cache
from .cache import PriceCache

router = APIRouter(prefix="/api", tags=["market"])


@router.get("/history")
async def get_history(
    ticker: str,
    limit: int = Query(default=PriceCache.HISTORY_CAPACITY, gt=0, le=PriceCache.HISTORY_CAPACITY),
    cache: PriceCache = Depends(get_price_cache),
):
    symbol = ticker.upper().strip()
    points = cache.get_history(symbol, limit=limit)
    if points is None:
        raise HTTPException(status_code=404, detail=f"Ticker '{symbol}' is not tracked")
    return {"ticker": symbol, "points": points}
```

```python
# app/main.py -- corrected mounting, module-level router objects, cache injected via app.state

from app.market.history import router as history_router
from app.market.stream import router as stream_router  # also revised to use Depends(get_price_cache)

app = FastAPI(lifespan=lifespan)
app.include_router(stream_router)
app.include_router(history_router)
```

This supersedes the `create_stream_router(price_cache)` / `create_history_router(price_cache)` factory-closure pattern shown in §9/§10 (which works, but only if router creation happens *after* `lifespan` has created the cache — awkward given FastAPI wants routers included at app-construction time). `Depends(get_price_cache)` reading from `request.app.state` cleanly decouples "when the router object is created" from "when the cache instance exists," and is the pattern the rest of the routes (portfolio, watchlist, chat) should follow too for consistency.

### `/api/health`

```python
@app.get("/api/health")
async def health(request: Request):
    market_source: MarketDataSource = request.app.state.market_source
    task = getattr(market_source, "_task", None)  # both concrete sources expose this
    market_ok = task is not None and not task.done()
    db_ok = await db_reachable()

    if market_ok and db_ok:
        return {"status": "ok"}
    return JSONResponse(
        status_code=503,
        content={"status": "degraded", "detail": "market data task not running" if not market_ok else "database unreachable"},
    )
```

Per `PLAN.md` §8: `200 {"status": "ok"}` when DB is reachable **and** the market-data background task is running, else `503 {"status": "degraded", "detail": ...}`.

---

## 13. Watchlist / Position Coordination

Not yet implemented (no watchlist route exists yet) — this section designs it, incorporating the reconciliation gap `REVIEW.md` identified: `PLAN.md` defines what happens when a ticker is removed from the watchlist while a position exists (feed stays pinned), but never defines the reverse — **closing the last shares of a ticker that was already removed from the watchlist**. Without an explicit rule, that ticker leaks indefinitely in the simulator/cache/SSE payload/Massive poll set.

### 13.1 The fix: one reconciliation function, called from every mutation site

Rather than scatter ad hoc `add_ticker`/`remove_ticker` calls across the watchlist route and the trade-execution path (and inevitably missing an edge case, which is exactly how the closed-position leak happened), define one idempotent function that computes the *target* tracked-ticker set and diffs it against reality:

```python
# app/watchlist.py

import asyncio

from app.market import MarketDataSource
from app.db import get_watchlist_tickers, get_position_tickers

_reconcile_lock = asyncio.Lock()  # serialize concurrent reconciliations


async def reconcile_tracked_tickers(market_source: MarketDataSource) -> None:
    """Make the market-data source's tracked set exactly watchlist ∪ open positions.

    Call this after ANY watchlist mutation (add/remove) and after ANY trade that
    opens or closes a position (a buy that creates a new position row, or a sell
    that empties one). Idempotent -- safe to call even when nothing changed.
    """
    async with _reconcile_lock:
        watchlist_tickers = set(await get_watchlist_tickers())
        position_tickers = set(await get_position_tickers())
        target = watchlist_tickers | position_tickers

        current = set(market_source.get_tickers())

        to_add = target - current
        to_remove = current - target

        for ticker in to_add:
            await market_source.add_ticker(ticker)
        for ticker in to_remove:
            await market_source.remove_ticker(ticker)
```

Call sites:

```python
# app/routes/watchlist.py

@router.post("/api/watchlist")
async def add_to_watchlist(body: AddTickerRequest, request: Request):
    ticker = validate_ticker_format(body.ticker)  # ^[A-Z]{1,5}$, 400 on failure
    await db_insert_watchlist_entry(ticker)         # idempotent -- 200 even if already present
    await reconcile_tracked_tickers(request.app.state.market_source)
    return {"ticker": ticker, "added_at": ..., "price": price_cache.get_price(ticker)}


@router.delete("/api/watchlist/{ticker}")
async def remove_from_watchlist(ticker: str, request: Request):
    await db_delete_watchlist_entry(ticker)
    # Reconciliation itself decides whether the feed should keep the ticker
    # (a position still holds it) or drop it -- the route doesn't need to know.
    await reconcile_tracked_tickers(request.app.state.market_source)
    return Response(status_code=204)
```

```python
# app/routes/portfolio.py -- inside the shared trade-execution function (PLAN.md §8)

async def execute_trade(ticker: str, side: str, quantity: float, market_source: MarketDataSource, price_cache: PriceCache) -> TradeResult:
    async with _trade_lock:  # process-level lock per PLAN.md §8
        ...  # validation, cash/position/trade updates as in PLAN.md §8
        await reconcile_tracked_tickers(market_source)
        return result
```

Calling `reconcile_tracked_tickers` after **every** trade (not just ones that open/close a position) is deliberately simple rather than optimized — computing "did this trade open or close a position" and only reconciling then would save a couple of cheap DB reads per trade, at the cost of a second code path that can drift out of sync with the first. Reconciliation is idempotent and cheap (two DB reads, a set diff, and typically zero `add_ticker`/`remove_ticker` calls when nothing actually changed), so calling it unconditionally after every mutation is the simpler, harder-to-get-wrong choice.

### 13.2 Serialization

The module-level `_reconcile_lock` prevents two concurrent reconciliations (e.g. a watchlist POST and a trade landing at nearly the same moment) from computing `target`/`current` against a stale view of each other's in-flight DB writes and issuing contradictory `add_ticker`/`remove_ticker` calls. This is separate from the trade-execution lock in `PLAN.md` §8 (which guards cash/position mutation, not ticker tracking) — `execute_trade` above acquires its own trade lock first, then calls `reconcile_tracked_tickers`, which acquires the reconcile lock; the two never nest in a way that could deadlock since reconciliation never calls back into trade execution.

### 13.3 Edge case walkthrough

| Scenario | `watchlist` | `positions` | Result |
|---|---|---|---|
| Ticker only ever watched, never traded | has it | — | tracked (from watchlist) |
| Ticker watched, then bought | has it | has it | tracked (both agree) |
| Watched ticker removed while a position remains | removed it | still has it | **stays tracked** — `PLAN.md` §8's existing rule |
| Position fully sold while still on the watchlist | has it | position row deleted (qty → 0) | **stays tracked** — watchlist still wants it |
| Position fully sold AND not on the watchlist | doesn't have it | position row deleted | **untracked** — this is the gap `REVIEW.md` found; reconciliation now drops it via `to_remove` |
| Ticker added via LLM `watchlist_changes` | has it | — | tracked (add flows through the same `POST /api/watchlist`-equivalent DB insert + reconcile) |

---

## 14. The "Not Yet Warmed" Contract

Restated here as the interface's binding contract (source: `PLAN.md` §6, extended with the `GET /api/history` row this document adds):

| Consumer | Behavior when `cache.get(ticker)` is `None` |
|---|---|
| `GET /api/watchlist` | `price: null` for that entry |
| Portfolio valuation | Position excluded from `total_value`; its `current_price`/P&L reported as `null` |
| Chat portfolio context | Ticker annotated `"price unavailable"` in the prompt |
| `GET /api/history` | Ticker never registered → `404`; registered but no points yet → `200` with `points: []` |
| Trade execution | Validation step 1 (`PLAN.md` §8) rejects the trade — a ticker with no warmed price can never be traded |
| Frontend | Renders `—` |

A ticker becomes "warmed" the instant either data source's `start()` or `add_ticker()` successfully calls `cache.update()` for it — both sources seed synchronously at add-time specifically to make this window as short as possible (§7.2, §8.2).

---

## 15. Testing Strategy

Builds on the existing 73-test suite (`MARKET_DATA_SUMMARY.md`) — this section covers only what's new or was flagged as a gap.

### 15.1 History ring buffer (new)

```python
# tests/market/test_cache.py -- additions

def test_get_history_returns_none_for_unknown_ticker():
    cache = PriceCache()
    assert cache.get_history("AAPL") is None

def test_get_history_returns_oldest_first():
    cache = PriceCache()
    for i, price in enumerate([100.0, 101.0, 102.0]):
        cache.update("AAPL", price, timestamp=float(i))
    points = cache.get_history("AAPL")
    assert [p["price"] for p in points] == [100.0, 101.0, 102.0]

def test_get_history_respects_limit():
    cache = PriceCache()
    for i in range(10):
        cache.update("AAPL", 100.0 + i, timestamp=float(i))
    points = cache.get_history("AAPL", limit=3)
    assert [p["price"] for p in points] == [107.0, 108.0, 109.0]

def test_history_evicts_oldest_past_capacity():
    cache = PriceCache()
    cache.HISTORY_CAPACITY = 5  # shrink for a fast test
    for i in range(10):
        cache.update("AAPL", float(i), timestamp=float(i))
    points = cache.get_history("AAPL")
    assert len(points) == 5
    assert points[0]["price"] == 5.0  # oldest 5 evicted

def test_remove_clears_history_too():
    cache = PriceCache()
    cache.update("AAPL", 100.0)
    cache.remove("AAPL")
    assert cache.get_history("AAPL") is None
```

### 15.2 `GET /api/history` route (new)

```python
# tests/market/test_history.py

from fastapi.testclient import TestClient

def test_history_404_for_untracked_ticker(client: TestClient):
    resp = client.get("/api/history?ticker=ZZZZ")
    assert resp.status_code == 404

def test_history_returns_points_oldest_first(client: TestClient, price_cache: PriceCache):
    for i, price in enumerate([190.0, 190.5, 191.0]):
        price_cache.update("AAPL", price, timestamp=float(i))
    resp = client.get("/api/history?ticker=AAPL")
    body = resp.json()
    assert body["ticker"] == "AAPL"
    assert [p["price"] for p in body["points"]] == [190.0, 190.5, 191.0]

def test_history_limit_capped_at_buffer_capacity(client: TestClient):
    resp = client.get(f"/api/history?ticker=AAPL&limit={PriceCache.HISTORY_CAPACITY + 100}")
    assert resp.status_code == 422  # FastAPI Query(le=...) validation rejects it

def test_history_lowercases_and_trims_ticker(client: TestClient, price_cache: PriceCache):
    price_cache.update("AAPL", 190.0)
    resp = client.get("/api/history?ticker=aapl")
    assert resp.json()["ticker"] == "AAPL"
```

### 15.3 `reconcile_tracked_tickers` (new)

```python
# tests/test_watchlist.py

async def test_reconcile_drops_ticker_with_no_watchlist_and_no_position(fake_market_source, fake_db):
    fake_db.watchlist = set()          # ticker removed from watchlist
    fake_db.positions = set()          # ...and position fully sold
    fake_market_source._tickers = {"AAPL"}  # still tracked from before

    await reconcile_tracked_tickers(fake_market_source)

    assert "AAPL" not in fake_market_source.get_tickers()

async def test_reconcile_keeps_ticker_with_open_position_only(fake_market_source, fake_db):
    fake_db.watchlist = set()
    fake_db.positions = {"AAPL"}       # still held, just unwatched
    fake_market_source._tickers = {"AAPL"}

    await reconcile_tracked_tickers(fake_market_source)

    assert "AAPL" in fake_market_source.get_tickers()

async def test_reconcile_adds_newly_watched_ticker(fake_market_source, fake_db):
    fake_db.watchlist = {"TSLA"}
    fake_market_source._tickers = set()

    await reconcile_tracked_tickers(fake_market_source)

    assert "TSLA" in fake_market_source.get_tickers()

async def test_reconcile_is_idempotent(fake_market_source, fake_db):
    fake_db.watchlist = {"AAPL"}
    fake_market_source._tickers = {"AAPL"}

    calls_before = fake_market_source.add_ticker.call_count + fake_market_source.remove_ticker.call_count
    await reconcile_tracked_tickers(fake_market_source)
    calls_after = fake_market_source.add_ticker.call_count + fake_market_source.remove_ticker.call_count

    assert calls_after == calls_before  # nothing changed -> no add/remove calls
```

### 15.4 SSE (gap flagged in `MARKET_DATA_REVIEW.md` §4.2 — currently 31% coverage, no dedicated tests)

```python
# tests/market/test_stream.py

import json
from fastapi.testclient import TestClient

def test_sse_sends_immediate_snapshot_on_connect(client: TestClient, price_cache: PriceCache):
    price_cache.update("AAPL", 190.0)
    with client.stream("GET", "/api/stream/prices") as resp:
        lines = []
        for line in resp.iter_lines():
            lines.append(line)
            if line.startswith("data:"):
                break
        payload = json.loads(lines[-1][len("data: "):])
        assert payload["AAPL"]["price"] == 190.0

def test_sse_sends_retry_directive_first(client: TestClient):
    with client.stream("GET", "/api/stream/prices") as resp:
        first_line = next(resp.iter_lines())
        assert first_line == "retry: 1000"

def test_sse_pushes_only_on_version_change(price_cache: PriceCache):
    # Unit-test _generate_events directly against a fake Request with a
    # controllable is_disconnected(), asserting the generator yields nothing
    # new between two polls where price_cache.version hasn't advanced.
    ...

def test_sse_sends_keepalive_comment_after_quiet_interval(price_cache: PriceCache):
    # Same approach, asserting a ": keepalive\n\n" line appears after
    # keepalive_interval elapses with no cache updates, and that no such
    # line appears before then.
    ...
```

### 15.5 Concurrency (gap flagged in `MARKET_DATA_REVIEW.md` §4.2)

```python
# tests/market/test_cache.py -- addition

def test_cache_survives_concurrent_writers():
    """Multiple threads writing simultaneously shouldn't corrupt state or crash."""
    import threading

    cache = PriceCache()
    tickers = [f"T{i}" for i in range(20)]

    def writer(ticker: str):
        for i in range(200):
            cache.update(ticker, float(i))

    threads = [threading.Thread(target=writer, args=(t,)) for t in tickers]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(cache) == 20
    for ticker in tickers:
        update = cache.get(ticker)
        assert update is not None
        assert update.price == 199.0  # last write for that ticker
```

### 15.6 Full-watchlist Cholesky (gap flagged in `MARKET_DATA_REVIEW.md` §4.2)

```python
# tests/market/test_simulator.py -- addition

def test_cholesky_succeeds_for_full_default_watchlist():
    from app.market.seed_prices import SEED_PRICES
    sim = GBMSimulator(tickers=list(SEED_PRICES.keys()))
    # Should not raise (np.linalg.cholesky raises LinAlgError on a non-PSD matrix)
    prices = sim.step()
    assert len(prices) == len(SEED_PRICES)
```

---

## 16. Configuration Summary

| Env var | Default | Effect |
|---|---|---|
| `MASSIVE_API_KEY` | unset | Unset/empty → `SimulatorDataSource`. Set → `MassiveDataSource`, polling every 15s (constructor default; not currently env-configurable, could be added as `MASSIVE_POLL_INTERVAL` if needed). |
| — | — | `PriceCache.HISTORY_CAPACITY` (300) and the simulator's `update_interval` (0.5s) / `event_probability` (0.001) are constructor defaults, not env vars — no product requirement to make them runtime-configurable. |

```python
# app/market/__init__.py public surface, for reference by the rest of the backend

from app.market import (
    PriceUpdate,               # dataclass: ticker, price, previous_price, timestamp (+ computed change/direction)
    PriceCache,                 # .update() .get() .get_all() .get_price() .get_history() .remove() .version
    MarketDataSource,           # ABC: start/stop/add_ticker/remove_ticker/get_tickers
    create_market_data_source,  # factory, reads MASSIVE_API_KEY
    create_stream_router,       # GET /api/stream/prices (SSE) -- or module-level `stream_router` w/ Depends, §12
    create_history_router,      # GET /api/history -- or module-level `history_router` w/ Depends, §12
)
```

---

## 17. Known Issues to Fix

Carried forward from `MARKET_DATA_REVIEW.md` and this document's own research, for whoever picks up implementation of the deltas:

| # | Issue | Severity | Fix |
|---|---|---|---|
| 1 | `massive_client.py` reads `snap.last_trade.timestamp` (doesn't exist) instead of `.sip_timestamp`, and divides by `1000` (ms) instead of `1_000_000_000` (ns) | **High** — breaks on first real API call | Apply §7.4's two-line fix |
| 2 | No history ring buffer / `GET /api/history` | High (blocks frontend sparklines/detail chart per `PLAN.md` §10) | Implement §4 + §10 |
| 3 | No `reconcile_tracked_tickers` — closing the last position in an unwatched ticker leaks it in the feed forever | Medium | Implement §13, wire into watchlist + trade routes |
| 4 | `PLAN.md`'s "DB lazily initializes on first request" vs. "market data starts from DB state on every boot" contradiction | Medium | §12 makes lifespan-driven startup authoritative |
| 5 | SSE keepalive comment was documented as feeding the frontend connection-status dot; `EventSource` cannot see comments | Medium | §9.3 corrects the contract — dot derives from `EventSource` state only |
| 6 | `PriceCache.version` read without the lock | Low | §4's snippet takes the lock |
| 7 | `_generate_events` was annotated `-> None` instead of `-> AsyncGenerator[str, None]` | Low | Already shown fixed in §9.1 |
| 8 | Docker volume docs describe both a named volume and a bind mount for the same path | Low, not market-data — flagged in `REVIEW.md`, out of scope for this document | Resolve in `PLAN.md`/Docker docs, not here |
