#!/usr/bin/env bash
# Start FinAlly in Docker (macOS/Linux). Idempotent: safe to run repeatedly.
#
# Usage: scripts/start_mac.sh [--build] [--no-open]
#   --build     rebuild the image even if it already exists
#   --no-open   do not open the browser
set -euo pipefail

IMAGE="finally"
CONTAINER="finally"
VOLUME="finally-data"
PORT=8000
URL="http://localhost:${PORT}"

BUILD=0
OPEN=1
for arg in "$@"; do
  case "$arg" in
    --build) BUILD=1 ;;
    --no-open) OPEN=0 ;;
    -h|--help)
      sed -n '2,7p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "Unknown option: $arg (expected --build and/or --no-open)" >&2
      exit 2
      ;;
  esac
done

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! command -v docker >/dev/null 2>&1; then
  echo "Error: docker is not installed or not on PATH." >&2
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  echo "Error: the Docker daemon is not running. Start Docker Desktop (or the docker service) and retry." >&2
  exit 1
fi

if [ ! -f .env ]; then
  echo "Error: .env not found in $ROOT." >&2
  echo "Create it from the template and add your OpenRouter key:  cp .env.example .env" >&2
  exit 1
fi

if [ "$BUILD" -eq 1 ] || ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo "Building image '$IMAGE'..."
  docker build -t "$IMAGE" .
else
  echo "Using existing image '$IMAGE' (pass --build to rebuild)."
fi

# Replace any existing container (running or stopped) with the same name.
if docker container inspect "$CONTAINER" >/dev/null 2>&1; then
  echo "Replacing existing container '$CONTAINER'..."
  docker rm -f "$CONTAINER" >/dev/null
fi

echo "Starting container '$CONTAINER'..."
docker run -d \
  --name "$CONTAINER" \
  -v "${VOLUME}:/app/db" \
  -p "${PORT}:8000" \
  --env-file .env \
  "$IMAGE" >/dev/null

# Wait (up to ~30s) for the API to come up, when curl is available.
if command -v curl >/dev/null 2>&1; then
  printf "Waiting for the app to become healthy"
  ready=0
  for _ in $(seq 1 30); do
    if curl -fsS "${URL}/api/health" >/dev/null 2>&1; then
      ready=1
      break
    fi
    printf "."
    sleep 1
  done
  echo
  if [ "$ready" -eq 0 ]; then
    echo "Warning: the app did not report healthy within 30s. Check logs:  docker logs $CONTAINER" >&2
  fi
fi

echo "FinAlly is running at $URL"
echo "Stop it with: scripts/stop_mac.sh"

if [ "$OPEN" -eq 1 ]; then
  if command -v open >/dev/null 2>&1; then
    open "$URL" >/dev/null 2>&1 || true
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$URL" >/dev/null 2>&1 || true
  elif command -v cmd.exe >/dev/null 2>&1; then
    cmd.exe /c start "" "$URL" >/dev/null 2>&1 || true
  fi
fi
