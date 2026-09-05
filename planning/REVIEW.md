# Review: changes since `HEAD`

## Findings

### High — The marketplace plugin cannot be installed from its declared source

`.claude-plugin/marketplace.json` declares `independent-reviewer` with source
`./independent-reviewer`, but that directory has no
`independent-reviewer/.claude-plugin/plugin.json`. A marketplace entry requires
the source plugin manifest; enabling `independent-reviewer@cheng` in
`.claude/settings.json` therefore points at a plugin that collaborators cannot
install or resolve. The marketplace manifest also spells the metadata key
`authoer` rather than `author`.

Add a valid plugin manifest under `independent-reviewer/.claude-plugin/`, then
correct the metadata key (or remove the key if it is not supported by the
marketplace schema). Verify installation from a clean checkout before enabling
the plugin by default.

### High — The Codex reviewer agent writes to a misspelled, noncanonical path

`.claude/agents/codex-reviewer.md` runs:

```text
codex exec "Please review the file planning/Plan.md and write your feedback to planing/REVIEW.md"
```

The repository file is `planning/PLAN.md`, and the requested output directory
is `planning/`, not `planing/`. This agent will fail to produce the promised
review (or create an unintended directory) when invoked. Correct both paths
and ensure the command runs from the repository root.

### High — `PLAN.md` advertises the history API as available while deferring its implementation

`planning/PLAN.md` makes the cache ring buffer and `GET /api/history` a
frontend/API dependency (Sections 2, 6, 8, and 10), then lists the same work as
an outstanding implementation delta in Section 6. The actual
`backend/app/market/cache.py` only stores the latest `PriceUpdate`; it has no
history buffer, and no route exposes history.

Split the document into the implemented market-data baseline and required
integration extensions. Do not describe `/api/history` as available until it
exists. Define the exact capacity, point schema/timestamp unit, whether the
initial seeded price is recorded, and the owner of the route.

### Medium — The normal startup model is contradictory

Section 4 says database initialization happens lazily on the first request.
Section 6 requires the database to be initialized and its persisted watchlist
and positions read before the market source starts on every boot. Those cannot
both be the normal application lifecycle.

Make application-lifespan startup authoritative: initialize/migrate the DB,
read `watchlist ∪ open positions`, start the market source, then start snapshot
tasks. If lazy initialization remains useful for a test helper, scope it
explicitly to that path.

### Medium — Docker persistence documentation describes two different mounts

The documented command uses a named volume:

```bash
docker run -v finally-data:/app/db ...
```

Elsewhere the plan says the repository's `db/` directory maps to `/app/db`.
The former is Docker-managed storage and the latter is a host bind mount; they
do not provide the same user-visible location or start-script behavior.

Choose one for the primary workflow. If named volumes are intended, describe
the top-level `db/` directory only as an optional local-development bind mount
and provide its separate command.

### Medium — Ticker cleanup is undefined after closing a removed position

The plan keeps a ticker in the market source after it is removed from the
watchlist while a position exists. It does not define the inverse transition:
selling the final shares of a ticker that is no longer watched. The ticker can
remain indefinitely in the simulator, cache, SSE payload, and Massive poll set.

Define a serialized `reconcile_tracked_tickers()` operation whose target is
`watchlist ∪ open-position tickers`. Invoke it after watchlist mutations and
after any trade that opens or closes a position, with a specified retry policy
if a source update fails.

### Medium — SSE comments cannot implement the proposed quiet-stream UI signal

The plan says a `: keepalive` SSE comment lets browser code distinguish a quiet
stream from a stalled one. Native `EventSource` does not expose received SSE
comments to JavaScript. Comments can prevent proxy timeouts, but cannot reset a
client-side heartbeat timer.

Either limit the requirement to EventSource open/error/closed state, or emit a
parsed heartbeat event and specify how the client consumes it.

### Low — The updated README still presents planned infrastructure as current

`README.md` correctly says Docker packaging is still to be built, but its
Architecture section immediately states "Single Docker container serving
everything on port 8000" and lists a volume-mounted SQLite database and an AI
stack that do not yet exist in the checkout. This makes the current status
ambiguous for a new contributor.

Label that table as the *target architecture*, or restrict it to implemented
components and link to `planning/PLAN.md` for planned infrastructure.

## Verification

- `git diff --check` completed without whitespace errors.
- The currently implemented market module supports a latest-price cache and
  version-triggered, batched SSE events. It does not yet implement the planned
  history buffer/route or SSE keepalive.
- All marketplace/plugin files are untracked, so they must be included
  intentionally in the commit for the plugin feature to reach collaborators.
