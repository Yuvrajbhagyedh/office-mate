"""Hybrid retrieval: vector search + BM25, fused with Reciprocal Rank Fusion.

Why hybrid + RRF (see ARCHITECTURE.md for the full rationale):
* Vector search finds semantically related passages even with no shared words.
* BM25 nails exact keyword/entity matches that embeddings blur.
* RRF fuses the two *rankings* (not scores), so we never have to normalize a
  cosine similarity against a BM25 score — it just uses positions:
        score(d) = sum over lists of  1 / (k + rank_list(d))
  This is robust, parameter-light, and consistently beats either retriever
  alone on keyword-heavy corpora.

The output is a de-duplicated candidate list ordered by fused score, ready for
the (more expensive, more accurate) cross-encoder reranker.
"""
from __future__ import annotations

from typing import List, Optional

from ..config import settings
from .bm25 import bm25_index
from .embeddings import embedder
from .vectorstore import vector_store


def hybrid_retrieve(
    query: str, document_ids: Optional[List[str]], trace
) -> List[dict]:
    with trace.stage("embed_query"):
        query_vector = embedder.embed_query(query)

    with trace.stage("vector_search"):
        vector_hits = vector_store.search(
            query_vector, top_k=settings.vector_top_k, document_ids=document_ids
        )

    with trace.stage("bm25_search"):
        bm25_hits = bm25_index.search(
            query, top_k=settings.bm25_top_k, document_ids=document_ids
        )

    with trace.stage("fusion"):
        fused = _reciprocal_rank_fusion(vector_hits, bm25_hits, k=settings.rrf_k)
    return fused


def _reciprocal_rank_fusion(vector_hits: List[dict], bm25_hits: List[dict], k: int) -> List[dict]:
    merged: dict[str, dict] = {}

    def ingest(hits: List[dict], score_key: str) -> None:
        for rank, hit in enumerate(hits, start=1):
            cid = hit["chunk_id"]
            entry = merged.setdefault(
                cid,
                {
                    "chunk_id": cid,
                    "document_id": hit.get("document_id"),
                    "vector_score": None,
                    "bm25_score": None,
                    "fused_score": 0.0,
                },
            )
            entry[score_key] = hit["score"]
            entry["fused_score"] += 1.0 / (k + rank)

    ingest(vector_hits, "vector_score")
    ingest(bm25_hits, "bm25_score")

    return sorted(merged.values(), key=lambda x: x["fused_score"], reverse=True)
