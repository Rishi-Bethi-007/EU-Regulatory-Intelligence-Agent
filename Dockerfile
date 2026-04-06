# ─────────────────────────────────────────────────────────────────────────────
# EU Regulatory Intelligence Agent — Dockerfile
#
# Build:   docker build -t eu-reg-agent .
# Run:     docker run -p 8000:8000 --env-file .env eu-reg-agent
# Health:  curl localhost:8000/health
#
# Production: Amazon ECR (eu-north-1) → ECS Fargate
# ─────────────────────────────────────────────────────────────────────────────

FROM python:3.13-slim

# Install system dependencies needed by some Python packages
# (sentence-transformers needs gcc for tokenizer compilation)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Install uv — pinned for reproducible builds
COPY --from=ghcr.io/astral-sh/uv:0.6.6 /uv /usr/local/bin/uv

# Tell uv to use the system Python (already in the base image)
# and never try to download/manage its own Python installation.
# Without this, uv looks for a managed CPython that doesn't exist in the container.
ENV UV_PYTHON_PREFERENCE=only-system
ENV UV_LINK_MODE=copy

WORKDIR /app

# ── Layer cache optimisation ──────────────────────────────────────────────────
# Copy dependency files FIRST so this layer is only rebuilt when
# pyproject.toml or uv.lock changes — not on every code change.
COPY pyproject.toml uv.lock ./

# Install production dependencies only
# --frozen: fail if uv.lock is out of sync (ensures reproducibility)
# --no-dev: skip ruff, pytest, and other dev tools
RUN uv sync --frozen --no-dev

# ── Application code ──────────────────────────────────────────────────────────
# Copy after deps so code changes don't invalidate the expensive dep layer
COPY . .

# ── Runtime config ────────────────────────────────────────────────────────────
EXPOSE 8000

# Health check — ECS uses this to determine task health before routing traffic
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Activate the virtualenv and run uvicorn directly.
# Using the venv python directly is more explicit than uv run,
# and avoids uv trying to resolve a Python interpreter at startup.
CMD [".venv/bin/python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
