"""Optional live smoke test against OpenRouter/Cerebras (not part of pytest).

Run: cd backend && uv run python -m app.llm.smoke_live
Needs OPENROUTER_API_KEY in the environment or the repo-root .env. The key is never printed.
"""

from __future__ import annotations

import asyncio
import os
import sys

from app import config  # noqa: F401  (loads the repo-root .env)

from .client import get_structured_response
from .prompts import build_messages

CONTEXT = {
    "cash_balance": 10000.0,
    "realized_pnl": 0.0,
    "total_value": 10000.0,
    "total_unrealized_pnl": 0.0,
    "positions": [],
    "watchlist": [
        {"ticker": "AAPL", "price": 190.0},
        {"ticker": "NVDA", "price": 120.0},
    ],
}


async def main() -> int:
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key or key.startswith("your-"):  # unset, or the .env.example placeholder
        print("OPENROUTER_API_KEY is not set; skipping live smoke test.")
        return 0
    messages = build_messages(CONTEXT, [], "Put $1,000 into NVDA and add PYPL to my watchlist.")
    result = await get_structured_response(messages)
    print(result.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
