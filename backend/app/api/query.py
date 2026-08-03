"""Question-answering endpoint (any authenticated user)."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from ..core import pipeline
from ..core.auth import get_current_user
from ..core.llm import LLMNotConfigured
from ..logging_config import get_logger
from ..schemas import AskRequest, AskResponse
from ..storage.users import UserRecord

logger = get_logger(__name__)
router = APIRouter(prefix="/api", tags=["query"])


@router.post("/ask", response_model=AskResponse)
async def ask(
    request: AskRequest,
    _: Annotated[UserRecord, Depends(get_current_user)],
) -> AskResponse:
    try:
        response = pipeline.answer_question(
            question=request.question,
            document_ids=request.document_ids,
            top_n=request.top_n,
        )
    except LLMNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        logger.exception("Query failed")
        msg = str(exc)
        lower = msg.lower()
        if any(
            token in lower
            for token in ("503", "high demand", "unavailable", "overloaded", "429", "busy")
        ):
            raise HTTPException(
                status_code=503,
                detail="The assistant is busy right now. Please try again in a moment.",
            )
        raise HTTPException(
            status_code=500,
            detail="Something went wrong answering that. Please try again.",
        )

    logger.info(
        "Answered question",
        extra={
            "extra": {
                "grounded": response.grounded,
                "citations": len(response.citations),
                "timings_ms": response.timings_ms,
            }
        },
    )
    return response
