# FinAlly — AI Trading Workstation

A visually rich, AI-powered trading workstation: live-streaming market data, a
simulated $10k portfolio, and an LLM chat assistant that can analyze positions
and execute trades from natural language. Bloomberg-style dark terminal UI.

Built entirely by coding agents as the capstone project for an agentic AI
coding course.

## Status

In development. The **market data subsystem** (`backend/app/market/`) is
complete and tested — GBM price simulator, optional real data via Massive API,
thread-safe price cache, and an SSE stream endpoint. Portfolio, watchlist,
chat, frontend, and Docker packaging are still to be built. See
[`planning/PLAN.md`](planning/PLAN.md) for the full specification.

## Architecture

Single Docker container serving everything on port 8000:

| Layer | Choice |
|---|---|
| Frontend | Next.js (static export), TypeScript, Tailwind CSS |
| Backend | FastAPI (Python, managed with `uv`) |
| Real-time | Server-Sent Events (one-way push) |
| Database | SQLite, lazy-initialized, volume-mounted |
| AI | LiteLLM → OpenRouter, `openai/gpt-oss-120b` on Cerebras, structured outputs |
| Market data | Built-in GBM simulator (default) or Massive/Polygon.io API (optional) |

## Development

```bash
cd backend
uv sync --extra dev
uv run pytest              # run the test suite
uv run market_data_demo.py # live terminal dashboard of the simulator
```

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `OPENROUTER_API_KEY` | Yes | OpenRouter key for the AI chat assistant |
| `MASSIVE_API_KEY` | No | Massive (Polygon.io) key for real market data; omit to use the simulator |
| `LLM_MOCK` | No | `true` for deterministic mock LLM responses (tests / CI) |

The backend reads `.env` from the project root.

## Project Structure

```
finally/
├── backend/     # FastAPI uv project (market data subsystem implemented)
├── frontend/    # Next.js static export (planned)
├── planning/    # Specification and agent contracts — start with PLAN.md
├── test/        # Playwright E2E tests (planned)
├── scripts/     # Docker start/stop helpers (planned)
└── db/          # SQLite volume mount (runtime)
```

## License

See [LICENSE](LICENSE).
