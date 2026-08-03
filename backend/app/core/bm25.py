"""BM25 keyword index.

Vector search captures semantic similarity but misses exact-term matches
(product codes, names, acronyms, rare keywords). BM25 covers that gap. We keep
an in-memory index built from the registry's chunk text; it is cheap to rebuild
and is refreshed whenever documents change.

For very large corpora this would move to a dedicated engine (Elasticsearch /
OpenSearch); the interface here is intentionally the same shape so that swap is
localized.
"""
from __future__ import annotations

import re
import threading
from typing import List, Optional

from rank_bm25 import BM25Okapi

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> List[str]:
    return _TOKEN_RE.findall(text.lower())


class BM25Index:
    def __init__(self):
        self._lock = threading.Lock()
        self._bm25: Optional[BM25Okapi] = None
        self._chunk_ids: List[str] = []
        self._doc_ids: List[str] = []

    def build(self, chunks: List[dict]) -> None:
        """chunks: list of registry rows with keys id, document_id, text."""
        with self._lock:
            if not chunks:
                self._bm25, self._chunk_ids, self._doc_ids = None, [], []
                return
            corpus = [tokenize(c["text"]) for c in chunks]
            self._bm25 = BM25Okapi(corpus)
            self._chunk_ids = [c["id"] for c in chunks]
            self._doc_ids = [c["document_id"] for c in chunks]

    def search(
        self, query: str, top_k: int, document_ids: Optional[List[str]] = None
    ) -> List[dict]:
        with self._lock:
            if self._bm25 is None:
                return []
            scores = self._bm25.get_scores(tokenize(query))
            allow = set(document_ids) if document_ids else None
            ranked = sorted(
                (
                    {"chunk_id": self._chunk_ids[i], "document_id": self._doc_ids[i], "score": float(s)}
                    for i, s in enumerate(scores)
                    if s > 0 and (allow is None or self._doc_ids[i] in allow)
                ),
                key=lambda x: x["score"],
                reverse=True,
            )
            return ranked[:top_k]


bm25_index = BM25Index()
