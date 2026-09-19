# FinAlly E2E tests (Playwright)

Browser tests for the whole stack (PLAN §12). They drive the UI through the `data-testid` contract in
`planning/TEAM_CONTRACTS.md`, and use the public HTTP API for setup, cross-checks and state reset (there is no
reset endpoint).

## Run in Docker (recommended, fresh DB, mock LLM)

From the repo root:

```bash
docker compose -f test/docker-compose.test.yml up --build --abort-on-container-exit --exit-code-from playwright
docker compose -f test/docker-compose.test.yml down -v
```

- `web` is built from the root `Dockerfile` with `LLM_MOCK=true`, the simulator, and a tmpfs `/app/db` (empty DB every run).
- `playwright` (`mcr.microsoft.com/playwright:v1.63.0-noble`) runs the suite against `http://web:8000`.
- Reports land in `test/playwright-report/` and `test/test-results/` (traces for failures).

## Run locally against an already-running app

```bash
cd test
npm install
npx playwright install chromium
BASE_URL=http://localhost:8000 npx playwright test          # bash
$env:BASE_URL="http://localhost:8000"; npx playwright test  # PowerShell
```

Fast local backend (serves the exported frontend, mock LLM, throw-away DB):

```bash
cd backend
LLM_MOCK=true STATIC_DIR=../frontend/out DB_PATH=/tmp/e2e.db uv run uvicorn app.main:app --port 8000
```

Useful flags: `--headed`, `--ui`, `-g "chat"` (grep), `specs/03-trading.spec.ts`, `npx playwright show-report`.

## Notes

- **Single worker, serial files.** All specs share one server and one SQLite DB.
- **Fresh DB assumption.** `01-fresh-start` asserts the seeded `$10,000.00`. Point the suite at a new DB, or set
  `FRESH_DB=0` to skip that exact-value assertion when re-running against a used DB. Every other spec is
  independent of prior state: the `app` fixture (`lib/fixtures.ts`) first sells all positions and restores the
  default ten-ticker watchlist through the API, and assertions use deltas or values read back from `/api/portfolio`.
- **Mock LLM triggers** (`oversized`, `buy`, `sell`, `add`, `remove`) are pinned in `planning/TEAM_CONTRACTS.md`; the
  chat spec fails if the mock's wording drifts from "Mock:".
- **SSE resilience** (`06-sse-resilience`) loads the page through `lib/flaky-proxy.ts`, a tiny in-process reverse proxy
  that can cut, refuse, mute or 500 the stream at the socket level. Browser offline emulation is not used because it
  does not sever an established `EventSource`.
- History-backfill specs wait until the server ring buffer holds ~30 points (~15s after app start), so the first run
  after boot is slower.

## Layout

```
playwright.config.ts   baseURL from BASE_URL (default http://localhost:8000), 1 worker, traces on failure
lib/                   env, api helpers + resetState, formatting, page object (app.ts), flaky SSE proxy
specs/00-api-smoke     HTTP contract checks (health, watchlist, history, validation, SSE snapshot)
specs/01-fresh-start   10 tickers, $10k, prices streaming + flashing
specs/02-watchlist     add / remove / invalid / held-ticker removal
specs/03-trading       buy, sell, avg cost, realized P&L, validation errors, heatmap, P&L chart
specs/04-charts        session %, sparkline + detail chart backfill from /api/history
specs/05-chat          mocked chat: reply, executed / rejected trades, watchlist changes, loading, 503
specs/06-sse-resilience  drop -> yellow -> green, prices resume, quiet stream stays green, hard failure -> red
```
