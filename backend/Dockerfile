# syntax=docker/dockerfile:1

# --- Build stage: install dependencies with uv ---
FROM python:3.14-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.12.13 /uv /bin/uv

# Precompile .pyc files (faster startup), copy files out of the cache mount instead of
# hard-linking them, and use the image's Python instead of downloading one.
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# Dependencies first: this layer stays cached until pyproject.toml or uv.lock change,
# so editing the code does not reinstall every package.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev

# Then the application itself, installed as a regular package (not editable).
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

# --- Runtime stage: just Python and the virtualenv, no uv, no sources ---
FROM python:3.14-slim

# Never run as root inside the container.
RUN useradd --create-home --uid 1000 netherbrain
WORKDIR /app
COPY --from=builder --chown=netherbrain:netherbrain /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
USER netherbrain
EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"]

CMD ["uvicorn", "netherbrain.main:app", "--host", "0.0.0.0", "--port", "8000"]
