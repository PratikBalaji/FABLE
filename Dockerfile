FROM python:3.11-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml ./
COPY backend/ ./backend/

# Install Python deps (CPU-only torch to save ~4GB)
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu \
    -e "." \
    && pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

EXPOSE 8000

CMD ["uvicorn", "backend.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
