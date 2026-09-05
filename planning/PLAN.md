# FinAlly — AI Trading Workstation

## Project Specification

## 1. Vision

FinAlly (Finance Ally) is a visually stunning AI-powered trading workstation that streams live market data, lets users trade a simulated portfolio, and integrates an LLM chat assistant that can analyze positions and execute trades on the user's behalf. It looks and feels like a modern Bloomberg terminal with an AI copilot.

This is the capstone project for an agentic AI coding course. It is built entirely by Coding Agents demonstrating how orchestrated AI agents can produce a production-quality full-stack application. Agents interact through files in `planning/`.

## 2. User Experience

### First Launch

The user runs a single Docker command (or a provided start script). A browser opens to `http://localhost:8000`. No login, no signup. They immediately see:

- A watchlist of 10 default tickers with live-updating prices in a grid
- $10,000 in virtual cash
- A dark, data-rich trading terminal aesthetic
- An AI chat panel ready to assist

### What the User Can Do

- **Watch prices stream** — prices flash green (uptick) or red (downtick) with subtle CSS animations that fade
- **View sparkline mini-charts** — price action beside each ticker in the watchlist, backfilled from `GET /api/history` on load and then extended live from the SSE stream
- **Click a ticker** to see a larger detailed chart in the main chart area (seeded from `GET /api/history`, then appended from SSE)
- **Buy and sell shares** — market orders only, instant fill at current price, no fees, no confirmation dialog
- **Monitor their portfolio** — a heatmap (treemap) showing positions sized by weight and colored by P&L, a P&L chart tracking total portfolio value over time, and a running cumulative **realized P&L** figure
- **View a positions table** — ticker, quantity, average cost, current price, unrealized P&L ($), and unrealized P&L % (vs. avg cost)
- **Chat with the AI assistant** — ask about their portfolio, get analysis, and have the AI execute trades and manage the watchlist through natural language
- **Manage the watchlist** — add/remove tickers manually or via the AI chat

### Visual Design

- **Dark theme**: backgrounds around `#0d1117` or `#1a1a2e`, muted gray borders, no pure black
- **Price flash animations**: brief green/red background highlight on price change, fading over ~500ms via CSS transitions
- **Connection status indicator**: a small colored dot (green = connected, yellow = reconnecting, red = disconnected) visible in the header
- **Professional, data-dense layout**: inspired by Bloomberg/trading terminals — every pixel earns its place
- **Responsive but desktop-first**: optimized for wide screens, functional on tablet

### Color Scheme
- Accent Yellow: `#ecad0a`
- Blue Primary: `#209dd7`
- Purple Secondary: `#753991` (submit buttons)

## 3. Architecture Overview

### Single Container, Single Port

```
┌─────────────────────────────────────────────────┐
│  Docker Container (port 8000)                   │
│                                                 │
│  FastAPI (Python/uv)                            │
│  ├── /api/*          REST endpoints             │
│  ├── /api/stream/*   SSE streaming              │
│  └── /*              Static file serving         │
│                      (Next.js export)            │
│                                                 │
│  SQLite database (volume-mounted)               │
│  Background task: market data polling/sim        │
└─────────────────────────────────────────────────┘
```

- **Frontend**: Next.js with TypeScript, built as a static export (`output: 'export'`), served by FastAPI as static files
- **Backend**: FastAPI (Python), managed as a `uv` project
- **Database**: SQLite, single file at `db/finally.db`, volume-mounted for persistence
- **Real-time data**: Server-Sent Events (SSE) — simpler than WebSockets, one-way server→client push, works everywhere
- **AI integration**: LiteLLM → OpenRouter (Cerebras for fast inference), with structured outputs for trade execution
- **Market data**: Environment-variable driven — simulator by default, real data via Massive API if key provided

### Why These Choices

| Decision | Rationale |
|---|---|
| SSE over WebSockets | One-way push is all we need; simpler, no bidirectional complexity, universal browser support |
| Static Next.js export | Single origin, no CORS issues, one port, one container, simple deployment |
| SQLite over Postgres | No auth = no multi-user = no need for a database server; self-contained, zero config |
| Single Docker container | Students run one command; no docker-compose for production, no service orchestration |
| uv for Python | Fast, modern Python project management; reproducible lockfile; what students should learn |
| Market orders only | Eliminates order book, limit order logic, partial fills — dramatically simpler portfolio math |

---

## 4. Directory Structure

```
finally/
├── frontend/                 # Next.js TypeScript project (static export)
├── backend/                  # FastAPI uv project (Python)
│   └── db/                   # Schema definitions, seed data, migration logic
├── planning/                 # Project-wide documentation for agents
│   ├── PLAN.md               # This document
│   └── ...                   # Additional agent reference docs
├── scripts/
│   ├── start_mac.sh          # Launch Docker container (macOS/Linux)
│   ├── stop_mac.sh           # Stop Docker container (macOS/Linux)
│   ├── start_windows.ps1     # Launch Docker container (Windows PowerShell)
│   └── stop_windows.ps1      # Stop Docker container (Windows PowerShell)
├── test/                     # Playwright E2E tests + docker-compose.test.yml
├── db/                       # Volume mount target (SQLite file lives here at runtime)
│   └── .gitkeep              # Directory exists in repo; finally.db is gitignored
├── Dockerfile                # Multi-stage build (Node → Python)
├── .env                      # Environment variables (gitignored, .env.example committed)
└── .gitignore
```

### Key Boundaries

- **`frontend/`** is a self-contained Next.js project. It knows nothing about Python. It talks to the backend via `/api/*` endpoints and `/api/stream/*` SSE endpoints. Internal structure is up to the Frontend Engineer agent.
- **`backend/`** is a self-contained uv project with its own `pyproject.toml`. It owns all server logic including database initialization, schema, seed data, API routes, SSE streaming, market data, and LLM integration. Internal structure is up to the Backend/Market Data agents.
- **`backend/db/`** contains schema SQL definitions and seed logic. The backend lazily initializes the database on first request — creating tables and seeding default data if the SQLite file doesn't exist or is empty.
- **`db/`** at the top level is the runtime volume mount point. The SQLite file (`db/finally.db`) is created here by the backend and persists across container restarts via Docker volume.
- **`planning/`** contains project-wide documentation, including this plan. All agents reference files here as the shared contract.
- **`test/`** contains Playwright E2E tests and supporting infrastructure (e.g., `docker-compose.test.yml`). Unit tests live within `frontend/` and `backend/` respectively, following each framework's conventions.
- **`scripts/`** contains start/stop scripts that wrap Docker commands.

---

## 5. Environment Variables

```bash
# Required: OpenRouter API key for LLM chat functionality
OPENROUTER_API_KEY=your-openrouter-api-key-here

# Optional: Massive (Polygon.io) API key for real market data
# If not set, the built-in market simulator is used (recommended for most users)
MASSIVE_API_KEY=

# Optional: Set to "true" for deterministic mock LLM responses (testing)
LLM_MOCK=false
```

### Behavior

- If `MASSIVE_API_KEY` is set and non-empty → backend uses Massive REST API for market data
- If `MASSIVE_API_KEY` is absent or empty → backend uses the built-in market simulator
- If `LLM_MOCK=true` → backend returns deterministic mock LLM responses (for E2E tests)
- The backend reads `.env` from the project root (mounted into the container or read via docker `--env-file`)

---

## 6. Market Data

### Two Implementations, One Interface

Both the simulator and the Massive client implement the same abstract interface. The backend selects which to use based on the environment variable. All downstream code (SSE streaming, price cache, frontend) is agnostic to the source.

### Simulator (Default)

- Generates prices using geometric Brownian motion (GBM) with configurable drift and volatility per ticker
- Updates at ~500ms intervals
- Correlated moves across tickers (e.g., tech stocks move together)
- Occasional random "events" — sudden 2-5% moves on a ticker for drama
- Starts from realistic seed prices (e.g., AAPL ~$190, GOOGL ~$175, etc.)
- Runs as an in-process background task — no external dependencies

### Massive API (Optional)

- REST API polling (not WebSocket) — simpler, works on all tiers
- Polls **all** watched tickers in a **single** API call per cycle (`get_snapshot_all` — one request regardless of ticker count), then writes each result to the cache
- Free tier (5 calls/min): poll every 15 seconds (4 calls/min)
- Paid tiers: poll every 2-15 seconds depending on tier
- Parses REST response into the same format as the simulator
- An invalid/unknown symbol simply yields no data (no cache entry); the ticker stays "not warmed" until removed

### Ticker Validation & Dynamically Added Tickers

`POST /api/watchlist` and LLM `watchlist_changes` accept tickers beyond the seeded 10. Rules:

- **Format validation (API layer):** 1–5 uppercase letters (`^[A-Z]{1,5}$`), after upper-casing and trimming. Anything else → `400 {"detail": "Invalid ticker symbol"}`.
- **Simulator:** an accepted-but-unseeded ticker is assigned a random seed price in `$50–$300`, default GBM params (`sigma=0.25, mu=0.05`), and the cross-sector correlation coefficient (`0.3`). *(Already implemented in `seed_prices.py` / `simulator.py`.)*
- **Massive:** the ticker is added to the poll set; if the API returns nothing for it after one poll cycle it is treated as "not warmed" (see below). No hard validation against a symbol master list.

### Shared Price Cache

- A single background task (simulator or Massive poller) writes to an in-memory price cache
- The cache holds the latest price, previous price, and timestamp for each ticker
- The cache also keeps a **bounded ring buffer** of recent points per ticker (last ~300 ≈ 2.5 min at 500ms ticks), exposed via `GET /api/history` for sparkline / detail-chart backfill. Bounded size → no unbounded growth in long-lived processes.
- SSE streams read from this cache and push updates to connected clients
- This architecture supports future multi-user scenarios without changes to the data layer

#### "Price not yet warmed" behavior

Before the first tick for a ticker, `cache.get()` returns `None`. Every consumer has a defined fallback:

- `GET /api/watchlist` → `price: null` for that ticker
- Portfolio valuation → the position is excluded from `total_value` and its `current_price` / P&L are reported as `null`
- Chat portfolio context → the ticker is annotated "price unavailable"
- Frontend → shows `—`

### SSE Streaming

- Endpoint: `GET /api/stream/prices`
- Long-lived SSE connection; client uses native `EventSource` API
- The server checks an in-memory version counter every ~500ms and pushes **only when a price changed** since the last push. Each push is a **single** `data:` event whose JSON payload is an object keyed by ticker — all tracked tickers in one event, not one event per ticker:
  ```
  data: {"AAPL": {"ticker":"AAPL","price":190.50,"previous_price":190.48,"timestamp":...,"change":0.02,"change_percent":0.01,"direction":"up"}, ...}
  ```
- `previous_price` is tick-to-tick (the immediately preceding cached price); `direction` is `"up" | "down" | "flat"`. These let the first post-connect event flash correctly.
- On connect the server emits an immediate full snapshot so a new client paints without waiting for the next change.
- The server sends a `: keepalive` comment every ~15s so a quiet stream is not mistaken for dead, and the client can tell "connected but quiet" from "stalled". **(Implementation delta — not yet in `stream.py`.)**
- A `retry: 1000` directive is sent once on connect; `EventSource` handles reconnection automatically.

### Startup Sequence

On every boot (fresh or with a persisted volume), in order:

1. Initialize the DB — create tables and seed default data only if missing/empty.
2. Read the **current** watchlist and positions from the DB.
3. Start the market-data source with the **union of watchlist tickers and position tickers** — never the hardcoded default 10 (the user may have edited the watchlist in a prior run).
4. Start the background tasks (portfolio snapshotter, snapshot retention).

Position tickers stay in the market-data set even when absent from the watchlist, so held positions can always be valued (see §8, `DELETE /api/watchlist/{ticker}`).

### Implementation deltas (completed market-data code)

The market-data subsystem is built and tested; these small additions remain for the platform build:

- **History ring buffer + `GET /api/history`** — add to the cache layer.
- **SSE keepalive comment** (~15s) in `stream.py`.
- **Ticker format validation** — lives in the new watchlist API route, not the market module.

---

## 7. Database

### SQLite with Lazy Initialization

The backend checks for the SQLite database on startup (or first request). If the file doesn't exist or tables are missing, it creates the schema and seeds default data. This means:

- No separate migration step
- No manual database setup
- Fresh Docker volumes start with a clean, seeded database automatically

### Schema

All tables include a `user_id` column defaulting to `"default"`. This is hardcoded for now (single-user) but enables future multi-user support without schema migration.

All timestamp columns store ISO-8601 **UTC** strings (`datetime.now(timezone.utc).isoformat()`). The frontend converts to local time for display.

**users_profile** — User state (cash balance, realized P&L)
- `id` TEXT PRIMARY KEY (default: `"default"`)
- `cash_balance` REAL (default: `10000.0`) — rounded to cents on every write to bound float drift
- `realized_pnl` REAL (default: `0.0`) — cumulative realized gain/loss, avg-cost basis; on each sell, increased by `(fill_price - avg_cost) * sell_qty`
- `created_at` TEXT (ISO-8601 UTC timestamp)

**watchlist** — Tickers the user is watching
- `id` TEXT PRIMARY KEY (UUID)
- `user_id` TEXT (default: `"default"`)
- `ticker` TEXT
- `added_at` TEXT (ISO-8601 UTC timestamp)
- UNIQUE constraint on `(user_id, ticker)`

**positions** — Current holdings (one row per ticker per user)
- `id` TEXT PRIMARY KEY (UUID)
- `user_id` TEXT (default: `"default"`)
- `ticker` TEXT
- `quantity` REAL (fractional shares supported)
- `avg_cost` REAL
- `updated_at` TEXT (ISO-8601 UTC timestamp)
- UNIQUE constraint on `(user_id, ticker)`
- **`avg_cost` maintenance:** buy → weighted average `((old_qty*old_cost) + (buy_qty*fill_price)) / (old_qty + buy_qty)`; sell → `avg_cost` unchanged, `quantity` reduced
- **Closing a position:** when `quantity` falls within `1e-6` of zero, delete the row (no zero/dust rows)

**trades** — Trade history (append-only log)
- `id` TEXT PRIMARY KEY (UUID)
- `user_id` TEXT (default: `"default"`)
- `ticker` TEXT
- `side` TEXT (`"buy"` or `"sell"`)
- `quantity` REAL (fractional shares supported)
- `price` REAL
- `executed_at` TEXT (ISO-8601 UTC timestamp)

**portfolio_snapshots** — Portfolio value over time (for P&L chart). Recorded by a background task every **60 seconds**, and immediately after each trade execution. The timed task skips a snapshot when `total_value` moved less than **0.1%** since the last one (adaptive — keeps the table small during quiet periods).
- `id` TEXT PRIMARY KEY (UUID)
- `user_id` TEXT (default: `"default"`)
- `total_value` REAL
- `recorded_at` TEXT (ISO-8601 UTC timestamp)
- **Retention:** a task on startup + daily deletes rows older than 30 days. `GET /api/portfolio/history` downsamples to ~300 points (see §8).
- Consumers must tolerate two rows with near-identical timestamps (an on-trade snapshot landing ~ms after a timed one).

**chat_messages** — Conversation history with LLM
- `id` TEXT PRIMARY KEY (UUID)
- `user_id` TEXT (default: `"default"`)
- `role` TEXT (`"user"` or `"assistant"`)
- `content` TEXT
- `actions` TEXT (JSON; `null` for user messages and for assistant messages that executed nothing)
- `created_at` TEXT (ISO-8601 UTC timestamp)

`actions` JSON shape (rendered as inline confirmations by the frontend):

```json
{
  "trades": [{"ticker": "AAPL", "side": "buy", "quantity": 10, "price": 190.12, "status": "executed"}],
  "watchlist_changes": [{"ticker": "PYPL", "action": "add", "status": "executed"}],
  "errors": ["Insufficient cash for TSLA buy"]
}
```

`status` is `"executed"` or `"rejected"`. `errors` holds human-readable strings for anything that failed validation.

### Default Seed Data

- One user profile: `id="default"`, `cash_balance=10000.0`, `realized_pnl=0.0`
- Ten watchlist entries: AAPL, GOOGL, MSFT, AMZN, TSLA, NVDA, META, JPM, V, NFLX

---

## 8. API Endpoints

### Market Data
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/stream/prices` | SSE stream of live price updates |
| GET | `/api/history?ticker=SYM&limit=N` | Recent price points for one ticker from the in-memory ring buffer (sparkline / detail-chart backfill). `limit` optional (default 300, capped at buffer size). Returns `{"ticker": "SYM", "points": [{"price": 190.1, "timestamp": ...}, ...]}` oldest-first. `404` if the ticker is not tracked. |

### Portfolio
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/portfolio` | Cash balance, cumulative `realized_pnl`, `positions[]` (each: qty, avg cost, current price, unrealized P&L $, unrealized P&L %), `total_value`, `total_unrealized_pnl`. A position whose price is not warmed reports `current_price: null` and is excluded from `total_value`. |
| POST | `/api/portfolio/trade` | Execute a market order: `{ticker, quantity, side}`. Instant fill at the current cached price. Validation + locking per "Trade Execution" below. |
| GET | `/api/portfolio/history?since=<iso>&limit=<n>` | Portfolio value snapshots for the P&L chart. Both params optional; `since` filters by `recorded_at`, `limit` caps the count. With neither, the server downsamples the full series to ~300 evenly-spaced points. |

### Watchlist
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/watchlist` | Entries as `{ticker, added_at, price}`. `price` is the latest cached price or `null` if not yet warmed (SSE fills it within ~500ms). |
| POST | `/api/watchlist` | Add a ticker: `{ticker}`. Validates format (§6); `400 {"detail": ...}` on invalid symbol. Idempotent — re-adding an existing ticker returns `200`. Registers the ticker with the market-data source. |
| DELETE | `/api/watchlist/{ticker}` | Remove the watchlist row. If a **position** in that ticker still exists, the price feed is retained (only the row is removed); otherwise the ticker is also dropped from the market-data source and price cache. |

### Chat
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/chat` | Send `{message}`, receive `{message, actions}` (§9). 30s upstream timeout; on LLM/network failure returns `503 {"detail": ...}` and persists nothing. |

### System
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | `200 {"status": "ok"}` when the DB is reachable **and** the market-data background task is running; otherwise `503 {"status": "degraded", "detail": ...}`. |

### Error Responses

All endpoints use FastAPI's default error shape — `{"detail": "<message>"}` (or a list of field errors for `422` request-validation failures) — with a conventional status: `400` invalid input, `404` unknown resource, `409` business-rule conflict, `503` upstream failure.

### Trade Execution (shared by `POST /api/portfolio/trade` and LLM-issued trades)

Both paths call **one** function, guarded by a process-level lock so a trade-bar submit and an LLM trade cannot interleave and double-spend cash.

Validation, in order (first failure wins → `400`, or reported to the LLM via `actions.errors[]`):

1. `ticker` is tracked and has a warmed price.
2. `side` is `"buy"` or `"sell"`.
3. `quantity` is a finite number, `> 0`, and `<= 1e9`.
4. **Buy:** `quantity * price <= cash_balance` (cash rounded to cents first).
5. **Sell:** `quantity <= position.quantity + 1e-6`.

On success: append to `trades`; upsert `positions` (avg-cost rules per §7, delete row at ~0 qty); adjust `cash_balance` (rounded to cents); add `(fill_price - avg_cost) * qty` to `realized_pnl` on sells; write a `portfolio_snapshots` row.

---

## 9. LLM Integration

When writing code to make calls to LLMs, use cerebras-inference skill to use LiteLLM via OpenRouter to the `openrouter/openai/gpt-oss-120b` model with Cerebras as the inference provider. Structured Outputs should be used to interpret the results.

There is an OPENROUTER_API_KEY in the .env file in the project root.

### How It Works

When the user sends a chat message, the backend:

1. Loads the user's current portfolio context (cash, realized P&L, positions with per-ticker qty + live price + unrealized P&L, watchlist with live prices, total portfolio value; tickers with no warmed price are annotated "price unavailable")
2. Loads recent conversation history from the `chat_messages` table — the last **20 messages** (user + assistant), oldest-first
3. Constructs a prompt with a system message, portfolio context, conversation history, and the user's new message
4. Calls the LLM via LiteLLM → OpenRouter, requesting structured output, using the cerebras-inference skill
5. Parses the complete structured JSON response
6. Auto-executes any trades or watchlist changes specified in the response
7. Stores the message and executed actions in `chat_messages`
8. Returns the complete JSON response to the frontend (no token-by-token streaming — Cerebras inference is fast enough that a loading indicator is sufficient)

### Structured Output Schema

The LLM is instructed to respond with JSON matching this schema:

```json
{
  "message": "Your conversational response to the user",
  "trades": [
    {"ticker": "AAPL", "side": "buy", "quantity": 10}
  ],
  "watchlist_changes": [
    {"ticker": "PYPL", "action": "add"}
  ]
}
```

- `message` (required): The conversational text shown to the user
- `trades` (optional): Array of trades to auto-execute. Each trade goes through the shared Trade Execution path (§8) — same validation and lock as manual trades
- `trades[].quantity` is always a **number of shares** (fractional allowed). The system prompt instructs the LLM to convert dollar amounts ("put $2,000 into NVDA") and relative sizes ("sell half my Tesla") into share quantities using the live prices and position quantities in the portfolio context
- `watchlist_changes` (optional): Array of `{ticker, action}` where `action` is `"add"` or `"remove"`

### Response Validation & Fallback

The response is parsed and validated against the schema. On a parse or schema failure, the backend reprompts **once** ("return valid JSON matching this schema", with the raw output attached). If the retry also fails, `/api/chat` returns `503` and the user sees "The assistant returned an unreadable response — please try again."

### Failure Handling

- **Upstream timeout: 30 seconds.** On timeout, `5xx`, or rate-limit from OpenRouter, `/api/chat` returns `503 {"detail": "The assistant is unavailable right now — please try again."}` and persists no messages.
- A trade that fails validation is **not** an error response: the assistant message is still returned and stored, with the failure in `actions.errors[]` and the offending `actions.trades[].status = "rejected"`.

### Auto-Execution

Trades specified by the LLM execute automatically — no confirmation dialog. This is a deliberate design choice:
- It's a simulated environment with fake money, so the stakes are zero
- It creates an impressive, fluid demo experience
- It demonstrates agentic AI capabilities — the core theme of the course

If a trade fails validation (e.g., insufficient cash), the error is included in the chat response so the LLM can inform the user.

### System Prompt Guidance

The LLM should be prompted as "FinAlly, an AI trading assistant" with instructions to:
- Analyze portfolio composition, risk concentration, and P&L
- Suggest trades with reasoning
- Execute trades when the user asks or agrees
- Convert dollar amounts and relative sizes ("half my position") into share quantities using the live prices and position data in the context
- Never invent tickers or prices that are not in the provided context
- Manage the watchlist proactively
- Be concise and data-driven in responses
- Always respond with valid structured JSON

### LLM Mock Mode

When `LLM_MOCK=true`, the backend returns deterministic mock responses instead of calling OpenRouter. This enables:
- Fast, free, reproducible E2E tests
- Development without an API key
- CI/CD pipelines

The mock must be able to return a response whose trade **fails** validation (e.g., an oversized buy), so E2E exercises the inline `actions.errors[]` / `status: "rejected"` path.

---

## 10. Frontend Design

### Layout

The frontend is a single-page application with a dense, terminal-inspired layout. The specific component architecture and layout system is up to the Frontend Engineer, but the UI should include these elements:

- **Watchlist panel** — grid/table of watched tickers with: ticker symbol, current price (flashing green/red on change), **session change %** (price now vs. the first price this browser session observed for that ticker — label it "Session %", not "Day %", since the sim has no trading day), and a sparkline mini-chart (backfilled from `GET /api/history` on load, then extended live from SSE)
- **Main chart area** — larger chart for the currently selected ticker, price over time. Seeded from `GET /api/history?ticker=` on selection, then appended live from SSE. Clicking a ticker in the watchlist selects it here.
- **Portfolio heatmap** — treemap visualization where each rectangle is a position, sized by portfolio weight, colored by P&L (green = profit, red = loss)
- **P&L chart** — line chart showing total portfolio value over time, using data from `GET /api/portfolio/history`
- **Positions table** — ticker, quantity, avg cost, current price, unrealized P&L ($), unrealized P&L % (vs. avg cost — a *different* number from the watchlist's "Session %", which is a raw price move). Shows `—` for price / P&L while a price is not warmed.
- **Trade bar** — simple input area: ticker field, quantity field, buy button, sell button. Market orders, instant fill.
- **AI chat panel** — docked/collapsible sidebar. Message input, scrolling conversation history, loading indicator while waiting for LLM response. Trade executions and watchlist changes shown inline as confirmations; rejected trades shown inline as errors (from `actions.errors[]`).
- **Header** — portfolio total value (updating live), cash balance, cumulative realized P&L, connection status indicator

### Technical Notes

- Use `EventSource` for SSE connection to `/api/stream/prices`
- **Recharts** for all charts — line charts (price, P&L) *and* the portfolio treemap/heatmap come from the one dependency. Only reach for a canvas library (e.g. Lightweight Charts) if profiling shows SVG can't keep up with ~500ms updates at ~10 tickers — not expected.
- Price flash effect: on receiving a new price, briefly apply a CSS class with background color transition, then remove it
- **Connection status dot** — derive three states from `EventSource`: green once `onopen` fired and `readyState === OPEN`; yellow on `onerror` while `readyState === CONNECTING` (reconnecting); red when `readyState === CLOSED`. The server's ~15s keepalive comment (§6) keeps a quiet stream green.
- **Session change % baseline** — on the first SSE tick for a ticker after page load, store that price in memory as the ticker's baseline; not persisted, resets on refresh.
- **Static-export constraints** — the app relies on no Next.js API routes, middleware, `next/image` optimization, or server-component runtime data fetching; all runtime data comes from `/api/*` + SSE, which `output: 'export'` supports.
- All API calls go to the same origin (`/api/*`) — no CORS configuration needed
- Tailwind CSS for styling with a custom dark theme

---

## 11. Docker & Deployment

### Multi-Stage Dockerfile

```
Stage 1: Node 20 slim
  - Copy frontend/
  - npm install && npm run build (produces static export)

Stage 2: Python 3.12 slim
  - Install uv
  - Copy backend/
  - uv sync (install Python dependencies from lockfile)
  - Copy frontend build output into a static/ directory
  - Expose port 8000
  - CMD: uvicorn serving FastAPI app
```

FastAPI serves the static frontend files and all API routes on port 8000.

### Docker Volume

The SQLite database persists via a named Docker volume:

```bash
docker run -v finally-data:/app/db -p 8000:8000 --env-file .env finally
```

The `db/` directory in the project root maps to `/app/db` in the container. The backend writes `finally.db` to this path.

### Start/Stop Scripts

**`scripts/start_mac.sh`** (macOS/Linux):
- Builds the Docker image if not already built (or if `--build` flag passed)
- Runs the container with the volume mount, port mapping, and `.env` file
- Prints the URL to access the app
- Optionally opens the browser

**`scripts/stop_mac.sh`** (macOS/Linux):
- Stops and removes the running container
- Does NOT remove the volume (data persists)

**`scripts/start_windows.ps1`** / **`scripts/stop_windows.ps1`**: PowerShell equivalents for Windows.

All scripts should be idempotent — safe to run multiple times.

### Optional Cloud Deployment

The container is designed to deploy to AWS App Runner, Render, or any container platform. A Terraform configuration for App Runner may be provided in a `deploy/` directory as a stretch goal, but is not part of the core build.

**Public deployment note:** there is no auth, so a public URL exposes `/api/chat` (spends real OpenRouter credits) and `/api/portfolio/trade`. Any public deployment must add at least a basic per-IP rate limit (e.g., 20 chat requests/min) or an IP allowlist — otherwise document the container as local-only.

---

## 12. Testing Strategy

### Unit Tests (within `frontend/` and `backend/`)

**Backend (pytest)**:
- Market data: simulator generates valid prices, GBM math is correct, Massive API response parsing works, both implementations conform to the abstract interface
- History: `/api/history` returns bounded, oldest-first points; `404` for an untracked ticker; ring buffer evicts oldest past capacity
- Portfolio: trade execution logic, P&L calculations, edge cases (selling more than owned, buying with insufficient cash, selling at a loss)
  - avg-cost weighted-average on buys, unchanged on sells; position row deleted at ~0 qty
  - `realized_pnl` accumulates correctly across a buy→partial-sell→sell sequence
  - validation: `quantity <= 0`, non-finite, `> 1e9`, insufficient cash/shares — all rejected; manual and LLM trades hit one code path
  - cash rounded to cents; no drift across many buy/sell cycles
- Snapshots: adaptive skip under 0.1% move; retention prune of >30-day rows; `/api/portfolio/history` downsampling and `since`/`limit` params
- LLM: structured output parsing handles all valid schemas, one reprompt on malformed response then `503`, trade validation within chat flow (rejected trade → `actions.errors[]`, not an HTTP error), 30s timeout → `503`
- API routes: correct status codes, response shapes, error handling; `/api/health` returns `503` when the market-data task is down
- Startup: market data starts from watchlist ∪ position tickers, not the default 10; `DELETE /api/watchlist/{ticker}` keeps the feed for a still-held ticker

**Frontend (React Testing Library or similar)**:
- Component rendering with mock data
- Price flash animation triggers correctly on price changes
- Watchlist CRUD operations
- Portfolio display calculations
- Chat message rendering and loading state

### E2E Tests (in `test/`)

**Infrastructure**: A separate `docker-compose.test.yml` in `test/` that spins up the app container plus a Playwright container. This keeps browser dependencies out of the production image.

**Environment**: Tests run with `LLM_MOCK=true` by default for speed and determinism.

**Key Scenarios**:
- Fresh start: default watchlist appears, $10k balance shown, prices are streaming
- Add and remove a ticker from the watchlist
- Buy shares: cash decreases, position appears, portfolio updates
- Sell shares: cash increases, position updates or disappears, realized P&L updates
- Session change % reads ~0 at page load and moves as prices tick
- Detail chart is populated immediately on ticker select (backfilled from `/api/history`)
- Portfolio visualization: heatmap renders with correct colors, P&L chart has data points
- AI chat (mocked): send a message, receive a response, trade execution appears inline
- AI chat (mocked): an oversized buy is rejected and the error shows inline
- SSE resilience: disconnect and verify reconnection; connection dot goes yellow then green; a quiet stream stays green (keepalive)

---

## 13. Review Notes — Questions, Clarifications & Simplification Opportunities

*Added by `/doc-review` on 2026-08-27. Everything below is advisory — open questions and suggestions for the team to resolve before/while building the remaining platform (portfolio, watchlist, chat, frontend, Docker). The market-data subsystem is already complete; items touching it are noted as "verify against implementation" rather than "decide".*

---

### RESOLVED 2026-08-28 — decisions folded into §§2, 6–12

All items below have been actioned in the body of the plan. This section is retained as the rationale record. Key decisions made during resolution:

- **A1 / A25** — "daily change %" → **"Session %"**, baseline = first price the browser session sees per ticker (§6, §10).
- **A2 / C3** — price history via a **bounded in-memory ring buffer** (~300 pts/ticker) in the cache layer, exposed as `GET /api/history` (§6, §8, §10). Sparklines and the detail chart backfill from it.
- **A3** — ticker validation `^[A-Z]{1,5}$` in the watchlist route → `400`; simulator already handles unseeded tickers (random $50–$300 seed, default GBM params, 0.3 correlation) (§6).
- **A4** — position tickers stay in the price feed even when removed from the watchlist (§6 Startup Sequence, §8 `DELETE`).
- **A5** — SSE contract rewritten to match the implementation (single batched event, push-on-change, immediate snapshot on connect) + a **~15s keepalive comment** to add to `stream.py` (§6).
- **A6 / A7** — `avg_cost` weighted-average formula and delete-at-`1e-6` rule stated (§7).
- **A8 / A11 / A20** — one shared, process-locked **Trade Execution** path with an ordered validation list; FastAPI `{"detail": …}` error shape (§8).
- **A9** — dollar / relative-size → shares handled in the system prompt (§9).
- **A10** — realized P&L: **lightweight cumulative figure**, `users_profile.realized_pnl`, shown in the header (§2, §7, §8, §10).
- **A12** — all timestamps ISO-8601 **UTC** (§7).
- **A13 / A14 / C4** — snapshots every **60s** + on-trade + adaptive 0.1% skip; 30-day retention; `/api/portfolio/history` gains `since` / `limit` + ~300-point downsample (§7, §8).
- **A15** — chat history window = **last 20 messages** (§9).
- **A16** — `chat_messages.actions` JSON shape specified (§7).
- **A17 / A18** — one reprompt on bad JSON then `503`; 30s upstream timeout → `503`; rejected trades are not HTTP errors (§9).
- **A19** — `/api/health` checks DB + market-data task; `200 {"status":"ok"}` / `503 {"status":"degraded"}` (§8).
- **A21 / A22** — connection-dot derivation and static-export constraints documented (§10).
- **A23** — explicit startup sequence: init DB → read watchlist+positions → start market data on their **union** (§6).
- **A24** — public-deployment rate-limit / allowlist note (§11).
- **B (Massive budget)** — confirmed: `get_snapshot_all` is one call per poll; wording fixed (§6).
- **B ("prices not warmed")** — per-consumer `null` / `—` fallback defined (§6).
- **B (float drift)** — cash rounded to cents on write (§7).
- **C1** — `GET /api/watchlist` returns `{ticker, added_at, price}` with `price` nullable until warmed (§8).
- **C2** — **Recharts** chosen for all charts incl. the treemap (§10).
- **C5** — root `docker-compose.yml` **dropped** (§4); `docker-compose.test.yml` kept.
- **C6** — SSE payload keeps `change` / `direction` (already emitted by the built `PriceUpdate`; not worth changing complete code).
- **C7 / C8** — no change (keep typed `users_profile`; archive-doc merge is cosmetic).

---

### A. Open questions & clarifications needed

#### Market data & charts

1. **"Daily change %" has no defined baseline.** The watchlist (§2, §10) and positions table show a daily/percent change, but the simulator starts from seed prices at container launch — there is no previous close or daily open. Is the baseline (a) the price at page load, (b) the price at backend startup, or (c) a synthetic "open" stored once per calendar day? `PriceUpdate` only carries tick-to-tick `previous_price` and `change`, so whatever baseline is chosen needs its own storage/logic. Recommend: baseline = price observed at page load (matches the "since page load" model already used for sparklines) and label it "session change %" to avoid implying a real trading day.

2. **The main detail chart has no data source.** Sparklines are explicitly "accumulated on the frontend from SSE since page load" (§2), but §10's "larger chart for the currently selected ticker … price over time" is never wired to anything. There is no historical-price API endpoint and no stored price history. Decide one of:
   - **Simplest:** the detail chart is also session-accumulated from SSE (just a bigger sparkline). No backend work.
   - **Better UX:** add a bounded in-memory ring buffer (e.g., last 300–600 points/ticker) in the price-cache layer, exposed as `GET /api/history?ticker=AAPL`. This also lets sparklines render immediately on load instead of starting empty. See simplification #3.

3. **Adding an unseeded ticker is underspecified.** `POST /api/watchlist {ticker}` — what happens when the ticker isn't one of the 10 seeded symbols? The simulator needs a seed price and per-ticker GBM drift/volatility; Massive needs to handle an unknown/invalid symbol. Define: (a) validation + rejection contract (400 with what body?), and (b) default sim parameters for accepted-but-unseeded tickers (e.g., seed at a random \$50–\$300, assign to the "cross-sector" correlation group). Verify what the completed market-data code actually does here.

4. **Removing a watched ticker while holding a position.** `DELETE /api/watchlist/{ticker}` — if the user (or the LLM) removes a ticker they still own, does the price feed stop for it, breaking portfolio valuation and P&L? Recommend an explicit rule: **position tickers are always pinned into the price feed** regardless of watchlist membership; the watchlist only controls what's displayed in the watchlist panel.

5. **SSE cadence wording is contradictory.** §6 says the server "pushes price updates for all tickers … at a regular cadence (~500ms)" but `MARKET_DATA_SUMMARY.md` describes version-based change detection (push only on change). Clarify the contract: push-on-change plus a keepalive comment every N seconds (needed anyway so the browser doesn't treat an idle stream as dead, and so the connection-status dot can distinguish "connected but quiet" from "stalled").

#### Portfolio & trades

6. **`avg_cost` update formula isn't stated.** Spell out: buys → weighted average `((old_qty*old_cost) + (buy_qty*price)) / (old_qty + buy_qty)`; sells → `avg_cost` unchanged, `quantity` reduced. Without this in the spec, different agents will implement it differently.

7. **Closing a position: delete the row or keep it at quantity 0?** §12 says "position updates or disappears" — pick one. Recommend deleting the row when `quantity` falls within an epsilon of 0 (e.g., `1e-6`) to avoid fractional-share dust rows.

8. **Quantity validation rules.** §9 covers insufficient cash / insufficient shares, but not `quantity <= 0`, non-numeric, or absurdly large values. State the full validation list for both `POST /api/portfolio/trade` and LLM-issued trades (they should share one code path).

9. **Dollar-denominated intent in chat.** The trade schema is share-quantity only. Users will say "put \$2,000 into NVDA" or "sell half my Tesla". Confirm the intent: the system prompt must instruct the LLM to convert dollars→shares using the live prices provided in context, and half-position sells using the position quantity in context. Worth an explicit sentence in §9.

10. **Realized P&L is never surfaced.** The `trades` log has the data but no endpoint aggregates it, and no UI shows it. Is realized P&L explicitly out of scope? If so, say so in §2/§10.

11. **Trade execution concurrency.** A trade-bar submit and an LLM trade can overlap. Single-user, but two concurrent reads of `cash_balance` could double-spend. State that trade execution is serialized (a process-level lock / single writer).

12. **Timestamps: UTC?** "ISO timestamp" appears ~10 times with no timezone. Specify `datetime.now(timezone.utc).isoformat()` for storage; frontend converts to local for display.

13. **`portfolio_snapshots` growth.** Every 30s forever, in a volume-mounted SQLite file that persists across restarts — ~2,880 rows/day, unbounded. Decide a retention/downsampling policy, or see simplification #4.

14. **`GET /api/portfolio/history` has no parameters.** After the app runs for days this returns thousands of points. Add `?since=<iso>` and/or `?limit=N` (or server-side downsampling to ~200 points).

#### Chat / LLM

15. **Conversation history window.** §9 step 2 says "recent conversation history" — how many messages (or tokens)? Pick a number (e.g., last 20 messages or last ~4k tokens) so context size is bounded and predictable.

16. **`chat_messages.actions` JSON shape is undefined.** The frontend renders inline confirmations from it, so it needs a schema. Propose:
    ```json
    {"trades": [{"ticker":"AAPL","side":"buy","quantity":10,"price":190.12,"status":"executed"}],
     "watchlist_changes": [{"ticker":"PYPL","action":"add","status":"executed"}],
     "errors": ["Insufficient cash for TSLA buy"]}
    ```

17. **Structured-output reliability on this path.** Does `openrouter/openai/gpt-oss-120b` via Cerebras reliably honor a JSON schema? Define the fallback: validate the response, and on parse/schema failure do one reprompt ("return valid JSON matching schema") before surfacing an error to the user.

18. **`/api/chat` failure contract.** OpenRouter timeout/5xx/rate-limit — what does the endpoint return, and what does the user see? Define a timeout (e.g., 30s) and a user-facing error message. `LLM_MOCK=true` should also exercise the "trade fails validation" branch for E2E.

#### System / frontend

19. **`/api/health` contract.** What does it check — process alive only, or DB reachable + market-data task running? Define the response body (`{"status":"ok"}`) and when it returns non-200.

20. **Standard error-response shape.** No endpoint defines its error body. Pick one (FastAPI's default `{"detail": ...}` is fine) and state it once.

21. **Connection-status "reconnecting" state.** `EventSource` doesn't expose a clean reconnecting state — it's inferred from `onerror` + `readyState === CONNECTING`. Just confirm the frontend derives the three-state dot (green/yellow/red) this way, and that the server sends periodic keepalives (see #5) so a quiet stream doesn't look disconnected.

22. **Next.js `output: 'export'` constraints.** Static export disables API routes, middleware, `next/image` optimization, and server components' runtime data fetching. Confirm the frontend design relies on none of these (all data via `/api/*` + SSE at runtime).

23. **Startup sequence with a persisted DB.** On restart with an existing volume, the market-data source must start with the *current* watchlist ∪ position tickers (which the user may have edited), not the hardcoded default 10. Make the startup order explicit in §6/§7: init DB → read watchlist + positions → start market data with that union.

24. **Public deployment = unauthenticated, uncapped `/api/chat`.** §11's "optional cloud deployment" exposes an open endpoint that spends real OpenRouter credits. Note that cloud deployment should add at least a basic rate limit or IP allowlist, or be documented as local-only.

25. **"% change" means two different things.** Watchlist "daily change %" = price move; positions table "% change" = P&L percentage vs avg cost. Same label, different math — clarify the column headers so agents and users don't conflate them.

### B. Feedback / risks

- **Massive free-tier call budget (verify against implementation).** §6 assumes "poll for the union of all watched tickers" is one call per poll. Polygon.io's free tier may require one call per ticker for real-time snapshots; 10 tickers every 15s would blow the 5 calls/min limit. Confirm the completed `massive_client.py` uses a single snapshot/grouped call, and update §6's wording to match (it currently reads as if any polling interval is safe).
- **The plan lists two chart libraries** ("Lightweight Charts or Recharts", §10). Leaving the choice open invites both being pulled in. Recommend deciding now — see simplification #2.
- **`portfolio_snapshots` immediately-after-trade + every-30s** can produce two snapshots ~milliseconds apart. Harmless, but the history endpoint / chart should tolerate near-duplicate timestamps.
- **No explicit "prices not yet warmed" state.** On the very first page load, SSE has pushed nothing and `cache.get()` returns `None`. Every consumer (portfolio valuation, watchlist GET, chat context) needs a defined behavior when a price is missing (use last trade price? show "—"? exclude from total value?). Worth one sentence in §6.
- **Fractional shares + float math.** Cash and P&L use `REAL`/float throughout. Acceptable for a sim, but repeated buy/sell cycles will accumulate rounding drift in `cash_balance`. Consider rounding cash to cents on write, and document that P&L is display-rounded.

### C. Opportunities to simplify

1. **Collapse the watchlist GET's price duplication.** `GET /api/watchlist` returns "tickers with latest prices" (§8), but the frontend already receives every price via SSE. Returning just `{ticker, added_at}` and letting SSE populate prices removes a second price-fetch code path. (Trade-off: a brief "—" on tickers until the first SSE tick. Acceptable, or send one immediate SSE snapshot on connect.)

2. **Pick one chart library: Recharts.** It covers the line charts (price, P&L) *and* the treemap/heatmap in a single dependency, keeping the bundle and the mental model small. Only reach for a canvas library (Lightweight Charts) if profiling shows the SVG line charts can't keep up with ~500ms updates — unlikely at 10 tickers.

3. **Replace "frontend accumulates history" with a small server-side ring buffer.** A bounded in-memory buffer (last ~300–600 points/ticker) in the price-cache layer, exposed as `GET /api/history?ticker=`, is only a few dozen lines and:
   - lets sparklines and the detail chart render populated on first load instead of starting empty,
   - removes per-client accumulation logic and the associated memory growth in long-lived tabs,
   - gives E2E tests a deterministic thing to assert.
   This is arguably *less* total code than doing it correctly on the frontend for every panel.

4. **Snapshot P&L on trades + a coarser timer.** Drop the 30s cadence to 60–120s (or make it adaptive: only snapshot when total value moved > 0.1% since the last snapshot). Halves-to-quarters the table growth with no visible chart-quality loss, and sidesteps needing a retention policy for a while.

5. **Drop `docker-compose.yml`.** §4 already says "no docker-compose for production", and the start/stop scripts wrap `docker run` directly. The "optional convenience wrapper" is one more artifact to keep in sync with the Dockerfile and env handling for little gain.

6. **Trim the SSE payload.** `direction` (and arguably `change`) are derivable on the client from `price` vs the previously received price. Keeping `previous_price` is worthwhile (lets the first post-connect event flash correctly); `direction`/`change` can be dropped to slim each event. Minor, but multiplied across every tick.

7. **Consider folding `users_profile` into a generic `app_state` key/value table** *only if* more singleton state appears (e.g., a synthetic daily-open per ticker from #1). For just `cash_balance`, the typed table is clearer — leave it. Flagging so the decision is deliberate if #1 adds singleton state.

8. **One `.md` per market-data topic in `planning/archive/` (5 files)** could be a single `MARKET_DATA.md` now that the work is done and summarized. Reduces the "consult these docs only when required" surface. Cosmetic.
