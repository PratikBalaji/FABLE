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

# Copy pyproject first for Docker layer caching.
COPY pyproject.toml ./

# Install runtime deps. We pin via pyproject; `pip install .` would need source so we
# do an explicit dep install (faster, avoids editable-build overhead at runtime).
RUN pip install --upgrade pip setuptools wheel \
    && pip install \
        "openai>=1.30.0" \
        "fastapi>=0.111.0" \
        "uvicorn[standard]>=0.30.0" \
        "pydantic>=2.7.0" \
        "pydantic-settings>=2.3.0" \
        "httpx>=0.27.0" \
        "faiss-cpu==1.9.0.post1" \
        "numpy" \
        "supabase>=2.5.0" \
        "structlog>=24.2.0" \
        "PyJWT[crypto]>=2.8.0" \
        "itsdangerous>=2.2.0" \
        "cryptography>=41.0.0" \
        "python-multipart>=0.0.9" \
        "aiofiles>=23.2.1" \
        "nbformat>=5.10.0" \
        "slowapi>=0.1.9" \
        "pypdf>=4.0.0" \
        "python-docx>=1.1.0"

# Copy application code.
COPY backend/ ./backend/

# Cloud Run injects $PORT (default 8080). Railway also respects $PORT. Local dev: defaults to 8000.
ENV PORT=8080
EXPOSE 8080

# /health endpoint already implemented in backend.api.main.
CMD ["sh", "-c", "uvicorn backend.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
