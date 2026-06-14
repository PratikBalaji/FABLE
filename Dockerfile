# F.A.B.L.E. backend — Cloud Run / Railway image.
# Trimmed for free-tier deploy (P6): no Presidio, no spaCy, no sentence-transformers, no torch.
# Embeddings via OpenAI text-embedding-3-small (dim=384) — see backend/core/embeddings.py.
# Image target: <300 MB.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Minimal system deps — faiss-cpu wheels are prebuilt so no build-essential needed.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy the pinned lockfile first for Docker layer caching.
# F-038: install exact pinned versions from requirements.lock for reproducible builds.
COPY backend/requirements.lock ./requirements.lock

RUN pip install --upgrade pip setuptools wheel \
    && pip install --require-hashes=false -r requirements.lock

# Copy application code.
COPY backend/ ./backend/

# Cloud Run injects $PORT (default 8080). Railway also respects $PORT. Local dev: defaults to 8000.
ENV PORT=8080
EXPOSE 8080

# /health endpoint already implemented in backend.api.main.
CMD ["sh", "-c", "uvicorn backend.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
