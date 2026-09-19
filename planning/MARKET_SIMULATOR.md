# Market Simulator Design

Approach and code structure for simulating realistic stock prices when no `MASSIVE_API_KEY` is configured — the default, recommended path for most users (`PLAN.md` §5–6). This is what actually runs for the demo/course experience, since even a free Massive tier only returns EOD/delayed data (`MASSIVE_API.md` §2) rather than a live tick stream.

**Status**: Implemented in `backend/app/market/simulator.py` and `backend/app/market/seed_prices.py`, with 17 unit tests (`test_simulator.py`) + 10 integration tests (`test_simulator_source.py`), per `MARKET_DATA_SUMMARY.md`. This document describes that implementation as the reference design.

## 1. Why GBM

The simulator uses **Geometric Brownian Motion (GBM)** — the standard stochastic process underlying Black-Scholes option pricing — to generate price paths. Three properties make it the right tool here:

- **Multiplicative, so prices can't go negative.** Each step multiplies the price by `exp(...)`, which is always positive, unlike an additive random walk that could push a price below zero given enough bad draws.
- **Lognormal returns**, matching the rough statistical shape of real short-horizon stock returns — small moves are common, large moves are rare but not impossible.
- **Parameterized by drift and volatility** (`mu`, `sigma`), so different tickers can behave differently (TSLA choppier than JPM) with two numbers per ticker, not a bespoke model each.

Updates run at **~500ms intervals**, producing a continuous, visually alive stream of price changes suitable for a dashboard that flashes on every tick.

## 2. GBM Math

At each time step, a price evolves as:

```
S(t+dt) = S(t) * exp((mu - sigma^2/2) * dt + sigma * sqrt(dt) * Z)
```

Where:
- `S(t)` — current price
- `mu` — annualized drift (expected return), e.g. `0.05` (5%/year)
- `sigma` — annualized volatility, e.g. `0.20` (20%/year)
- `dt` — time step as a fraction of a trading year
- `Z` — a (correlated, §3) standard normal random draw

`dt` is derived from real trading-calendar conventions so that `mu`/`sigma` keep their normal "annualized" meaning even though ticks happen every 500ms:

```python
TRADING_SECONDS_PER_YEAR = 252 * 6.5 * 3600   # 252 trading days * 6.5h/day = 5,896,800s
DEFAULT_DT = 0.5 / TRADING_SECONDS_PER_YEAR   # ≈ 8.48e-8
```

This tiny `dt` produces small, sub-cent-scale moves per tick that compound naturally into realistic-looking multi-minute price action — exactly what you want for a sparkline, without every single tick looking like a headline-driven spike.

## 3. Correlated Moves

Real stocks don't move independently — tech names tend to move together, sector peers track each other, and a handful of names (TSLA) mostly do their own thing. The simulator reproduces this with a **Cholesky decomposition** of a correlation matrix: given a valid (positive semi-definite) correlation matrix `C`, `L = cholesky(C)` satisfies `L @ Lᵀ = C`, so applying `L` to a vector of *independent* standard normals produces a vector of *correlated* standard normals with exactly the target correlation structure.

```python
z_independent = np.random.standard_normal(n)      # n independent draws, one per ticker
z_correlated = cholesky_matrix @ z_independent      # same n draws, now correlated
```

### Correlation structure

| Pair | Correlation | Rationale |
|---|---|---|
| Two tech-sector tickers | `0.6` | Tech names broadly move together (rate sensitivity, sentiment) |
| Two finance-sector tickers | `0.5` | Financials move together on rate/credit news |
| Either ticker is TSLA | `0.3` | TSLA is idiosyncratic — high-beta but not sector-locked |
| Cross-sector / unknown ticker involved | `0.3` | Baseline market-wide correlation |

```python
CORRELATION_GROUPS: dict[str, set[str]] = {
    "tech": {"AAPL", "GOOGL", "MSFT", "AMZN", "META", "NVDA", "NFLX"},
    "finance": {"JPM", "V"},
}
INTRA_TECH_CORR = 0.6
INTRA_FINANCE_CORR = 0.5
CROSS_GROUP_CORR = 0.3
TSLA_CORR = 0.3
```

Pairwise lookup checks TSLA first (it's nominally in the `tech` set by ticker but should not inherit the `0.6` intra-tech correlation), then same-group membership, then falls through to the `0.3` baseline:

```python
def _pairwise_correlation(t1: str, t2: str) -> float:
    if t1 == "TSLA" or t2 == "TSLA":
        return TSLA_CORR
    if t1 in CORRELATION_GROUPS["tech"] and t2 in CORRELATION_GROUPS["tech"]:
        return INTRA_TECH_CORR
    if t1 in CORRELATION_GROUPS["finance"] and t2 in CORRELATION_GROUPS["finance"]:
        return INTRA_FINANCE_CORR
    return CROSS_GROUP_CORR
```

Any ticker not in either named group (including tickers added dynamically at runtime, e.g. via chat) simply falls into the `0.3` baseline with everything else — no special-casing needed for unseeded tickers here.

## 4. Random Events

Every step, each ticker independently has a small chance of a sudden 2–5% jump — enough drama to make the dashboard feel alive without dominating normal price action.

```python
event_probability = 0.001   # ~0.1% chance per tick, per ticker

if random.random() < event_probability:
    shock_magnitude = random.uniform(0.02, 0.05)
    shock_sign = random.choice([-1, 1])
    price *= 1 + shock_magnitude * shock_sign
```

At `0.1%` per tick and 2 ticks/sec, a single ticker sees an event roughly every 500 seconds (~8 minutes); across a 10-ticker watchlist, expect a visible event somewhere roughly every ~50 seconds — frequent enough to be noticed, rare enough to still read as an event rather than noise.

## 5. Seed Prices & Per-Ticker Parameters

Realistic starting prices and per-ticker volatility/drift for the default watchlist, in `seed_prices.py`:

```python
SEED_PRICES: dict[str, float] = {
    "AAPL": 190.00, "GOOGL": 175.00, "MSFT": 420.00, "AMZN": 185.00, "TSLA": 250.00,
    "NVDA": 800.00, "META": 500.00,  "JPM": 195.00,  "V": 280.00,   "NFLX": 600.00,
}

TICKER_PARAMS: dict[str, dict[str, float]] = {
    "AAPL":  {"sigma": 0.22, "mu": 0.05},
    "GOOGL": {"sigma": 0.25, "mu": 0.05},
    "MSFT":  {"sigma": 0.20, "mu": 0.05},
    "AMZN":  {"sigma": 0.28, "mu": 0.05},
    "TSLA":  {"sigma": 0.50, "mu": 0.03},   # high volatility
    "NVDA":  {"sigma": 0.40, "mu": 0.08},   # high volatility, strong drift
    "META":  {"sigma": 0.30, "mu": 0.05},
    "JPM":   {"sigma": 0.18, "mu": 0.04},   # low volatility (bank)
    "V":     {"sigma": 0.17, "mu": 0.04},   # low volatility (payments)
    "NFLX":  {"sigma": 0.35, "mu": 0.05},
}

DEFAULT_PARAMS: dict[str, float] = {"sigma": 0.25, "mu": 0.05}
```

**Tickers added dynamically** (via `POST /api/watchlist` or an LLM `watchlist_changes` action, beyond the seeded 10 — see `PLAN.md` §6 "Ticker Validation & Dynamically Added Tickers") get:
- A random seed price in **$50–$300**: `random.uniform(50.0, 300.0)`
- `DEFAULT_PARAMS` (`sigma=0.25, mu=0.05`)
- The `0.3` cross-group correlation coefficient with everything else (§3 — no group membership needed, the fallback already handles it)

Format validation (`^[A-Z]{1,5}$`) happens one layer up, in the watchlist API route — the simulator itself accepts any string ticker it's given and doesn't validate the symbol; it just seeds a price for it. This split is deliberate (`PLAN.md` §6 "Implementation deltas"): validation is an API-layer concern, not a market-data concern.

## 6. `GBMSimulator` — Core Class

Pure, synchronous, no I/O — a stateful step function. This is what makes it trivially unit-testable (17 tests, 98% coverage per `MARKET_DATA_SUMMARY.md`) independent of asyncio scheduling.

```python
class GBMSimulator:
    """Geometric Brownian Motion simulator for correlated stock prices."""

    TRADING_SECONDS_PER_YEAR = 252 * 6.5 * 3600
    DEFAULT_DT = 0.5 / TRADING_SECONDS_PER_YEAR

    def __init__(self, tickers: list[str], dt: float = DEFAULT_DT, event_probability: float = 0.001) -> None:
        self._dt = dt
        self._event_prob = event_probability
        self._tickers: list[str] = []
        self._prices: dict[str, float] = {}
        self._params: dict[str, dict[str, float]] = {}
        self._cholesky: np.ndarray | None = None
        for ticker in tickers:
            self._add_ticker_internal(ticker)
        self._rebuild_cholesky()

    def step(self) -> dict[str, float]:
        """Advance all tickers by one time step. Hot path — called every 500ms."""
        n = len(self._tickers)
        if n == 0:
            return {}

        z_independent = np.random.standard_normal(n)
        z_correlated = self._cholesky @ z_independent if self._cholesky is not None else z_independent

        result: dict[str, float] = {}
        for i, ticker in enumerate(self._tickers):
            params = self._params[ticker]
            drift = (params["mu"] - 0.5 * params["sigma"] ** 2) * self._dt
            diffusion = params["sigma"] * math.sqrt(self._dt) * z_correlated[i]
            self._prices[ticker] *= math.exp(drift + diffusion)

            if random.random() < self._event_prob:
                shock = random.uniform(0.02, 0.05) * random.choice([-1, 1])
                self._prices[ticker] *= 1 + shock

            result[ticker] = round(self._prices[ticker], 2)
        return result

    def add_ticker(self, ticker: str) -> None:
        """Add a ticker mid-session. Rebuilds the correlation matrix."""
        if ticker in self._prices:
            return
        self._add_ticker_internal(ticker)
        self._rebuild_cholesky()

    def remove_ticker(self, ticker: str) -> None:
        if ticker not in self._prices:
            return
        self._tickers.remove(ticker)
        del self._prices[ticker]
        del self._params[ticker]
        self._rebuild_cholesky()

    def get_price(self, ticker: str) -> float | None:
        return self._prices.get(ticker)

    def get_tickers(self) -> list[str]:
        return list(self._tickers)

    def _add_ticker_internal(self, ticker: str) -> None:
        """Add without rebuilding Cholesky — for batch init in __init__."""
        if ticker in self._prices:
            return
        self._tickers.append(ticker)
        self._prices[ticker] = SEED_PRICES.get(ticker, random.uniform(50.0, 300.0))
        self._params[ticker] = TICKER_PARAMS.get(ticker, dict(DEFAULT_PARAMS))

    def _rebuild_cholesky(self) -> None:
        n = len(self._tickers)
        if n <= 1:
            self._cholesky = None
            return
        corr = np.eye(n)
        for i in range(n):
            for j in range(i + 1, n):
                rho = self._pairwise_correlation(self._tickers[i], self._tickers[j])
                corr[i, j] = corr[j, i] = rho
        self._cholesky = np.linalg.cholesky(corr)
```

Two `add_ticker` paths exist on purpose: `_add_ticker_internal` (no Cholesky rebuild) for constructing the initial batch in `__init__` — rebuilding after every single ticker during batch init would be wasted `O(n^2)` work repeated `n` times — versus the public `add_ticker` (rebuilds once) for a single ticker arriving mid-session from the watchlist API.

## 7. `SimulatorDataSource` — Async Wrapper

`GBMSimulator` itself knows nothing about asyncio, the price cache, or the `MarketDataSource` interface. `SimulatorDataSource` is the thin adapter that runs it on a timer and writes results into the shared `PriceCache` (`MARKET_INTERFACE.md` §4):

```python
class SimulatorDataSource(MarketDataSource):
    def __init__(self, price_cache: PriceCache, update_interval: float = 0.5, event_probability: float = 0.001) -> None:
        self._cache = price_cache
        self._interval = update_interval
        self._event_prob = event_probability
        self._sim: GBMSimulator | None = None
        self._task: asyncio.Task | None = None

    async def start(self, tickers: list[str]) -> None:
        self._sim = GBMSimulator(tickers=tickers, event_probability=self._event_prob)
        for ticker in tickers:
            price = self._sim.get_price(ticker)
            if price is not None:
                self._cache.update(ticker=ticker, price=price)  # seed immediately
        self._task = asyncio.create_task(self._run_loop(), name="simulator-loop")

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None

    async def add_ticker(self, ticker: str) -> None:
        if self._sim:
            self._sim.add_ticker(ticker)
            price = self._sim.get_price(ticker)
            if price is not None:
                self._cache.update(ticker=ticker, price=price)

    async def remove_ticker(self, ticker: str) -> None:
        if self._sim:
            self._sim.remove_ticker(ticker)
        self._cache.remove(ticker)

    def get_tickers(self) -> list[str]:
        return self._sim.get_tickers() if self._sim else []

    async def _run_loop(self) -> None:
        while True:
            try:
                if self._sim:
                    for ticker, price in self._sim.step().items():
                        self._cache.update(ticker=ticker, price=price)
            except Exception:
                logger.exception("Simulator step failed")
            await asyncio.sleep(self._interval)
```

Two deliberate robustness choices:
- **Seed-on-add.** Both `start()` and `add_ticker()` write an initial price into the cache synchronously, rather than waiting for the next 500ms tick. A newly added ticker is never "not warmed" for even one tick longer than necessary — important since `GET /api/watchlist` and `GET /api/history` should reflect it right away.
- **`_run_loop` never dies from a bad step.** The `try/except Exception` around `self._sim.step()` means one arithmetic edge case (extremely unlikely given GBM's structure, but e.g. a pathological correlation matrix on an unusual ticker mix) logs and skips a tick rather than silently killing the background task and freezing every price in the app.

## 8. File Structure

```
backend/
  app/
    market/
      simulator.py       # GBMSimulator (pure math/state) + SimulatorDataSource (async adapter)
      seed_prices.py      # SEED_PRICES, TICKER_PARAMS, DEFAULT_PARAMS, CORRELATION_GROUPS, correlation constants
```

Kept as two files rather than one: `seed_prices.py` is pure data (easy to tweak watchlist economics without touching logic), `simulator.py` is the class hierarchy. `GBMSimulator` and `SimulatorDataSource` share a file because they're small, tightly coupled (one exists to drive the other on a timer), and splitting them would mean two files that are never meaningfully used independently.

## 9. Behavior Notes

- **Prices never go negative** — GBM is multiplicative (`price *= exp(...)`), so the result of any finite step is always positive.
- **Sub-cent moves per tick, compounding over time.** The tiny `dt` (~8.5e-8) means no single tick looks unrealistic, but a minute of ticks (120 of them) produces a believable minute-scale price move.
- **`sigma=0.50` (TSLA)** over a simulated "day" (a few minutes of wall-clock time at demo speed, or a full 6.5 real trading hours if left running) produces roughly the right *intraday range* relative to its annualized volatility — this is the point of deriving `dt` from real trading-calendar seconds rather than picking an arbitrary tick size.
- **The correlation matrix must stay positive semi-definite** for `np.linalg.cholesky` to succeed — guaranteed here because correlations are built from a small fixed palette (`0.3`, `0.5`, `0.6`, symmetric, unit diagonal), which is a valid correlation structure by construction, not something that needs runtime validation.
- **Rebuilding Cholesky on ticker add/remove is `O(n²)`** (matrix build) `+ O(n³)` (decomposition), but `n` stays small (tens of tickers, not thousands) in any realistic FinAlly session, so this is not a hot-path concern — it only runs on `add_ticker`/`remove_ticker`, not on every `step()`.
- **Unseeded tickers behave identically to seeded ones** once added — same `step()` code path, same correlation lookup, just different starting numbers. There's no special "unknown ticker" branch inside `GBMSimulator.step()`.
