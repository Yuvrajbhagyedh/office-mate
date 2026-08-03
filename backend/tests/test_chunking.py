"""Tests for cleaning and chunking — pure logic, no external services."""
from app.core.ingestion import Segment
from app.core.preprocessing import chunk_segments, clean_text


def test_clean_dehyphenates_and_collapses_whitespace():
    raw = "inter-\nnational   trade\n\n\n\nmarkets"
    assert clean_text(raw) == "international trade\n\nmarkets"


def test_chunking_respects_size_and_overlap():
    text = " ".join(f"word{i}" for i in range(400))  # well over one chunk
    chunks = chunk_segments([Segment(text=text, page=1)], chunk_size=200, chunk_overlap=40)
    assert len(chunks) > 1
    for c in chunks:
        assert len(c.text) <= 200 + 40  # size plus a small overlap tolerance
        assert c.page == 1  # provenance preserved


def test_chunking_preserves_page_and_section():
    segments = [
        Segment(text="A" * 50, page=3, section="Intro"),
        Segment(text="B" * 50, page=4, section="Body"),
    ]
    chunks = chunk_segments(segments, chunk_size=900, chunk_overlap=100)
    pages = {c.page for c in chunks}
    assert pages == {3, 4}


def test_empty_segments_produce_no_chunks():
    assert chunk_segments([Segment(text="   ")], 900, 100) == []


def test_chunk_indices_are_monotonic():
    text = " ".join(f"tok{i}" for i in range(300))
    chunks = chunk_segments([Segment(text=text)], chunk_size=150, chunk_overlap=30)
    indices = [c.chunk_index for c in chunks]
    assert indices == sorted(indices)
    assert indices[0] == 0
