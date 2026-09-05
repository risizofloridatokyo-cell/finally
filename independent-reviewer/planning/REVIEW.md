# Review: changes since `HEAD`

## Findings

### [High] Installing the plugin causes the Stop review to run twice

`.claude/settings.json:8-16` registers a `Stop` hook directly, and the marketplace plugin registers the identical hook in `indenpendent-reviewer/independent-reviewer/hooks/hooks.json:2-12`. Once `independent-reviewer@finally-local` is installed, every Claude stop invokes two concurrent `codex exec` processes that both write `planning/REVIEW.md`.

This doubles the work and makes the generated review nondeterministic: either process can overwrite the other, and the file can be read while the other process is replacing it. Keep the hook in exactly one place. If the marketplace plugin is the deliverable, remove the project-local `hooks` entry from `.claude/settings.json`.

### [High] The `codex-reviewer` agent cannot produce its promised output

`.claude/agents/codex-reviewer.md:6` invokes `planning/Plan.md` and writes to `planing/REVIEW.md`. The latter directory name is misspelled, so the command fails unless an unrelated `planing` directory exists. It also disagrees with the requested `planning/REVIEW.md` path.

Correct the command to use the canonical filenames and ensure it runs from the repository root (or use explicit root-relative paths). Also remove the duplicated `---` after the front matter so the agent instructions are unambiguous.

### [High] The plan specifies history as an available feature while explicitly deferring its implementation

`planning/PLAN.md:179` and `:316` make the bounded cache history and `GET /api/history` a current API/frontend dependency. But `:216-221` list the same ring buffer and route as outstanding implementation work. The current market cache only holds latest prices.

Split the document into the implemented market-data baseline and required integration work, and do not present the endpoint as available until it lands. Specify an exact capacity, point schema/timestamp unit, and whether the initial price is recorded.

### [Medium] Database startup instructions contradict the required startup sequence

`planning/PLAN.md:112` says DB initialization is lazy on the first request. `:209-213` instead requires initialization and reading persisted watchlist/positions before the market source starts on every boot. Both cannot be the normal startup path.

Make application lifespan startup authoritative: initialize/migrate the DB, read the ticker union, then start market data and snapshot tasks. Reserve lazy initialization for a specifically documented test helper only, if needed.

### [Medium] Persistence documentation mixes a named Docker volume with a repository bind mount

The documented command at `planning/PLAN.md:496` mounts the named volume `finally-data` at `/app/db`. `:101` and `:499` instead describe the project `db/` directory as the mounted path. Those are different persistence models.

Choose one for the standard scripts. A named volume is suitable for the documented command; describe `db/` only as an optional local-development bind mount with its own command.

### [Medium] Ticker cleanup is unspecified when the final position is sold

`planning/PLAN.md:330` retains a removed watchlist ticker while it has a position, but the trade rules at `:346-358` do not define the inverse transition after that position reaches zero. The symbol can remain indefinitely in the source, cache, and SSE payload.

Define a single serialized reconciliation operation whose target set is `watchlist union open-position tickers`, and call it after watchlist changes and after trades that open or close positions.

### [Medium] SSE comments cannot tell browser code that a stream is quiet

`planning/PLAN.md:202` and `:463` claim the `: keepalive` comment lets the frontend distinguish a quiet stream from a stalled stream. Native browser `EventSource` does not expose comment receipt to JavaScript. Comments help intermediaries preserve the connection, but cannot update a client-side heartbeat timer.

Either limit the feature to normal EventSource connection/reconnection state, or send a parsed heartbeat event and define client handling for it.

## Notes

- `git diff --check` reports no whitespace errors.
- All marketplace/plugin files are currently untracked. Ensure they are included intentionally when committing; otherwise neither the marketplace nor the plugin will be available to collaborators.
