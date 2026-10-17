"""FastAPI application entry point.

Wires routers, middleware (request-id + timing + structured access logs), CORS,
the Prometheus /metrics endpoint, and startup tasks (ensure the vector
collection exists, rebuild the BM25 index from persisted chunks).
"""
from __future__ import annotations

import threading
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from .api import auth, documents, health, query
from .config import settings
from .core.auth import seed_users
from .core.embeddings import embedder
from .core.pipeline import refresh_bm25, seed_documents
from .deps import registry
from .core.vectorstore import vector_store
from .logging_config import configure_logging, get_logger, request_id_ctx
from .metrics import REQUEST_LATENCY, REQUESTS_TOTAL

configure_logging(settings.log_level)
logger = get_logger(__name__)


def _seed_in_background() -> None:
    try:
        seed_documents(settings.seed_docs_dir)
    except Exception:  # noqa: BLE001
        logger.exception("Seeding failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up", extra={"extra": {"env": settings.environment}})
    seed_users()
    try:
        vector_store._dim = embedder.dim
    except Exception:  # noqa: BLE001
        logger.warning("Could not eagerly load embedding model at startup.")
    vector_store.ensure_collection()
    if registry.counts()[0] == 0:
        # Registry is the source of truth: if it is empty (fresh disk), clear
        # any vectors left behind, then load the seed documents in the
        # background so the port opens immediately and health checks pass.
        vector_store.reset()
        threading.Thread(
            target=_seed_in_background, name="seed-docs", daemon=True
        ).start()
    refresh_bm25()
    logger.info("Startup complete")
    yield
    logger.info("Shutting down")


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="Production RAG knowledge assistant with hybrid retrieval, reranking, and grounded citations.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def observability_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
    token = request_id_ctx.set(request_id)
    start = time.perf_counter()
    endpoint = request.url.path
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    except Exception:
        status = 500
        logger.exception("Unhandled error")
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})
    finally:
        elapsed = time.perf_counter() - start
        REQUEST_LATENCY.labels(endpoint=endpoint).observe(elapsed)
        REQUESTS_TOTAL.labels(endpoint=endpoint, status=str(status)).inc()
        logger.info(
            "request",
            extra={"extra": {"method": request.method, "path": endpoint,
                              "status": status, "latency_ms": round(elapsed * 1000, 2)}},
        )
        request_id_ctx.reset(token)


@app.get("/metrics")
async def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


app.include_router(health.router)
app.include_router(auth.router)
app.include_router(documents.router)
app.include_router(query.router)
