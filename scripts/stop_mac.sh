#!/usr/bin/env bash
# Stop and remove the FinAlly container (macOS/Linux). Idempotent.
# The 'finally-data' volume is NOT removed, so your data persists.
set -euo pipefail

CONTAINER="finally"

if ! command -v docker >/dev/null 2>&1; then
  echo "Error: docker is not installed or not on PATH." >&2
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  echo "Error: the Docker daemon is not running." >&2
  exit 1
fi

if docker container inspect "$CONTAINER" >/dev/null 2>&1; then
  docker rm -f "$CONTAINER" >/dev/null
  echo "Stopped and removed container '$CONTAINER' (volume 'finally-data' kept)."
else
  echo "Container '$CONTAINER' is not running; nothing to do."
fi
