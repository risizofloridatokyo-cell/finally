"""LLM chat assistant: structured-output calls via LiteLLM -> OpenRouter (Cerebras)."""

import os

# Must run before anything imports litellm: otherwise litellm fetches its model-cost map from
# GitHub at import time, which stalls first boot ~30s (and fails offline). Use the bundled copy.
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

from .router import router  # noqa: E402
from .service import handle_chat  # noqa: E402

__all__ = ["router", "handle_chat"]
