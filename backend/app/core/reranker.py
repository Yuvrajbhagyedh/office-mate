"""Reranking.

Cross-encoder mode needs sentence-transformers/torch (heavy).
Identity mode reuses hybrid fused scores — fits free-tier hosts. It still
applies an evidence gate: chunks must be semantically close to the question
(cosine >= MIN_VECTOR_SCORE), so an off-topic question gets no context and
the pipeline refuses without calling the LLM.
"""
from __future__ import annotations

import threading
from typing import List

from ..config import settings
from ..logging_config import get_logger

logger = get_logger(__name__)


class Reranker:
    def __init__(self, model_name: str, device: str, enabled: bool, min_vector_score: float = 0.0):
        self._model_name = model_name
        self._device = device
        self._enabled = enabled
        self._min_vector_score = min_vector_score
        self._model = None
        self._lock = threading.Lock()

    def _ensure_model(self):
        if self._model is None:
            with self._lock:
                if self._model is None:
                    from sentence_transformers import CrossEncoder

                    logger.info(
                        "Loading reranker model",
                        extra={"extra": {"model": self._model_name}},
                    )
                    self._model = CrossEncoder(self._model_name, device=self._device)
        return self._model

    def rerank(self, query: str, candidates: List[dict], top_n: int, min_score: float) -> List[dict]:
        if not candidates:
            return []

        if not self._enabled:
            return self._gate_without_model(candidates, top_n)

        model = self._ensure_model()
        pairs = [(query, c["text"]) for c in candidates]
        scores = model.predict(pairs, show_progress_bar=False)
        for c, s in zip(candidates, scores):
            c["rerank_score"] = float(s)
        kept = [c for c in candidates if c["rerank_score"] >= min_score]
        kept.sort(key=lambda x: x["rerank_score"], reverse=True)
        return kept[:top_n]

    def _gate_without_model(self, candidates: List[dict], top_n: int) -> List[dict]:
        """Keep hybrid-fusion order, but only when the question is on-topic.

        BM25 matches any shared word ("how", "do", "i"), so it cannot prove
        relevance on its own. The gate therefore needs at least one chunk with a
        strong vector score; once the topic is confirmed, keyword-only hits are
        allowed through because exact terms (codes, names) are BM25's job.
        """
        threshold = self._min_vector_score

        def vec(c: dict) -> float:
            return float(c["vector_score"]) if c.get("vector_score") is not None else float("-inf")

        if not any(vec(c) >= threshold for c in candidates):
            return []
        kept = [
            c for c in candidates
            if vec(c) >= threshold or c.get("vector_score") is None
        ]
        kept.sort(key=lambda c: float(c.get("fused_score") or 0.0), reverse=True)
        out = kept[:top_n]
        for c in out:
            c["rerank_score"] = float(c.get("fused_score") or 0.0)
        return out


reranker = Reranker(
    model_name=settings.reranker_model,
    device=settings.embedding_device,
    enabled=settings.reranker_enabled,
    min_vector_score=settings.min_vector_score,
)
