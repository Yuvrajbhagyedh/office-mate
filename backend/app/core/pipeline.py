"""Orchestration: the two end-to-end flows.

ingest_document():  bytes -> extract -> clean+chunk -> embed -> index (vector +
                    BM25) -> registry. Records processing time.

answer_question():  question -> hybrid retrieve -> rerank -> build grounded
                    prompt -> LLM -> parse citations. Records every stage
                    timing in the Trace.

This module is the only place that knows the *order* of stages; each stage is
implemented in its own module and is independently testable.
"""
from __future__ import annotations

import re
import time
from typing import List, Optional

from ..config import settings
from ..deps import registry
from ..logging_config import get_logger
from ..metrics import ANSWERS_REFUSED, CHUNKS_INDEXED, DOCS_INGESTED, Trace
from ..schemas import AskResponse, Citation, RetrievedChunk
from . import ingestion, preprocessing
from .bm25 import bm25_index
from .embeddings import embedder
from .llm import llm
from .prompt import REFUSAL_PHRASE, SYSTEM_PROMPT, build_context_block, build_user_prompt
from .reranker import reranker
from .retrieval import hybrid_retrieve
from .vectorstore import vector_store

logger = get_logger(__name__)

_CITATION_RE = re.compile(r"\[(\d+)\]")


def refresh_bm25() -> None:
    """Rebuild the in-memory BM25 index from the registry. Call on startup and
    after any ingest/delete."""
    bm25_index.build(registry.all_chunks())


def ingest_document(doc_id: str, filename: str, data: bytes) -> None:
    """Process an already-registered document. Updates registry status."""
    start = time.perf_counter()
    try:
        segments = ingestion.extract_segments(filename, data)
        chunks = preprocessing.chunk_segments(
            segments, settings.chunk_size, settings.chunk_overlap
        )
        if not chunks:
            raise ValueError("No extractable text found in document.")

        vectors = embedder.embed_documents([c.text for c in chunks])

        payloads = [
            {
                "document_id": doc_id,
                "filename": filename,
                "chunk_index": c.chunk_index,
                "page": c.page,
                "section": c.section,
                "text": c.text,
            }
            for c in chunks
        ]
        vector_store.upsert([c.id for c in chunks], vectors, payloads)

        registry.add_chunks(
            [
                {
                    "id": c.id,
                    "document_id": doc_id,
                    "chunk_index": c.chunk_index,
                    "page": c.page,
                    "section": c.section,
                    "text": c.text,
                }
                for c in chunks
            ]
        )
        refresh_bm25()

        elapsed_ms = (time.perf_counter() - start) * 1000
        registry.mark_ready(doc_id, num_chunks=len(chunks), processing_time_ms=round(elapsed_ms, 2))
        DOCS_INGESTED.inc()
        CHUNKS_INDEXED.inc(len(chunks))
        logger.info(
            "Document ingested",
            extra={"extra": {"document_id": doc_id, "chunks": len(chunks), "ms": round(elapsed_ms, 2)}},
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Ingestion failed", extra={"extra": {"document_id": doc_id}})
        registry.mark_failed(doc_id, str(exc))
        raise


def delete_document(doc_id: str) -> bool:
    ok = registry.delete_document(doc_id)
    if ok:
        vector_store.delete_document(doc_id)
        refresh_bm25()
    return ok


def answer_question(
    question: str, document_ids: Optional[List[str]], top_n: Optional[int]
) -> AskResponse:
    trace = Trace()
    top_n = top_n or settings.rerank_top_n

    # 1. Hybrid retrieval (embed + vector + bm25 + fusion) — each stage timed inside.
    fused = hybrid_retrieve(question, document_ids, trace)

    # 2. Hydrate candidate text from the registry (single source of truth).
    candidates = _hydrate(fused)

    # 3. Cross-encoder rerank.
    with trace.stage("rerank"):
        top_chunks = reranker.rerank(
            question, candidates, top_n=top_n, min_score=settings.min_rerank_score
        )

    # 4. Grounded prompt + generation.
    context_text, ordered = build_context_block(top_chunks)
    user_prompt = build_user_prompt(question, context_text)
    with trace.stage("llm"):
        if not top_chunks:
            answer = REFUSAL_PHRASE
        else:
            answer = llm.generate(SYSTEM_PROMPT, user_prompt)

    grounded = _is_grounded(answer)
    if not grounded:
        ANSWERS_REFUSED.inc()

    citations = _extract_citations(answer, ordered) if grounded else []

    return AskResponse(
        question=question,
        answer=answer,
        grounded=grounded,
        citations=citations,
        retrieved_context=[_to_retrieved(c) for c in ordered],
        timings_ms=trace.as_dict(),
        model=llm.model,
    )


def _hydrate(fused: List[dict]) -> List[dict]:
    """Attach full chunk text + provenance from the registry to fused hits."""
    out: List[dict] = []
    for hit in fused:
        row = registry.get_chunk(hit["chunk_id"])
        if not row:
            continue
        out.append(
            {
                "chunk_id": hit["chunk_id"],
                "document_id": row["document_id"],
                "filename": _filename_for(row["document_id"]),
                "page": row["page"],
                "section": row["section"],
                "text": row["text"],
                "vector_score": hit.get("vector_score"),
                "bm25_score": hit.get("bm25_score"),
                "fused_score": hit.get("fused_score"),
            }
        )
    return out


_FILENAME_CACHE: dict[str, str] = {}


def _filename_for(doc_id: str) -> str:
    if doc_id not in _FILENAME_CACHE:
        meta = registry.get_document(doc_id)
        _FILENAME_CACHE[doc_id] = meta.filename if meta else doc_id
    return _FILENAME_CACHE[doc_id]


def _is_grounded(answer: str) -> bool:
    normalized = answer.strip().lower().rstrip(".")
    return normalized != REFUSAL_PHRASE.lower().rstrip(".")


def _extract_citations(answer: str, ordered: List[dict]) -> List[Citation]:
    markers = sorted({int(m) for m in _CITATION_RE.findall(answer)})
    citations: List[Citation] = []
    for marker in markers:
        if 1 <= marker <= len(ordered):
            ch = ordered[marker - 1]
            citations.append(
                Citation(
                    marker=marker,
                    document_id=ch["document_id"],
                    filename=ch["filename"],
                    page=ch.get("page"),
                    section=ch.get("section"),
                )
            )
    return citations


def _to_retrieved(c: dict) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=c["chunk_id"],
        document_id=c["document_id"],
        filename=c["filename"],
        page=c.get("page"),
        section=c.get("section"),
        text=c["text"],
        vector_score=c.get("vector_score"),
        bm25_score=c.get("bm25_score"),
        fused_score=c.get("fused_score"),
        rerank_score=c.get("rerank_score"),
    )
