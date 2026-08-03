"""Reranking.

Cross-encoder mode needs sentence-transformers/torch (heavy).
Identity mode reuses hybrid fused scores — fits free-tier hosts.
"""
from __future__ import annotations

import threading
from typing import List

from ..config import settings
from ..logging_config import get_logger

logger = get_logger(__name__)


class Reranker:
    def __init__(self, model_name: str, device: str, enabled: bool):
        self._model_name = model_name
        self._device = device
        self._enabled = enabled
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
            # Keep hybrid-fusion order; treat fused_score as rerank_score.
            ranked = sorted(
                candidates,
                key=lambda c: float(c.get("fused_score") or c.get("vector_score") or 0.0),
                reverse=True,
            )
            out = ranked[:top_n]
            for c in out:
                c["rerank_score"] = float(c.get("fused_score") or c.get("vector_score") or 0.0)
            return out

        model = self._ensure_model()
        pairs = [(query, c["text"]) for c in candidates]
        scores = model.predict(pairs, show_progress_bar=False)
        for c, s in zip(candidates, scores):
            c["rerank_score"] = float(s)
        kept = [c for c in candidates if c["rerank_score"] >= min_score]
        kept.sort(key=lambda x: x["rerank_score"], reverse=True)
        return kept[:top_n]


reranker = Reranker(
    model_name=settings.reranker_model,
    device=settings.embedding_device,
    enabled=settings.reranker_enabled,
)
