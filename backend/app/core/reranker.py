"""Cross-encoder reranking.

The hybrid retriever is a *bi-encoder* stage: fast, but it scores query and
passage independently. A cross-encoder reads the (query, passage) pair jointly
and produces a far more accurate relevance score — at higher cost, which is why
we only run it on the ~40 fused candidates, not the whole corpus.

Reranking is where most of the end-to-end quality gain comes from: it pushes
the genuinely-relevant chunk to the top and filters out topically-adjacent but
unhelpful passages, which in turn reduces hallucination because the LLM sees a
tighter, higher-signal context.

Chunks scoring below `min_rerank_score` are dropped entirely. If nothing clears
the bar, we return an empty list and the pipeline tells the model there is no
supporting evidence — the core anti-fabrication guarantee.
"""
from __future__ import annotations

import threading
from typing import List

from ..config import settings
from ..logging_config import get_logger

logger = get_logger(__name__)


class Reranker:
    def __init__(self, model_name: str, device: str):
        self._model_name = model_name
        self._device = device
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
        model = self._ensure_model()
        pairs = [(query, c["text"]) for c in candidates]
        scores = model.predict(pairs, show_progress_bar=False)
        for c, s in zip(candidates, scores):
            c["rerank_score"] = float(s)
        kept = [c for c in candidates if c["rerank_score"] >= min_score]
        kept.sort(key=lambda x: x["rerank_score"], reverse=True)
        return kept[:top_n]


reranker = Reranker(model_name=settings.reranker_model, device=settings.embedding_device)
