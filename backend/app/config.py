"""Runtime configuration: .env loading and filesystem locations."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# backend/app/config.py -> repo root is two levels above the package dir
REPO_ROOT = Path(__file__).resolve().parents[2]

# Real environment variables always win over .env values.
load_dotenv(REPO_ROOT / ".env", override=False)

SNAPSHOT_INTERVAL_SECONDS = 60.0
SNAPSHOT_MIN_CHANGE = 0.001  # 0.1% move in total value required to record a timed snapshot
RETENTION_DAYS = 30
RETENTION_INTERVAL_SECONDS = 24 * 3600.0


def get_static_dir() -> Path | None:
    """Directory of the static frontend export, or None if none exists.

    STATIC_DIR env wins; otherwise <repo>/backend/static, then <repo>/frontend/out.
    """
    raw = os.environ.get("STATIC_DIR", "").strip()
    candidates = (
        [Path(raw)] if raw else [REPO_ROOT / "backend" / "static", REPO_ROOT / "frontend" / "out"]
    )
    for path in candidates:
        if path.is_dir():
            return path
    return None
