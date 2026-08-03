"""Pydantic request/response models — the API contract."""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class DocumentMeta(BaseModel):
    id: str
    filename: str
    filetype: str
    status: str  # processing | ready | failed
    num_chunks: int
    size_bytes: int
    processing_time_ms: Optional[float] = None
    error: Optional[str] = None
    uploaded_at: datetime


class UploadResponse(BaseModel):
    document: DocumentMeta


class DocumentListResponse(BaseModel):
    documents: List[DocumentMeta]


class Citation(BaseModel):
    marker: int = Field(..., description="The [n] marker used in the answer.")
    document_id: str
    filename: str
    page: Optional[int] = None
    section: Optional[str] = None


class RetrievedChunk(BaseModel):
    chunk_id: str
    document_id: str
    filename: str
    page: Optional[int] = None
    section: Optional[str] = None
    text: str
    vector_score: Optional[float] = None
    bm25_score: Optional[float] = None
    fused_score: Optional[float] = None
    rerank_score: Optional[float] = None


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    document_ids: Optional[List[str]] = Field(
        default=None,
        description="Restrict retrieval to these documents. None = search everything.",
    )
    top_n: Optional[int] = Field(default=None, description="Override reranked context size.")


class AskResponse(BaseModel):
    question: str
    answer: str
    grounded: bool = Field(..., description="False when the model refused for lack of evidence.")
    citations: List[Citation]
    retrieved_context: List[RetrievedChunk]
    timings_ms: Dict[str, float]
    model: str


class HealthResponse(BaseModel):
    status: str
    environment: str
    vector_store: str
    documents: int
    chunks: int


class LoginRequest(BaseModel):
    employee_id: str = Field(..., min_length=1, max_length=64)
    dob: str = Field(..., min_length=4, max_length=32, description="Date of birth YYYY-MM-DD or DD/MM/YYYY")


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    employee_id: str
    name: str
    role: str


class MeResponse(BaseModel):
    employee_id: str
    name: str
    role: str
