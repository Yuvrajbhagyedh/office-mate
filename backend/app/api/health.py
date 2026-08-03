"""Health & readiness endpoint."""
from __future__ import annotations

from fastapi import APIRouter

from ..config import settings
from ..deps import registry
from ..core.vectorstore import vector_store
from ..schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    docs, chunks = registry.counts()
    return HealthResponse(
        status="ok",
        environment=settings.environment,
        vector_store=vector_store.health(),
        documents=docs,
        chunks=chunks,
    )
