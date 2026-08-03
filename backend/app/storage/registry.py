"""Document & chunk registry backed by SQLite.

Responsibilities:
* Track document lifecycle (processing -> ready/failed) and metadata.
* Persist chunk text + provenance (page/section) so we can (a) rebuild the
  BM25 index on startup and (b) return the exact source text for citations
  without a round-trip to the vector store.

SQLite is deliberate: it is zero-infra, transactional, and more than enough
for single-node deployments. The access layer is small and isolated, so
swapping to Postgres later is a contained change (see ARCHITECTURE.md).
"""
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from ..schemas import DocumentMeta


class Registry:
    def __init__(self, db_path: str):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False + a lock: FastAPI runs handlers across a
        # threadpool; we serialize writes ourselves.
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock, self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    filetype TEXT NOT NULL,
                    status TEXT NOT NULL,
                    num_chunks INTEGER NOT NULL DEFAULT 0,
                    size_bytes INTEGER NOT NULL DEFAULT 0,
                    processing_time_ms REAL,
                    error TEXT,
                    uploaded_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS chunks (
                    id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    page INTEGER,
                    section TEXT,
                    text TEXT NOT NULL,
                    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(document_id);
                """
            )

    # ---- documents ----
    def create_document(
        self, doc_id: str, filename: str, filetype: str, size_bytes: int
    ) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO documents (id, filename, filetype, status, size_bytes, uploaded_at) "
                "VALUES (?, ?, ?, 'processing', ?, ?)",
                (doc_id, filename, filetype, size_bytes, datetime.now(timezone.utc).isoformat()),
            )

    def mark_ready(self, doc_id: str, num_chunks: int, processing_time_ms: float) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE documents SET status='ready', num_chunks=?, processing_time_ms=? WHERE id=?",
                (num_chunks, processing_time_ms, doc_id),
            )

    def mark_failed(self, doc_id: str, error: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE documents SET status='failed', error=? WHERE id=?", (error, doc_id)
            )

    def get_document(self, doc_id: str) -> Optional[DocumentMeta]:
        cur = self._conn.execute("SELECT * FROM documents WHERE id=?", (doc_id,))
        row = cur.fetchone()
        return self._row_to_meta(row) if row else None

    def list_documents(self) -> List[DocumentMeta]:
        cur = self._conn.execute("SELECT * FROM documents ORDER BY uploaded_at DESC")
        return [self._row_to_meta(r) for r in cur.fetchall()]

    def delete_document(self, doc_id: str) -> bool:
        with self._lock, self._conn:
            cur = self._conn.execute("DELETE FROM documents WHERE id=?", (doc_id,))
            self._conn.execute("DELETE FROM chunks WHERE document_id=?", (doc_id,))
            return cur.rowcount > 0

    # ---- chunks ----
    def add_chunks(self, chunks: List[dict]) -> None:
        """chunks: list of {id, document_id, chunk_index, page, section, text}"""
        with self._lock, self._conn:
            self._conn.executemany(
                "INSERT INTO chunks (id, document_id, chunk_index, page, section, text) "
                "VALUES (:id, :document_id, :chunk_index, :page, :section, :text)",
                chunks,
            )

    def all_chunks(self, document_ids: Optional[List[str]] = None) -> List[dict]:
        if document_ids:
            placeholders = ",".join("?" for _ in document_ids)
            cur = self._conn.execute(
                f"SELECT * FROM chunks WHERE document_id IN ({placeholders})", document_ids
            )
        else:
            cur = self._conn.execute("SELECT * FROM chunks")
        return [dict(r) for r in cur.fetchall()]

    def get_chunk(self, chunk_id: str) -> Optional[dict]:
        cur = self._conn.execute("SELECT * FROM chunks WHERE id=?", (chunk_id,))
        row = cur.fetchone()
        return dict(row) if row else None

    def counts(self) -> tuple[int, int]:
        d = self._conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        c = self._conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        return d, c

    @staticmethod
    def _row_to_meta(row: sqlite3.Row) -> DocumentMeta:
        return DocumentMeta(
            id=row["id"],
            filename=row["filename"],
            filetype=row["filetype"],
            status=row["status"],
            num_chunks=row["num_chunks"],
            size_bytes=row["size_bytes"],
            processing_time_ms=row["processing_time_ms"],
            error=row["error"],
            uploaded_at=datetime.fromisoformat(row["uploaded_at"]),
        )
