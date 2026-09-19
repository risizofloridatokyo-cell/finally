# Team Contracts — FinAlly platform build

Shared interfaces so the six teammates can work in parallel. `planning/PLAN.md` is the spec; this file only pins down
the seams between owners. If you need to change a seam, **message the affected teammate(s) first** and then update this file.

## Roster & ownership (each agent edits ONLY its own files)

| Name | Owns |
|---|---|
| `db-engineer` | `backend/app/db/**`, `backend/tests/db/**` |
| `backend-engineer` | `backend/app/main.py`, `backend/app/routes/**` (except chat), `backend/app/portfolio/**`, `backend/app/watchlist/**`, `backend/app/tasks.py`, `backend/app/config.py`, `backend/tests/api/**`, `backend/tests/portfolio/**`; the existing `backend/app/market/**` (only for the small deltas already in PLAN.md) |
| `llm-engineer` | `backend/app/llm/**` (incl. the `POST /api/chat` router), `backend/tests/llm/**` |
| `frontend-engineer` | `frontend/**` |
| `devops-engineer` | `Dockerfile`, `.dockerignore`, `scripts/**`, `.env.example`, `.gitignore`, `db/.gitkeep` |
| `integration-tester` | `test/**` (Playwright E2E + `test/docker-compose.test.yml`) |

Shared files: `backend/pyproject.toml` / `uv.lock` — `litellm`, `python-dotenv`, `httpx` (dev) are **already added**. Need another
dependency? Run `uv add` yourself, but only after checking nobody else is running uv (message `backend-engineer`). Do NOT
commit, push, branch or stash — the lead commits. Do not edit files you don't own; message the owner instead.

## Paths & env

- Code package is `backend/app/` (so DB code is `backend/app/db/`, not `backend/db/` as the PLAN tree loosely says).
- `DB_PATH` env → SQLite file; default `<repo>/db/finally.db` (Docker: `/app/db/finally.db`). Create parent dir if missing.
- `STATIC_DIR` env → static frontend dir; default `<repo>/backend/static`, falling back to `<repo>/frontend/out`. Served at `/`
  with `html=True` **after** all `/api` routes are registered. Missing dir must not crash startup (dev/test).
- `.env` at repo root loaded with python-dotenv (no override of real env vars). Env vars per PLAN §5.
- Run backend: `cd backend && uv run uvicorn app.main:app --port 8000`. App factory: `app.main:app`.
- Tests: `cd backend && uv run pytest`. Ruff clean (`uv run ruff check .`).
- Windows dev machine (Git Bash / PowerShell) — keep paths portable, use `pathlib`.

## DB layer — `app.db` (sync `sqlite3`, WAL, `busy_timeout`, foreign keys on)

Every function takes an open connection first; `user_id` is always `"default"` (module constant `DEFAULT_USER`).
Rows returned as plain `dict`s. Timestamps ISO-8601 UTC strings. Cash rounded to cents on every write.

```python
init_db(path: str | Path | None = None) -> None          # idempotent: create tables + seed (profile, 10 watchlist tickers)
get_conn() -> ContextManager[sqlite3.Connection]           # row_factory=Row; commit on clean exit, rollback on exception
                                                           # (uses DB_PATH); nesting-safe use: one conn per unit of work

get_profile(conn) -> {"cash_balance": float, "realized_pnl": float, "created_at": str}
update_profile(conn, *, cash_balance: float | None = None, realized_pnl: float | None = None) -> None

list_watchlist(conn) -> list[{"ticker","added_at"}]        # oldest first
add_watchlist(conn, ticker: str) -> bool                   # True if created, False if already present
remove_watchlist(conn, ticker: str) -> bool

list_positions(conn) -> list[{"ticker","quantity","avg_cost","updated_at"}]
get_position(conn, ticker: str) -> dict | None
upsert_position(conn, ticker: str, quantity: float, avg_cost: float) -> None
delete_position(conn, ticker: str) -> None

insert_trade(conn, ticker: str, side: str, quantity: float, price: float) -> dict   # returns the stored row
list_trades(conn, limit: int = 100) -> list[dict]                                   # newest first

insert_snapshot(conn, total_value: float, recorded_at: str | None = None) -> None
last_snapshot(conn) -> dict | None
list_snapshots(conn, since: str | None = None, limit: int | None = None) -> list[{"total_value","recorded_at"}]
    # oldest-first; since filters recorded_at >= since; with NEITHER param, downsample the full series to ~300 evenly-spaced points
    # (always keep first & last); with `limit`, return the most recent `limit` rows (oldest-first)
prune_snapshots(conn, older_than_days: int = 30) -> int

insert_chat_message(conn, role: str, content: str, actions: dict | None = None) -> dict
recent_chat_messages(conn, limit: int = 20) -> list[{"role","content","actions"(dict|None),"created_at"}]   # oldest-first
```

Additive helpers (landed): `get_conn(*, immediate=False)` — `immediate=True` runs `BEGIN IMMEDIATE`; **use it for trades** so the cash
read→write can't interleave. `check_db() -> bool` for `/api/health`; `get_db_path()`. `list_snapshots(since=...)` accepts `Z`/offset/naive
(naive = UTC) and raises `ValueError` on unparseable input → routes map to 400. Default watchlist is seeded only when the profile row is
first created (a removed ticker stays removed across restarts).

Business rules (avg-cost, realized P&L, validation, locking) live in `backend/app/portfolio/`, NOT in the DB layer. The DB layer
must make a whole trade atomic: the portfolio service does `with get_conn() as conn:` and calls several primitives inside it.

## Portfolio & watchlist services (backend-engineer) — imported by `llm-engineer`

```python
# app/portfolio/service.py
class TradeError(Exception):        # .message: str, .status_code: int (400 validation, 404 unknown/untracked ticker, 409 business rule)
def execute_trade(ticker: str, side: str, quantity: float) -> dict
    # THE single trade path (manual + LLM). Process-level threading.Lock. Validation order per PLAN §8. Returns
    # {"ticker","side","quantity","price","status":"executed"}; raises TradeError otherwise. Writes snapshot after success.
def get_portfolio() -> dict         # exactly the GET /api/portfolio body (PLAN §8); null-price rules per PLAN §6
def get_portfolio_context() -> dict # same data + watchlist w/ prices, for the LLM prompt (llm-engineer formats it)
# Position rows carry `unrealized_pnl` ($) and `unrealized_pnl_pct` (percent, 1.25 = 1.25%); frontend must use these exact keys.

# app/watchlist/service.py
class InvalidTicker(ValueError)
def normalize_ticker(raw: str) -> str      # strip+upper, must match ^[A-Z]{1,5}$ else raise InvalidTicker
def list_watchlist() -> list[dict]         # [{"ticker","added_at","price"|None}]
async def add_ticker(raw: str) -> bool     # ASYNC (market source is async). persists + source.add_ticker; idempotent
async def remove_ticker(raw: str) -> bool  # ASYNC. persists; drops from source+cache only if no position is held
```

Runtime singletons (price cache, market data source) are reachable via `app/state.py` (`get_cache()`, `get_source()`), set in the
`lifespan`. Services must work without FastAPI request context so the LLM router and tests can call them directly.

## LLM layer (llm-engineer)

```python
# app/llm/  →  router (APIRouter, prefix "/api") exposing POST /api/chat; main.py does `app.include_router(chat_router)`.
async def handle_chat(message: str) -> {"message": str, "actions": dict | None}
```
Response and `actions` shapes per PLAN §7/§9. Uses the `cerebras` skill (LiteLLM → OpenRouter, `openrouter/openai/gpt-oss-120b`,
Cerebras provider, structured outputs, 30 s timeout). Failure → `HTTPException(503, ...)` with the exact messages in PLAN §9 and
**nothing persisted**. Import services lazily inside functions or via module attribute access so tests can monkeypatch.

### `LLM_MOCK=true` deterministic triggers (case-insensitive substring on the user message, first match wins)

| Message contains | Mock returns |
|---|---|
| `oversized` | buy 1,000,000 × AAPL (fails cash validation → rejected, `errors[]` populated) |
| `buy` | buy 5 × AAPL |
| `sell` | sell 1 × AAPL |
| `add` | watchlist add `PYPL` |
| `remove` | watchlist remove `PYPL` |
| anything else | plain message, no trades/changes |

Mock `message` text must be stable and include the words "Mock:" and echo which action it took (tests assert on it).

## HTTP surface

Exactly PLAN §8. `backend-engineer` implements everything except `/api/chat`. `/api/stream/prices` comes from the existing
`app.market.create_stream_router`. Health per PLAN §8.

## Frontend `data-testid` contract (frontend-engineer implements, integration-tester relies on)

`{T}` = upper-case ticker.

| testid | Element |
|---|---|
| `connection-dot` | header dot; attribute `data-status="connected" \| "reconnecting" \| "disconnected"` |
| `header-total-value`, `header-cash`, `header-realized-pnl` | header figures (text is formatted currency, e.g. `$10,000.00`) |
| `watchlist-row-{T}` | one row per ticker |
| `watchlist-price-{T}` | price text (`—` when null); gets class `flash-up` / `flash-down` briefly on change |
| `watchlist-session-pct-{T}` | session change % text |
| `sparkline-{T}` | sparkline container; attribute `data-points` = number of points currently plotted |
| `watchlist-remove-{T}` | remove button |
| `watchlist-add-input`, `watchlist-add-button`, `watchlist-add-error` | add-ticker form |
| `main-chart` | detail chart; attributes `data-ticker`, `data-points` |
| `trade-ticker`, `trade-quantity`, `trade-buy`, `trade-sell`, `trade-error` | trade bar (+ inline error text) |
| `positions-table`, `position-row-{T}`, `position-qty-{T}`, `position-pnl-{T}` | positions table |
| `heatmap` | treemap container; each cell `heatmap-cell-{T}` with `data-pnl-sign="pos"\|"neg"\|"zero"` |
| `pnl-chart` | portfolio value chart; attribute `data-points` |
| `chat-panel`, `chat-toggle`, `chat-input`, `chat-send`, `chat-loading` | chat panel |
| `chat-message-user`, `chat-message-assistant` | one per message (repeat testid) |
| `chat-action-trade-executed`, `chat-action-trade-rejected`, `chat-action-watchlist`, `chat-action-error` | inline confirmations |

Colors/theme per PLAN §2 (dark, accent `#ecad0a`, blue `#209dd7`, purple `#753991` for submit buttons).

## Docker contract (devops-engineer)

- Multi-stage per PLAN §11; final image runs `uvicorn app.main:app --host 0.0.0.0 --port 8000` with `STATIC_DIR=/app/backend/static`
  (or wherever the frontend `out/` is copied; must match the `STATIC_DIR` env you set) and `DB_PATH=/app/db/finally.db`.
- Image name `finally`, container name `finally`, volume `finally-data`. Scripts idempotent (PLAN §11). `HEALTHCHECK` on `/api/health`.
- `test/docker-compose.test.yml` is owned by `integration-tester` and builds from devops's `Dockerfile`.

## Definition of done (all roles)

Own unit tests written and passing; ruff/eslint/tsc clean; no edits outside owned paths; a short final report listing files
created, how to run/test, and anything blocked or deviating from PLAN.md.
