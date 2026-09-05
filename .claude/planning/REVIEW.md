# Review: changes since `HEAD`

## Findings

### [Blocker] The Stop hook cannot write the intended review file

`settings.json:12` invokes `codex exec` from this `.claude` directory, but the repository plan is at `../planning/PLAN.md`. The hook prompt only says `planning/REVIEW.md`, so it targets a different location than the plan it is meant to review. A review can therefore be written beside the hook configuration instead of beside the project plan.

Pass explicit paths: review `../planning/PLAN.md` and write `../planning/REVIEW.md`, or configure the hook to run from the repository root.

### [High] The plan both requires and defers the history feature

`../planning/PLAN.md:179` and `:316` describe the cache ring buffer and `GET /api/history` as part of the contract, while `:218-221` explicitly list that same buffer and route as remaining implementation work. The existing `backend/app/market/cache.py` contains only latest prices—no history buffer or API.

Split the text into the implemented market-data baseline and required platform additions. Do not label the history endpoint available until it is implemented; specify buffer capacity, point schema, and whether the seed price is recorded.

### [High] Ticker removal has no reconciliation rule after the final position is sold

`../planning/PLAN.md:214` and `:330` retain the feed when a removed watchlist ticker still has a position, but the trade flow (`:346-358`) never says what happens when that final position is closed. The ticker can remain forever in the source/cache/SSE payload, or agents may remove it inconsistently.

Define one locked `reconcile_tracked_tickers()` operation targeting `watchlist ∪ open-position tickers`; call it after watchlist mutations and successful trades that can open or close positions.

### [High] LLM watchlist mutations lack the manual route’s result/error contract

`../planning/PLAN.md:169` applies ticker validation to LLM changes, but `:300-301` only permits coarse statuses and an unlinked string-error array. It does not define invalid action/ticker, duplicate add, absent remove, or mixed-response behavior, unlike the manual route at `:329`.

Use the same normalized watchlist command service for chat-originated changes. Persist a per-item result with `status` and an optional machine-readable error, and define idempotency and ordering relative to LLM trades.

### [Medium] “First price seen” conflicts with “first SSE tick” for Session %

The resolution record at `../planning/PLAN.md:574` defines the baseline as the first price the browser sees, while `:464` defines it as the first SSE tick. A price from `GET /api/watchlist` or `/api/history` may arrive first, producing different results and making the E2E assertion nondeterministic.

Choose one baseline and define ordering. A practical choice is the first valid price from the initial watchlist/SSE snapshot, with history never setting the baseline.

### [Medium] SSE comments cannot drive quiet-versus-stalled client state

`../planning/PLAN.md:202` and `:463` say a `: keepalive` comment lets the client distinguish a quiet stream from a stalled one. Browser `EventSource` does not expose received comments to JavaScript. The comment keeps the connection alive, but cannot reset a client-side last-message timer.

Either limit the feature to connection/reconnection state or emit a parsed heartbeat event and define its client handling.

### [Medium] The Codex review-agent command has broken target paths

`agents/codex-reviewer.md:6` requests `planning/Plan.md` and writes to `planing/REVIEW.md`. The output directory has a spelling error, and these paths do not identify the sibling project planning directory from this working directory.

Use `../planning/PLAN.md` and `../planning/REVIEW.md`, or change to the repository root before invoking Codex.

## Notes

- `git diff --check` reported no whitespace errors.
- The current cache and stream support latest prices and versioned batch events, but not the newly specified history buffer or keepalive.
