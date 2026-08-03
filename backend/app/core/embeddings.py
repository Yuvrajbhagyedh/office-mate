"""Embedding generation.

Providers:
  * local  — sentence-transformers (heavy; needs RAM for torch)
  * google — Gemini Embedding API (fits free-tier hosts like Render 512MB)
"""
from __future__ import annotations

import math
import threading
from typing import List, Optional

import httpx

from ..config import settings
from ..logging_config import get_logger

logger = get_logger(__name__)


def _l2_normalize(vec: List[float]) -> List[float]:
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


class LocalEmbedder:
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
        return int(self._ensure_model().get_sentence_embedding_dimension())

    def embed_documents(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        model = self._ensure_model()
        vectors = model.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=True,
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


class GoogleEmbedder:
    """Gemini Embedding API — no local torch / sentence-transformers."""

    def __init__(self, api_key: Optional[str], model: str, dim: int):
        self._api_key = (api_key or "").strip()
        self._model = model
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    def _require_key(self) -> str:
        if not self._api_key or "REPLACE" in self._api_key.upper():
            raise RuntimeError(
                "GOOGLE_API_KEY is required for Google embeddings. Set it in the environment."
            )
        return self._api_key

    def _embed_one(self, text: str, task_type: str) -> List[float]:
        key = self._require_key()
        model = self._model
        if model.startswith("models/"):
            model = model[len("models/") :]
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:embedContent"
        payload = {
            "model": f"models/{model}",
            "content": {"parts": [{"text": text}]},
            "taskType": task_type,
            "outputDimensionality": self._dim,
        }
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(
                url,
                headers={"Content-Type": "application/json", "x-goog-api-key": key},
                json=payload,
            )
        if resp.status_code >= 400:
            raise RuntimeError(f"Google embedding error {resp.status_code}: {resp.text[:400]}")
        data = resp.json()
        values = data.get("embedding", {}).get("values")
        if not values:
            raise RuntimeError(f"Unexpected embedding response: {data}")
        return _l2_normalize([float(v) for v in values])

    def embed_documents(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        # Simple sequential calls — fine for small office corpora on free tier.
        return [self._embed_one(t, "RETRIEVAL_DOCUMENT") for t in texts]

    def embed_query(self, text: str) -> List[float]:
        return self._embed_one(text, "RETRIEVAL_QUERY")


def build_embedder():
    provider = (settings.embedding_provider or "google").strip().lower()
    if provider == "local":
        return LocalEmbedder(
            model_name=settings.embedding_model,
            device=settings.embedding_device,
            query_prefix=settings.embedding_query_prefix,
        )
    return GoogleEmbedder(
        api_key=settings.google_api_key or settings.gemini_api_key or settings.llm_api_key,
        model=settings.embedding_model or "gemini-embedding-001",
        dim=settings.embedding_dim,
    )


embedder = build_embedder()
