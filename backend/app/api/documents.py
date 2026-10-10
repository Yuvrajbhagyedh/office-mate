"""Document management endpoints: upload, list, delete (admin only)."""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile

from ..config import settings
from ..core import pipeline
from ..core.auth import require_admin
from ..core.ingestion import SUPPORTED_EXTENSIONS
from ..deps import registry
from ..logging_config import get_logger
from ..schemas import DocumentListResponse, UploadResponse
from ..storage.users import UserRecord

logger = get_logger(__name__)
router = APIRouter(prefix="/api/documents", tags=["documents"])


def _ext(filename: str) -> str:
    dot = filename.rfind(".")
    return filename[dot:].lower() if dot != -1 else ""


# Plain `def`: ingestion makes blocking embedding calls, so it runs in the
# threadpool rather than blocking the event loop for other requests.
@router.post("", response_model=UploadResponse, status_code=201)
def upload_document(
    _: Annotated[UserRecord, Depends(require_admin)],
    file: UploadFile = File(...),
) -> UploadResponse:
    filename = file.filename or "upload"
    ext = _ext(filename)
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported type '{ext}'. Allowed: {sorted(SUPPORTED_EXTENSIONS)}",
        )

    data = file.file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds {settings.max_upload_mb} MB limit.",
        )

    doc_id = str(uuid.uuid4())
    registry.create_document(doc_id, filename, ext.lstrip("."), len(data))

    try:
        pipeline.ingest_document(doc_id, filename, data)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"Failed to process document: {exc}")

    meta = registry.get_document(doc_id)
    assert meta is not None
    return UploadResponse(document=meta)


@router.get("", response_model=DocumentListResponse)
async def list_documents(_: Annotated[UserRecord, Depends(require_admin)]) -> DocumentListResponse:
    return DocumentListResponse(documents=registry.list_documents())


@router.delete("/{document_id}", status_code=204, response_class=Response)
def delete_document(
    document_id: str,
    _: Annotated[UserRecord, Depends(require_admin)],
) -> Response:
    if not pipeline.delete_document(document_id):
        raise HTTPException(status_code=404, detail="Document not found.")
    return Response(status_code=204)
