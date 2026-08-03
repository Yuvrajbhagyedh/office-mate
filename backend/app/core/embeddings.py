"""Embedding generation via a local sentence-transformers model.

Local embeddings are free, private, and offline-capable. The model is loaded
once (lazily) and reused. bge-family models expect an instruction prefix on the
*query* side only — we handle that asymmetry here so callers don't have to
remember it.
"""
from __future__ import annotations

import threading
from typing import List

from ..config import settings
from ..logging_config import get_logger

logger = get_logger(__name__)


class Embedder:
    def __init__(self, model_name: str, device: str, query_prefix: str):
        self._model_name = model_name
        self._device = device
        self._query_prefix = query_prefix
        self._model = None
        self._lock = threading.Lock()

    def _ensure_model(self):
        if self._model is None:
            with self._lock:
                if self._model is None:
                    from sentence_transformers import SentenceTransformer

                    logger.info(
                        "Loading embedding model",
                        extra={"extra": {"model": self._model_name, "device": self._device}},
                    )
                    self._model = SentenceTransformer(self._model_name, device=self._device)
        return self._model

    @property
    def dim(self) -> int:
        return self._ensure_model().get_sentence_embedding_dimension()

    def embed_documents(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        model = self._ensure_model()
        vectors = model.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=True,  # cosine == dot product on normalized vectors
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return vectors.tolist()

    def embed_query(self, text: str) -> List[float]:
        model = self._ensure_model()
        vector = model.encode(
            self._query_prefix + text,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return vector.tolist()


embedder = Embedder(
    model_name=settings.embedding_model,
    device=settings.embedding_device,
    query_prefix=settings.embedding_query_prefix,
)
