# ---------------------------------------------------------------------------
# Stage 1: build the Next.js static export (frontend/out)
# ---------------------------------------------------------------------------
FROM node:20-slim AS frontend-build
WORKDIR /frontend

# Dependencies first so source edits don't bust the npm layer.
COPY frontend/package*.json ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

COPY frontend/ ./
RUN npm run build
# `output: 'export'` writes the static site to /frontend/out

# ---------------------------------------------------------------------------
# Stage 2: Python runtime serving the API and the static frontend
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/app/backend/.venv \
    LITELLM_LOCAL_MODEL_COST_MAP=True \
    PATH="/app/backend/.venv/bin:$PATH" \
    STATIC_DIR=/app/backend/static \
    DB_PATH=/app/db/finally.db

RUN pip install uv

WORKDIR /app/backend

# Third-party dependencies first (cached until pyproject.toml / uv.lock change).
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Application source, then install the project itself.
COPY backend/README.md ./README.md
COPY backend/app ./app
RUN uv sync --frozen --no-dev

# Static frontend build and the runtime volume mount point for SQLite.
COPY --from=frontend-build /frontend/out ./static
RUN mkdir -p /app/db

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
