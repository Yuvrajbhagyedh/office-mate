"""Tests for the free-tier fixes: evidence gate, batched embeddings, the Gemini
time budget, and startup seeding. No network — HTTP is mocked."""
import json
import time

import httpx
import pytest

from app.core import llm as llm_module
from app.core import pipeline
from app.core.embeddings import GoogleEmbedder
from app.core.llm import GeminiLLM
from app.core.reranker import Reranker


# ---- evidence gate (reranker disabled) ----

def _gate(min_vector_score=0.5):
    return Reranker(model_name="unused", device="cpu", enabled=False, min_vector_score=min_vector_score)


def test_gate_refuses_when_no_chunk_is_semantically_close():
    candidates = [
        {"chunk_id": "a", "vector_score": 0.31, "bm25_score": 4.0, "fused_score": 0.03},
        {"chunk_id": "b", "vector_score": None, "bm25_score": 2.0, "fused_score": 0.02},
    ]
    assert _gate().rerank("q", candidates, top_n=5, min_score=-6) == []


def test_gate_drops_weak_vector_hits_but_keeps_keyword_hits_on_topic():
    candidates = [
        {"chunk_id": "strong", "vector_score": 0.72, "bm25_score": None, "fused_score": 0.016},
        {"chunk_id": "weak", "vector_score": 0.20, "bm25_score": None, "fused_score": 0.015},
        {"chunk_id": "keyword", "vector_score": None, "bm25_score": 6.0, "fused_score": 0.017},
    ]
    out = _gate().rerank("q", candidates, top_n=5, min_score=-6)
    assert [c["chunk_id"] for c in out] == ["keyword", "strong"]
    assert all("rerank_score" in c for c in out)


def test_gate_respects_top_n():
    candidates = [
        {"chunk_id": str(i), "vector_score": 0.9, "bm25_score": None, "fused_score": 1.0 / (i + 1)}
        for i in range(10)
    ]
    out = _gate().rerank("q", candidates, top_n=3, min_score=-6)
    assert [c["chunk_id"] for c in out] == ["0", "1", "2"]


# ---- batched Google embeddings ----

def _embedder_with(handler, batch_size=100):
    emb = GoogleEmbedder(api_key="test-key", model="models/gemini-embedding-001", dim=3, batch_size=batch_size)
    emb._client = httpx.Client(transport=httpx.MockTransport(handler))
    return emb


def test_embed_documents_batches_requests():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append((request.url.path, len(body["requests"])))
        return httpx.Response(200, json={"embeddings": [{"values": [3.0, 0.0, 4.0]}] * len(body["requests"])})

    emb = _embedder_with(handler, batch_size=100)
    vectors = emb.embed_documents([f"chunk {i}" for i in range(250)])

    assert len(vectors) == 250
    assert calls == [
        ("/v1beta/models/gemini-embedding-001:batchEmbedContents", 100),
        ("/v1beta/models/gemini-embedding-001:batchEmbedContents", 100),
        ("/v1beta/models/gemini-embedding-001:batchEmbedContents", 50),
    ]
    assert vectors[0] == pytest.approx([0.6, 0.0, 0.8])  # L2-normalized


def test_embed_query_uses_single_endpoint(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith(":embedContent")
        assert json.loads(request.content)["taskType"] == "RETRIEVAL_QUERY"
        return httpx.Response(200, json={"embedding": {"values": [1.0, 0.0, 0.0]}})

    assert _embedder_with(handler).embed_query("leave?") == pytest.approx([1.0, 0.0, 0.0])


def test_embed_retries_when_busy(monkeypatch):
    monkeypatch.setattr("app.core.embeddings.time.sleep", lambda s: None)
    statuses = iter([503, 200])

    def handler(request: httpx.Request) -> httpx.Response:
        status = next(statuses)
        if status == 503:
            return httpx.Response(503, text="busy")
        return httpx.Response(200, json={"embeddings": [{"values": [1.0, 0.0, 0.0]}]})

    assert len(_embedder_with(handler).embed_documents(["x"])) == 1


# ---- Gemini time budget ----

def _patch_gemini_http(monkeypatch, handler):
    real_client = httpx.Client
    monkeypatch.setattr(
        llm_module.httpx, "Client", lambda *a, **kw: real_client(transport=httpx.MockTransport(handler))
    )


def test_gemini_gives_up_after_bounded_attempts(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(503, text="overloaded")

    _patch_gemini_http(monkeypatch, handler)
    monkeypatch.setattr(llm_module.time, "sleep", lambda s: None)

    with pytest.raises(RuntimeError, match="busy"):
        GeminiLLM(api_key="test-key", model="gemini-flash-latest", max_tokens=10, timeout_seconds=30).generate("s", "u")
    models = len(GeminiLLM(api_key="k", model="gemini-flash-latest", max_tokens=1)._model_candidates())
    assert len(calls) == models * GeminiLLM._ATTEMPTS_PER_MODEL


def test_gemini_respects_total_deadline(monkeypatch):
    real_sleep = time.sleep

    def slow_busy(request):
        real_sleep(0.4)
        return httpx.Response(503, text="overloaded")

    _patch_gemini_http(monkeypatch, slow_busy)
    monkeypatch.setattr(llm_module.time, "sleep", lambda s: None)

    start = time.monotonic()
    with pytest.raises(RuntimeError, match="busy"):
        GeminiLLM(api_key="test-key", model="gemini-flash-latest", max_tokens=10, timeout_seconds=1.5).generate("s", "u")
    assert time.monotonic() - start < 2.5


def test_gemini_returns_text(monkeypatch):
    def handler(request):
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "24 days [1]"}]}}]})

    _patch_gemini_http(monkeypatch, handler)
    assert GeminiLLM(api_key="test-key", model="gemini-flash-latest", max_tokens=10).generate("s", "u") == "24 days [1]"


# ---- startup seeding ----

class _FakeRegistry:
    def __init__(self, existing=()):
        self.docs = [type("Doc", (), {"filename": name})() for name in existing]
        self.created = []

    def list_documents(self):
        return self.docs

    def create_document(self, doc_id, filename, filetype, size_bytes):
        self.created.append((filename, filetype))


def test_seed_documents_ingests_new_supported_files(tmp_path, monkeypatch):
    (tmp_path / "policy.md").write_text("# Leave\n24 days.")
    (tmp_path / "already.txt").write_text("old")
    (tmp_path / "image.png").write_bytes(b"\x89PNG")
    (tmp_path / "empty.md").write_text("")

    fake = _FakeRegistry(existing=["already.txt"])
    ingested = []
    monkeypatch.setattr(pipeline, "registry", fake)
    monkeypatch.setattr(pipeline, "ingest_document", lambda doc_id, name, data: ingested.append(name))

    assert pipeline.seed_documents(str(tmp_path)) == 1
    assert ingested == ["policy.md"]
    assert fake.created == [("policy.md", "md")]


def test_seed_documents_missing_folder_is_a_no_op(tmp_path):
    assert pipeline.seed_documents(str(tmp_path / "nope")) == 0


# ---- Gemini thinking off ----

def test_gemini_turns_thinking_off_by_default(monkeypatch):
    seen = []

    def handler(request):
        seen.append(json.loads(request.content)["generationConfig"])
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "ok"}]}}]})

    _patch_gemini_http(monkeypatch, handler)
    GeminiLLM(api_key="test-key", model="gemini-flash-latest", max_tokens=10).generate("s", "u")
    assert seen[0]["thinkingConfig"] == {"thinkingBudget": 0}


def test_gemini_retries_without_thinking_config_when_unsupported(monkeypatch):
    seen = []

    def handler(request):
        config = json.loads(request.content)["generationConfig"]
        seen.append("thinkingConfig" in config)
        if "thinkingConfig" in config:
            return httpx.Response(400, text='{"error": {"message": "Thinking is not supported by this model."}}')
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "ok"}]}}]})

    _patch_gemini_http(monkeypatch, handler)
    llm = GeminiLLM(api_key="test-key", model="gemini-2.0-flash", max_tokens=10)
    assert llm.generate("s", "u") == "ok"
    assert seen == [True, False]
    assert llm.model == "gemini-2.0-flash"


def test_gemini_negative_budget_leaves_model_default(monkeypatch):
    seen = []

    def handler(request):
        seen.append(json.loads(request.content)["generationConfig"])
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "ok"}]}}]})

    _patch_gemini_http(monkeypatch, handler)
    GeminiLLM(api_key="test-key", model="gemini-flash-latest", max_tokens=10, thinking_budget=-1).generate("s", "u")
    assert "thinkingConfig" not in seen[0]
