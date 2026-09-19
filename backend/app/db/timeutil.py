"""ISO-8601 UTC timestamp helpers."""

from __future__ import annotations

from datetime import UTC, datetime


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def normalize_iso(value: str) -> str:
    """Parse any ISO-8601 string (naive is assumed UTC) and return canonical UTC ISO form.

    Raises ValueError on unparseable input.
    """
    dt = datetime.fromisoformat(value.strip())
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat(timespec="microseconds")
