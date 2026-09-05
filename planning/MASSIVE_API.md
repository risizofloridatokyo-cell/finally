# Massive API Reference (formerly Polygon.io)

Research notes and reference documentation for the Massive REST API, as used by FinAlly to fetch realtime and end-of-day (EOD) prices for multiple stock tickers. This document is the source of truth for what the API actually returns; `MARKET_INTERFACE.md` uses it to design the unified `MarketDataSource` implementation, and `backend/app/market/massive_client.py` is the existing code that consumes it (a correction to that code is flagged at the bottom — see "Implementation Note").

## 1. Overview & Rebrand

- Polygon.io rebranded to **Massive** (massive.com) on **October 30, 2025**. Existing Polygon API keys, accounts, and integrations continue to work unchanged.
- **Base URL**: `https://api.massive.com` (the legacy `https://api.polygon.io` host is still accepted by the client during the transition, but new code should use `api.massive.com`).
- **Python package**: `massive` on PyPI — this replaces the old `polygon-api-client` package name. Install with:
  ```bash
  pip install -U massive
  # or, in a uv project:
  uv add massive
  ```
- **Min Python version**: 3.9+
- **Source**: [github.com/massive-com/client-python](https://github.com/massive-com/client-python) (official SDK, MIT-style examples under `examples/rest/`)
- **Auth**: API key via the `MASSIVE_API_KEY` environment variable (read automatically) or passed explicitly to `RESTClient(api_key=...)`. Sent as `Authorization: Bearer <API_KEY>`.
- Note the happy coincidence: the SDK's own env var name (`MASSIVE_API_KEY`) is exactly the variable FinAlly's `.env` already defines (see `PLAN.md` §5) — no renaming needed.

## 2. Plans, Rate Limits & Data Freshness

This is the part most likely to bite a naive implementation: **the free tier is not real-time**, and "unlimited calls" does not imply real-time either.

| Tier | Price | Call limit | Data freshness | History |
|---|---|---|---|---|
| **Free** | $0/mo | 5 requests/minute | **End-of-day only** — snapshot/aggregate data, not live ticks | ~2 years |
| **Starter** | ~$29/mo | Unlimited | **15-minute delayed** | ~5 years |
| **Developer** | ~$79/mo | Unlimited | 15-minute delayed + trades data | ~10 years |
| **Advanced** | ~$199/mo | Unlimited | **Real-time** (first tier with true real-time US stock data) | 20+ years |

Implications for FinAlly:

- With no key (or a free-tier key), what we'd actually be polling is stale/EOD data, not a live tick stream — which is exactly why the simulator, not Massive, is the default and recommended path for most users (`PLAN.md` §5–6).
- `MASSIVE_API_KEY` being *set* only means "use the real API instead of the simulator" — it does not by itself guarantee real-time freshness. That depends on the plan behind the key. FinAlly doesn't need to detect the plan tier; it just polls on a fixed interval and displays whatever the API returns (§6 below), on the assumption that a user who provides a key has a plan whose freshness they're aware of.
- **Snapshot data resets at midnight ET** and repopulates as exchanges report new data starting around market pre-open. A poll shortly after midnight ET may return the previous session's numbers until fresh data arrives.

For FinAlly's polling cadence: **free tier → poll every 15s** (4 calls/min, safely under the 5/min cap); **paid tiers → poll every 2–15s** as budget/freshness needs dictate. This was already the design in `PLAN.md` §6 and remains correct.

## 3. Client Initialization

```python
from massive import RESTClient

# Reads MASSIVE_API_KEY from the environment automatically
client = RESTClient()

# Or pass explicitly
client = RESTClient(api_key="your_key_here")
```

`RESTClient` is **synchronous** (built on `urllib3`), so any use inside an `asyncio` event loop (as in FinAlly's background poller) must run it off-thread — e.g. `await asyncio.to_thread(client.get_snapshot_all, ...)`.

Built-in resilience (from the SDK's `base.py`):
- Retries automatically on HTTP `413, 429, 499, 500, 502, 503, 504` using `urllib3`'s `Retry`, backoff factor `0.1` (delays ≈ 0.0s, 0.2s, 0.4s, 0.8s, 1.6s, …).
- Raises `AuthError` at construction time if no API key is found (env var or constructor arg).
- Sends `Accept-Encoding: gzip` and a `User-Agent: Massive.com PythonClient/<version>` header.

## 4. Endpoints Used in FinAlly

### 4.1 Snapshot — All Tickers (primary endpoint)

Gets current prices for multiple tickers in **one API call** — this is the endpoint the poller uses every cycle.

**REST**: `GET /v2/snapshot/locale/us/markets/stocks/tickers?tickers=AAPL,GOOGL,MSFT&apiKey=...`

**Python client**:
```python
from massive import RESTClient
from massive.rest.models import TickerSnapshot

client = RESTClient()  # MASSIVE_API_KEY env var

tickers = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA"]

# market_type accepts a plain string ("stocks") or the SnapshotMarketType enum
snapshots = client.get_snapshot_all("stocks", tickers)

for snap in snapshots:
    if not isinstance(snap, TickerSnapshot):
        continue
    print(f"{snap.ticker}: ${snap.last_trade.price}")
    print(f"  Today's change: {snap.todays_change} ({snap.todays_change_percent}%)")
    if snap.prev_day:
        print(f"  Prev close: {snap.prev_day.close}")
    if snap.day:
        print(f"  Day OHLCV: O={snap.day.open} H={snap.day.high} L={snap.day.low} "
              f"C={snap.day.close} V={snap.day.volume}")
```

**Method signature** (from `massive/rest/snapshot.py`):
```python
def get_snapshot_all(
    self,
    market_type: str | SnapshotMarketType,   # e.g. "stocks"
    tickers: str | list[str] | None = None,  # omit/None = ALL ~10,000+ market tickers
    params: dict | None = None,
    raw: bool = False,
    include_otc: bool | None = False,
    options: RequestOptionBuilder | None = None,
) -> list[TickerSnapshot]:
    ...
```

⚠️ **Always pass `tickers` explicitly.** Omitting it fetches a full-market snapshot (10,000+ symbols) in one response — wasteful and slow for FinAlly's ~10–50 watched tickers, though it still only costs one API call against the rate limit.

**Response shape** — deserialized into `TickerSnapshot` objects (field names are the actual Python SDK attributes, snake_case; the raw JSON uses different short keys like `T`, `d`, `lastTrade` which the SDK maps for you):

```python
@dataclass
class TickerSnapshot:
    ticker: str | None
    day: Agg | None                    # today's running OHLCV bar
    prev_day: Agg | None               # yesterday's full OHLCV bar
    min: MinuteSnapshot | None         # most recent minute bar
    last_trade: LastTrade | None
    last_quote: LastQuote | None
    todays_change: float | None        # absolute change vs. prev close
    todays_change_percent: float | None
    updated: int | None                # nanosecond epoch of last update
    fair_market_value: float | None    # Business-plan only

@dataclass
class Agg:                             # day / prev_day / min
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: float | None
    vwap: float | None
    timestamp: int | None              # **milliseconds** since epoch (bar start)
    transactions: int | None
    otc: bool | None

@dataclass
class LastTrade:
    ticker: str | None
    price: float | None
    size: float | None
    exchange: int | None
    conditions: list[int] | None
    id: str | None
    tape: int | None
    correction: int | None
    sip_timestamp: int | None          # **nanoseconds** since epoch — NOT `.timestamp`
    participant_timestamp: int | None
    trf_timestamp: int | None
    trf_id: int | None
    sequence_number: float | None
    fractional_size: str | None

@dataclass
class LastQuote:
    ticker: str | None
    bid_price: float | None
    bid_size: int | None
    bid_exchange: int | None
    ask_price: float | None
    ask_size: int | None
    ask_exchange: int | None
    sip_timestamp: int | None          # nanoseconds since epoch
    participant_timestamp: int | None
    trf_timestamp: int | None
    tape: int | None
    conditions: list[int] | None
    indicators: list[int] | None
```

**Fields we actually need for FinAlly**:
- `snap.ticker` — which ticker this is
- `snap.last_trade.price` — the number we display and trade against
- `snap.last_trade.sip_timestamp` — when that trade happened (nanoseconds — divide by `1e9` for Unix seconds, not `1000`)
- `snap.todays_change_percent` — convenient ready-made "session %" if we ever want the API's own notion of daily change (FinAlly instead computes its own "Session %" client-side per `PLAN.md` §10, so this is informational only)

An invalid/unrecognized ticker in the `tickers` list is simply **absent** from the returned list — the endpoint doesn't error per-symbol, it just omits it. This is what "not warmed" detection is built on (§6 below and `PLAN.md` §6).

### 4.2 Single Ticker Snapshot

For a detailed view of one ticker (not currently used by FinAlly's poller, which always fetches the whole watchlist in one call, but useful for ad hoc lookups):

```python
snapshot = client.get_snapshot_ticker(market_type="stocks", ticker="AAPL")
print(f"Price: ${snapshot.last_trade.price}")
print(f"Bid/Ask: ${snapshot.last_quote.bid_price} / ${snapshot.last_quote.ask_price}")
if snapshot.day:
    print(f"Day range: ${snapshot.day.low} - ${snapshot.day.high}")
```

### 4.3 Previous Close

Previous full trading day's OHLC for a ticker. Useful for seeding a "prior close" baseline if FinAlly ever needs a real daily-change baseline instead of the session-since-load baseline it currently uses.

**REST**: `GET /v2/aggs/ticker/{ticker}/prev`

```python
from massive import RESTClient

client = RESTClient()
aggs = client.get_previous_close_agg("AAPL")

for agg in aggs:
    print(f"Previous close: ${agg.close}")
    print(f"OHLC: O={agg.open} H={agg.high} L={agg.low} C={agg.close}")
    print(f"Volume: {agg.volume}")
```

**Raw response**:
```json
{
  "ticker": "AAPL",
  "results": [
    {"o": 150.0, "h": 155.0, "l": 149.0, "c": 154.5, "v": 1000000, "t": 1672531200000}
  ]
}
```
(`t` is milliseconds since epoch, marking the start of the trading day.)

### 4.4 Aggregates (Bars) — EOD / historical

Historical OHLCV bars over a date range. Not needed for the live poll loop, but this is how FinAlly (or a future feature) would pull real end-of-day history for a ticker, e.g. to seed a chart with actual market history instead of the simulator's synthetic one.

**REST**: `GET /v2/aggs/ticker/{ticker}/range/{multiplier}/{timespan}/{from}/{to}`

```python
aggs = []
for a in client.list_aggs(
    "AAPL",
    1,
    "day",              # timespan: "minute" | "hour" | "day" | "week" | "month" | ...
    "2026-01-01",
    "2026-06-30",
    limit=50000,
):
    aggs.append(a)

for a in aggs:
    print(f"t={a.timestamp} O={a.open} H={a.high} L={a.low} C={a.close} V={a.volume}")
```

`list_aggs` paginates automatically — iterating the generator fetches subsequent pages as needed, so a large date range is safe to iterate without manual cursor handling.

### 4.5 Last Trade / Last Quote (single symbol)

Not used by the poller (the snapshot endpoint already includes both), but available for targeted lookups:

```python
trade = client.get_last_trade(ticker="AAPL")
print(f"Last trade: ${trade.price} x {trade.size}")

quote = client.get_last_quote(ticker="AAPL")
print(f"Bid: ${quote.bid_price} x {quote.bid_size}")
print(f"Ask: ${quote.ask_price} x {quote.ask_size}")
```

## 5. How FinAlly Polls Massive

The Massive poller runs as an asyncio background task, one snapshot call per cycle for the full watchlist ∪ position ticker set:

```python
import asyncio
from massive import RESTClient

async def poll_massive(api_key: str, get_tickers, price_cache, interval: float = 15.0):
    """Poll Massive's all-tickers snapshot and update the shared price cache."""
    client = RESTClient(api_key=api_key)

    while True:
        tickers = get_tickers()
        if tickers:
            snapshots = await asyncio.to_thread(
                client.get_snapshot_all, "stocks", tickers,
            )
            for snap in snapshots:
                if snap.last_trade is None or snap.last_trade.price is None:
                    continue  # ticker returned but has no trade yet — treat as not warmed
                price_cache.update(
                    ticker=snap.ticker,
                    price=snap.last_trade.price,
                    timestamp=(snap.last_trade.sip_timestamp or 0) / 1_000_000_000,
                )

        await asyncio.sleep(interval)
```

Steps:
1. Collect the current ticker set (watchlist ∪ held positions — see `PLAN.md` §6 Startup Sequence).
2. Call `get_snapshot_all("stocks", tickers)` — **one** API call regardless of ticker count.
3. For each returned snapshot with a usable `last_trade`, write `(ticker, price, timestamp)` into the shared `PriceCache`.
4. A ticker that isn't in the response, or whose `last_trade` is `None`, is left un-warmed for this cycle — it simply isn't updated (see "not warmed" behavior in `MARKET_INTERFACE.md` and `PLAN.md` §6).
5. Sleep for the poll interval, repeat.

## 6. Error Handling

| Condition | Behavior |
|---|---|
| **401** | Invalid/missing API key → `AuthError` (or an HTTP exception from the client, depending on SDK version) |
| **403** | Plan doesn't include the requested endpoint/tier of data |
| **429** | Rate limit exceeded (free tier: 5 req/min) — the client auto-retries a few times with backoff before surfacing an error |
| **5xx** | Server error — client auto-retries (`413, 429, 499, 500, 502, 503, 504`, backoff factor `0.1`) |
| Unknown/invalid ticker in a snapshot request | No error — the ticker is silently absent from the result list |
| Network failure | Standard `urllib3`/`requests`-style exception; FinAlly's poller should catch broadly and just skip the cycle (see `MARKET_INTERFACE.md` §5) |

FinAlly's poller wraps each poll cycle in a broad `try/except` so a single failed cycle (rate limit, transient network error, auth issue) logs and retries on the next interval rather than crashing the background task.

## 7. Notes & Gotchas

- **The snapshot-all endpoint is the key to staying within the free tier's rate limit.** One call covers the entire watchlist regardless of ticker count — this is why FinAlly polls this endpoint instead of calling per-ticker endpoints in a loop.
- **Timestamp units are inconsistent across the SDK** — a real footgun:
  - `Agg.timestamp` (from `day`, `prev_day`, aggregates/bars) — **milliseconds** since epoch.
  - `LastTrade.sip_timestamp` / `LastQuote.sip_timestamp` / `TickerSnapshot.updated` — **nanoseconds** since epoch.
  - Always divide nanosecond fields by `1_000_000_000` (not `1_000`) to get Unix seconds for `PriceCache`/`PriceUpdate`, which store Unix seconds throughout (per `MARKET_INTERFACE.md`).
- **`LastTrade` has no plain `.timestamp` attribute** — only `sip_timestamp`, `participant_timestamp`, and `trf_timestamp`. Code that reads `snap.last_trade.timestamp` will raise `AttributeError` against the real SDK.
- Snapshot data resets at midnight ET and repopulates through pre-market/market open — a poll immediately after midnight may return stale numbers for a few minutes.
- During market-closed hours, `last_trade.price` reflects the last traded price (which may be an after-hours print, not the closing auction price).
- `snap.day` may be `None` outside of a session with any trading activity yet (e.g., pre-market on a symbol with no pre-market prints) — always null-check before reading nested fields, matching the "not warmed" contract FinAlly uses everywhere else.

## 8. Implementation Note — correction needed in `massive_client.py`

The existing `backend/app/market/massive_client.py` (already implemented, per `MARKET_DATA_SUMMARY.md`) reads:

```python
price = snap.last_trade.price
timestamp = snap.last_trade.timestamp / 1000.0   # ms -> seconds
```

Per the real SDK models above, `LastTrade` has no `.timestamp` attribute — this should be `snap.last_trade.sip_timestamp`, and since that field is **nanoseconds**, the conversion should divide by `1_000_000_000`, not `1_000`. The existing test suite mocks the snapshot objects itself (`test_massive.py`), which is presumably why this wasn't caught — the mock likely defines a `.timestamp` attribute that doesn't exist on the real `LastTrade` class. This is a small, contained fix (two lines in `_poll_once`) worth making before ever running against a real `MASSIVE_API_KEY`; it does not affect simulator-only usage.
