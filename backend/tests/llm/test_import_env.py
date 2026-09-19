"""Importing app.llm must select LiteLLM's bundled cost map before litellm loads."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
PROBE = (
    "import os, sys\n"
    "assert 'litellm' not in sys.modules\n"
    "import app.llm\n"
    "print(os.environ.get('LITELLM_LOCAL_MODEL_COST_MAP'))\n"
)


def _run(env_value: str | None) -> str:
    env = {k: v for k, v in os.environ.items() if k != "LITELLM_LOCAL_MODEL_COST_MAP"}
    if env_value is not None:
        env["LITELLM_LOCAL_MODEL_COST_MAP"] = env_value
    out = subprocess.run(
        [sys.executable, "-c", PROBE],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )
    return out.stdout.strip().splitlines()[-1]


def test_importing_app_llm_sets_local_cost_map():
    assert _run(None) == "True"


def test_explicit_value_is_not_overridden():
    assert _run("False") == "False"
