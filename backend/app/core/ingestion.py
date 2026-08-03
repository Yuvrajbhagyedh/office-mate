"""Document ingestion: raw file bytes -> list of (text, provenance) segments.

Each supported format is extracted into *segments* that carry provenance:
    - PDF  -> one segment per page   (page number preserved)
    - DOCX -> segments split on headings (section title preserved)
    - MD   -> segments split on '#' headings (section title preserved)
    - TXT  -> a single segment

Chunking happens later (preprocessing.py). Keeping extraction and chunking
separate means we retain page/section info to attach to every chunk, which is
what makes citations precise.
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from typing import List, Optional

from pypdf import PdfReader


@dataclass
class Segment:
    text: str
    page: Optional[int] = None
    section: Optional[str] = None


SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".markdown"}


class UnsupportedFileType(Exception):
    pass


def extract_segments(filename: str, data: bytes) -> List[Segment]:
    ext = _ext(filename)
    if ext == ".pdf":
        return _extract_pdf(data)
    if ext == ".docx":
        return _extract_docx(data)
    if ext in {".md", ".markdown"}:
        return _extract_markdown(data)
    if ext == ".txt":
        return _extract_txt(data)
    raise UnsupportedFileType(f"Unsupported file type: {ext}")


def _ext(filename: str) -> str:
    dot = filename.rfind(".")
    return filename[dot:].lower() if dot != -1 else ""


def _extract_pdf(data: bytes) -> List[Segment]:
    reader = PdfReader(io.BytesIO(data))
    segments: List[Segment] = []
    for i, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if text.strip():
            segments.append(Segment(text=text, page=i))
    return segments


def _extract_docx(data: bytes) -> List[Segment]:
    # Imported lazily so the dependency is only needed when a .docx is uploaded.
    import docx  # python-docx

    document = docx.Document(io.BytesIO(data))
    segments: List[Segment] = []
    current_section: Optional[str] = None
    buffer: List[str] = []

    def flush() -> None:
        if buffer:
            segments.append(Segment(text="\n".join(buffer), section=current_section))
            buffer.clear()

    for para in document.paragraphs:
        style = (para.style.name or "").lower() if para.style else ""
        if style.startswith("heading") and para.text.strip():
            flush()
            current_section = para.text.strip()
            buffer.append(para.text)
        elif para.text.strip():
            buffer.append(para.text)
    flush()
    return segments


def _extract_markdown(data: bytes) -> List[Segment]:
    text = data.decode("utf-8", errors="replace")
    segments: List[Segment] = []
    current_section: Optional[str] = None
    buffer: List[str] = []

    def flush() -> None:
        if buffer:
            segments.append(Segment(text="\n".join(buffer), section=current_section))
            buffer.clear()

    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            flush()
            current_section = line.lstrip("#").strip()
        buffer.append(line)
    flush()
    return segments


def _extract_txt(data: bytes) -> List[Segment]:
    text = data.decode("utf-8", errors="replace")
    return [Segment(text=text)] if text.strip() else []
