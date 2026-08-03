"""Tests for RRF fusion and citation extraction — pure logic."""
from app.core.retrieval import _reciprocal_rank_fusion


def test_rrf_rewards_agreement_across_retrievers():
    # chunk "a" is top of BOTH lists -> should win.
    vector = [{"chunk_id": "a", "document_id": "d", "score": 0.9},
              {"chunk_id": "b", "document_id": "d", "score": 0.8}]
    bm25 = [{"chunk_id": "a", "document_id": "d", "score": 5.0},
            {"chunk_id": "c", "document_id": "d", "score": 4.0}]
    fused = _reciprocal_rank_fusion(vector, bm25, k=60)
    assert fused[0]["chunk_id"] == "a"
    # "a" carries both sub-scores
    assert fused[0]["vector_score"] == 0.9
    assert fused[0]["bm25_score"] == 5.0


def test_rrf_includes_union_of_candidates():
    vector = [{"chunk_id": "a", "document_id": "d", "score": 0.9}]
    bm25 = [{"chunk_id": "b", "document_id": "d", "score": 5.0}]
    fused = _reciprocal_rank_fusion(vector, bm25, k=60)
    ids = {f["chunk_id"] for f in fused}
    assert ids == {"a", "b"}


def test_citation_extraction_maps_markers_to_sources():
    from app.core.pipeline import _extract_citations

    ordered = [
        {"document_id": "d1", "filename": "a.pdf", "page": 2, "section": None},
        {"document_id": "d2", "filename": "b.md", "page": None, "section": "Intro"},
    ]
    answer = "The limit is 100 rps [1] and webhooks use HMAC [2]."
    cites = _extract_citations(answer, ordered)
    assert [c.marker for c in cites] == [1, 2]
    assert cites[0].filename == "a.pdf" and cites[0].page == 2
    assert cites[1].filename == "b.md" and cites[1].section == "Intro"


def test_citation_extraction_ignores_out_of_range_markers():
    from app.core.pipeline import _extract_citations

    ordered = [{"document_id": "d1", "filename": "a.pdf", "page": 1, "section": None}]
    cites = _extract_citations("nonsense [5]", ordered)
    assert cites == []


def test_refusal_detection():
    from app.core.pipeline import _is_grounded
    from app.core.prompt import REFUSAL_PHRASE

    assert _is_grounded("Revenue was $5M [1].") is True
    assert _is_grounded(REFUSAL_PHRASE) is False
    assert _is_grounded(REFUSAL_PHRASE.upper()) is False
