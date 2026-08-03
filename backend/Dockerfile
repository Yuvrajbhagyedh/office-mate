# syntax=docker/dockerfile:1
# Lightweight image for free-tier hosts (no torch / sentence-transformers).
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    EMBEDDING_PROVIDER=google \
    EMBEDDING_MODEL=gemini-embedding-001 \
    EMBEDDING_DIM=768 \
    RERANKER_ENABLED=false \
    QDRANT_COLLECTION=documents_g

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
COPY eval ./eval

RUN mkdir -p /app/data

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://localhost:${PORT:-8000}/health || exit 1

CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
