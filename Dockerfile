# Ross MD — backend (FastAPI + the agent orchestrator).
# Built for DigitalOcean App Platform; binds to $PORT (App Platform sets 8080).
FROM python:3.14-slim

# uv for fast, locked installs
RUN pip install --no-cache-dir uv

WORKDIR /app

# huggingface_hub / fastembed cache lives here so the model we bake below
# survives into the running container (no cold-start download on first request)
ENV HF_HOME=/opt/models \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

# 1) dependencies (cached layer — only re-runs when the lockfile changes)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# 2) app code
COPY ross ./ross
RUN uv sync --frozen --no-dev

# 3) pre-download the BGE-small embedding model into the image
RUN uv run python -c "from ross.embed import embed_one; embed_one('warmup')"

EXPOSE 8080
CMD ["sh", "-c", "uv run uvicorn ross.server:app --host 0.0.0.0 --port ${PORT:-8080}"]
