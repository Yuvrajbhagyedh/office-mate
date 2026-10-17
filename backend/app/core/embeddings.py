"""Embedding generation.

Providers:
  * local  — sentence-transformers (heavy; needs RAM for torch)
  * google — Gemini Embedding API (fits free-tier hosts like Render 512MB)
"""
from __future__ import annotations

import math
import threading
import time
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
    """Gemini Embedding API — no local torch / sentence-transformers.

    Documents go through batchEmbedContents (up to 100 texts per request) over
    one reused connection, so a 100-chunk PDF is one round trip instead of 100.
    """

    _BASE = "https://generativelanguage.googleapis.com/v1beta/models"
    _RETRY_STATUSES = (429, 500, 503)

    def __init__(self, api_key: Optional[str], model: str, dim: int, batch_size: int = 100):
        self._api_key = (api_key or "").strip()
        model = model or "gemini-embedding-001"
        self._model = model[len("models/") :] if model.startswith("models/") else model
        self._dim = dim
        self._batch_size = max(1, min(batch_size, 100))
        self._client: Optional[httpx.Client] = None
        self._lock = threading.Lock()

    @property
    def dim(self) -> int:
        return self._dim

    def _require_key(self) -> str:
        if not self._api_key or "REPLACE" in self._api_key.upper():
            raise RuntimeError(
                "GOOGLE_API_KEY is required for Google embeddings. Set it in the environment."
            )
        return self._api_key

    def _http(self) -> httpx.Client:
        # httpx.Client is thread-safe and keeps the TLS connection alive between
        # calls, which saves a handshake on every question.
        if self._client is None:
            with self._lock:
                if self._client is None:
                    self._client = httpx.Client(timeout=60.0)
        return self._client

    def _request(self, text: str, task_type: str) -> dict:
        return {
            "model": f"models/{self._model}",
            "content": {"parts": [{"text": text}]},
            "taskType": task_type,
            "outputDimensionality": self._dim,
        }

    def _post(self, method: str, payload: dict) -> dict:
        key = self._require_key()
        url = f"{self._BASE}/{self._model}:{method}"
        for attempt in range(3):
            resp = self._http().post(
                url,
                headers={"Content-Type": "application/json", "x-goog-api-key": key},
                json=payload,
            )
            if resp.status_code in self._RETRY_STATUSES and attempt < 2:
                logger.warning(
                    "Google embedding busy; retrying",
                    extra={"extra": {"status": resp.status_code, "attempt": attempt + 1}},
                )
                time.sleep(2.0 * (attempt + 1))
                continue
            if resp.status_code >= 400:
                raise RuntimeError(
                    f"Google embedding error {resp.status_code}: {resp.text[:400]}"
                )
            return resp.json()
        raise RuntimeError("Google embedding unavailable")  # unreachable

    @staticmethod
    def _values(embedding: dict) -> List[float]:
        values = (embedding or {}).get("values")
        if not values:
            raise RuntimeError(f"Unexpected embedding response: {embedding}")
        return _l2_normalize([float(v) for v in values])

    def embed_documents(self, texts: List[str], batch_size: Optional[int] = None) -> List[List[float]]:
        size = max(1, min(batch_size or self._batch_size, 100))
        vectors: List[List[float]] = []
        for i in range(0, len(texts), size):
            batch = texts[i : i + size]
            data = self._post(
                "batchEmbedContents",
                {"requests": [self._request(t, "RETRIEVAL_DOCUMENT") for t in batch]},
            )
            embeddings = data.get("embeddings") or []
            if len(embeddings) != len(batch):
                raise RuntimeError(
                    f"Google returned {len(embeddings)} embeddings for {len(batch)} texts"
                )
            vectors.extend(self._values(e) for e in embeddings)
        return vectors

    def embed_query(self, text: str) -> List[float]:
        data = self._post("embedContent", self._request(text, "RETRIEVAL_QUERY"))
        return self._values(data.get("embedding"))


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
        batch_size=settings.embedding_batch_size,
    )


embedder = build_embedder()
