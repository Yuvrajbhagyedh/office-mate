"""Cleaning + chunking.

Cleaning removes boilerplate noise (repeated whitespace, control chars,
hyphenation artifacts from PDF extraction) without destroying meaning.

Chunking uses a recursive, boundary-aware splitter: it prefers to break on
paragraph, then sentence, then word boundaries, targeting `chunk_size`
characters with `chunk_overlap` characters of overlap between neighbours.
Overlap preserves context that would otherwise be severed at a chunk edge,
which measurably improves recall for questions whose answer straddles a
boundary (see ARCHITECTURE.md -> "Chunking strategy").

Every emitted chunk inherits the page/section of its source segment, so
provenance survives all the way to the citation.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import List, Optional

from .ingestion import Segment

_WS_RE = re.compile(r"[ \t\f\v]+")
_MULTINEWLINE_RE = re.compile(r"\n{3,}")
# PDF extractors often split words across line breaks with a hyphen: "inter-\nnational".
_DEHYPHEN_RE = re.compile(r"(\w)-\n(\w)")
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


@dataclass
class Chunk:
    id: str
    text: str
    chunk_index: int
    page: Optional[int]
    section: Optional[str]


def clean_text(text: str) -> str:
    text = _CTRL_RE.sub("", text)
    text = _DEHYPHEN_RE.sub(r"\1\2", text)
    text = _WS_RE.sub(" ", text)
    text = _MULTINEWLINE_RE.sub("\n\n", text)
    return text.strip()


def chunk_segments(
    segments: List[Segment], chunk_size: int, chunk_overlap: int
) -> List[Chunk]:
    chunks: List[Chunk] = []
    idx = 0
    for seg in segments:
        cleaned = clean_text(seg.text)
        if not cleaned:
            continue
        for piece in _split_recursive(cleaned, chunk_size, chunk_overlap):
            chunks.append(
                Chunk(
                    id=str(uuid.uuid4()),
                    text=piece,
                    chunk_index=idx,
                    page=seg.page,
                    section=seg.section,
                )
            )
            idx += 1
    return chunks


def _split_recursive(text: str, size: int, overlap: int) -> List[str]:
    if len(text) <= size:
        return [text]

    # Try successively finer separators.
    for sep in ("\n\n", "\n", ". ", " "):
        parts = _split_keep(text, sep)
        if len(parts) == 1:
            continue
        return _merge_with_overlap(parts, size, overlap)

    # No separator helped (e.g. one giant token) -> hard slice with overlap.
    return _hard_slice(text, size, overlap)


def _split_keep(text: str, sep: str) -> List[str]:
    pieces = text.split(sep)
    # Re-attach the separator so we don't lose sentence/paragraph boundaries.
    return [p + sep for p in pieces[:-1]] + [pieces[-1]] if len(pieces) > 1 else pieces


def _merge_with_overlap(parts: List[str], size: int, overlap: int) -> List[str]:
    chunks: List[str] = []
    current = ""
    for part in parts:
        if len(part) > size:
            # A single part is itself too large — flush and recurse into it.
            if current:
                chunks.append(current.strip())
                current = ""
            chunks.extend(_split_recursive(part, size, overlap))
            continue
        if len(current) + len(part) <= size:
            current += part
        else:
            if current:
                chunks.append(current.strip())
            # Seed the next chunk with the tail of the previous one (overlap).
            tail = current[-overlap:] if overlap and current else ""
            current = tail + part
    if current.strip():
        chunks.append(current.strip())
    return [c for c in chunks if c]


def _hard_slice(text: str, size: int, overlap: int) -> List[str]:
    step = max(1, size - overlap)
    return [text[i : i + size] for i in range(0, len(text), step)]
