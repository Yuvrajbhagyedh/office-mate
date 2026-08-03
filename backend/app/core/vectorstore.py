"""Qdrant vector store wrapper.

Encapsulates all Qdrant specifics behind a small interface (ensure_collection,
upsert, search, delete_document) so the rest of the app never imports the
Qdrant client directly. Swapping the vector DB is therefore a single-file
change.

Chunks live in one collection; the owning document is stored in the payload so
we can (a) filter a search to a subset of documents and (b) delete a
document's vectors on demand.
"""
from __future__ import annotations

from typing import List, Optional

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from ..config import settings
from ..logging_config import get_logger

logger = get_logger(__name__)


class VectorStore:
    def __init__(
        self,
        collection: str,
        dim: int,
        url: Optional[str] = None,
        api_key: Optional[str] = None,
        local_path: Optional[str] = None,
    ):
        # Embedded mode (local_path) needs no running server — Qdrant runs
        # in-process and persists to disk. Otherwise connect to a server.
        if local_path:
            from pathlib import Path

            Path(local_path).mkdir(parents=True, exist_ok=True)
            logger.info("Using embedded Qdrant", extra={"extra": {"path": local_path}})
            self._client = QdrantClient(path=local_path)
        else:
            self._client = QdrantClient(url=url, api_key=api_key, timeout=30)
        self._collection = collection
        self._dim = dim

    def ensure_collection(self) -> None:
        existing = {c.name for c in self._client.get_collections().collections}
        if self._collection not in existing:
            logger.info(
                "Creating Qdrant collection",
                extra={"extra": {"collection": self._collection, "dim": self._dim}},
            )
            self._client.create_collection(
                collection_name=self._collection,
                vectors_config=qm.VectorParams(size=self._dim, distance=qm.Distance.COSINE),
            )
            # Index the document_id payload field so filtered search is fast.
            # Embedded mode filters without an explicit index, so a failure here
            # is non-fatal.
            try:
                self._client.create_payload_index(
                    collection_name=self._collection,
                    field_name="document_id",
                    field_schema=qm.PayloadSchemaType.KEYWORD,
                )
            except Exception:  # noqa: BLE001
                logger.info("Skipping payload index (embedded mode)")

    def upsert(self, chunk_ids: List[str], vectors: List[List[float]], payloads: List[dict]) -> None:
        points = [
            qm.PointStruct(id=cid, vector=vec, payload=payload)
            for cid, vec, payload in zip(chunk_ids, vectors, payloads)
        ]
        self._client.upsert(collection_name=self._collection, points=points, wait=True)

    def search(
        self, query_vector: List[float], top_k: int, document_ids: Optional[List[str]] = None
    ) -> List[dict]:
        flt = None
        if document_ids:
            flt = qm.Filter(
                must=[
                    qm.FieldCondition(
                        key="document_id", match=qm.MatchAny(any=document_ids)
                    )
                ]
            )
        hits = self._client.search(
            collection_name=self._collection,
            query_vector=query_vector,
            limit=top_k,
            query_filter=flt,
            with_payload=True,
        )
        return [{"chunk_id": str(h.id), "score": float(h.score), **h.payload} for h in hits]

    def delete_document(self, document_id: str) -> None:
        self._client.delete(
            collection_name=self._collection,
            points_selector=qm.FilterSelector(
                filter=qm.Filter(
                    must=[qm.FieldCondition(key="document_id", match=qm.MatchValue(value=document_id))]
                )
            ),
            wait=True,
        )

    def health(self) -> str:
        try:
            self._client.get_collections()
            return "ok"
        except Exception as exc:  # noqa: BLE001
            return f"unreachable: {exc}"


vector_store = VectorStore(
    collection=settings.qdrant_collection,
    dim=settings.embedding_dim,
    url=settings.qdrant_url,
    api_key=settings.qdrant_api_key,
    local_path=settings.qdrant_local_path,
)
