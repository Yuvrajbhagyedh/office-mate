# Architecture & Design Decisions

This document records *why* the system is built the way it is. The guiding
principle is **groundedness**: the assistant must answer only from the user's
documents, cite its sources, and refuse when the evidence is not there.

## 1. Pipeline overview

```
                          INGESTION                              QUERY
  file bytes                                   question
     │                                            │
     ▼                                            ▼
  extract_segments        (page/section)     embed_query
     │                                            │
     ▼                                    ┌────────┴────────┐
  clean + chunk (overlap)                 ▼                 ▼
     │                              vector_search       bm25_search
     ▼                                    └────────┬────────┘
  embed_documents                                  ▼
     │                                    Reciprocal Rank Fusion
     ├──────────────► Qdrant (vectors)             │
     └──────────────► SQLite (text) ──► BM25       ▼
                                             cross-encoder rerank
                                                   │
                                                   ▼
                                      grounded prompt → Claude
                                                   │
                                                   ▼
                                    answer + citations + context + timings
```

Each stage lives in its own module under `app/core/`; `pipeline.py` is the only
place that knows their order. This is what makes the components independently
testable and swappable.

## 2. Why hybrid retrieval (BM25 + vector)?

Dense vector search and sparse keyword search fail in *opposite* ways:

- **Vector search** captures meaning — "how much leave do I get" matches a
  passage about "annual paid time off" with no shared words. But it blurs exact
  tokens: product codes, error numbers, rare names, acronyms.
- **BM25** nails exact terms and is unbeatable for "HTTP 429" or "Idempotency-Key",
  but it is blind to paraphrase.

Real questions need both. Using them together recovers relevant chunks that
either retriever alone would miss, which directly raises retrieval accuracy on
keyword-heavy corpora (APIs, legal, finance, technical docs).

### Why Reciprocal Rank Fusion (RRF) to combine them?

Cosine similarities (~0–1) and BM25 scores (unbounded, corpus-dependent) are not
comparable, so naive score addition is fragile. RRF sidesteps this by fusing
**ranks**, not scores:

```
score(d) = Σ_lists  1 / (k + rank_list(d))          # k = 60 by default
```

It is parameter-light, robust to scale differences, and rewards documents that
*both* retrievers rank highly. See `_reciprocal_rank_fusion` in
`core/retrieval.py`.

## 3. Why cross-encoder reranking?

The retrievers above are **bi-encoders**: query and passage are embedded
separately, so relevance is only approximated. A **cross-encoder** feeds the
`(query, passage)` pair through the model *together* and scores their true
relevance — far more accurate, but too slow to run over the whole corpus.

So we use the classic two-stage design: cheap retrieval narrows thousands of
chunks to ~40 candidates; the expensive cross-encoder reranks *those* and keeps
the top `RERANK_TOP_N` (default 5).

On free hosts (512 MB RAM) the cross-encoder is switched off
(`RERANKER_ENABLED=false`) because torch does not fit. The pipeline then keeps
the fused order but applies an evidence gate instead: at least one chunk must
reach `MIN_VECTOR_SCORE` cosine similarity, weaker vector hits are dropped, and
if nothing qualifies the model is never called and the answer is a refusal.

Reranking is where most end-to-end quality comes from. It matters for
groundedness specifically: by tightening the context to only the highest-signal
chunks, the LLM sees less distracting, topically-adjacent text — which is a
primary cause of hallucination. Chunks scoring below `MIN_RERANK_SCORE` are
dropped; if nothing clears the bar, the pipeline sends **no** context and the
model refuses.

## 4. Chunking strategy

Chunking is a recall/precision trade-off:

- **Too large** → each chunk dilutes the embedding with unrelated content and
  wastes the LLM's context budget.
- **Too small** → the answer gets split across a boundary and no single chunk is
  retrievable.

Choices made (`core/preprocessing.py`):

1. **Boundary-aware recursive splitting.** We split on the largest natural
   separator that fits (`\n\n` → `\n` → `. ` → ` `), so chunks end on paragraph
   or sentence boundaries rather than mid-word. Default target ~900 chars.
2. **Overlap (default 150 chars).** Adjacent chunks share a tail/head window so a
   fact that straddles a boundary still appears whole in at least one chunk. This
   measurably improves recall for boundary-spanning answers.
3. **Provenance carried through.** Extraction (`core/ingestion.py`) keeps PDF
   **page numbers** and DOCX/Markdown **section headings**; every chunk inherits
   them, so a citation can point at "page 4" or "section Rate Limits".

## 5. How hallucinations are minimized

Defense in depth — no single mechanism is trusted:

1. **Retrieval quality** (hybrid + rerank) maximizes the chance the true answer
   is actually in the context.
2. **Hard evidence gate.** If reranking yields nothing above threshold, the model
   is given no context and returns the fixed refusal sentence.
3. **Strict system prompt** (`core/prompt.py`): answer only from context, cite
   every claim, and emit an exact refusal phrase when evidence is insufficient.
4. **Temperature 0** for deterministic, conservative generation.
5. **Citation binding.** `[n]` markers are parsed and mapped back to real source
   chunks (`_extract_citations`); markers outside range are discarded, so a
   citation always corresponds to a chunk that was actually retrieved.
6. **Refusal detection** flips `grounded=false`, surfaced in the UI and counted
   in the `rag_answers_refused_total` metric.
7. **Transparency.** The exact chunks and their scores are returned so a user can
   audit the basis for any answer.

## 6. Observability

- **Structured JSON logs** with a per-request `request_id` contextvar
  (`logging_config.py`) — correlatable across every stage of a request.
- **Per-request trace.** `metrics.Trace` records document processing, embedding,
  vector search, BM25, fusion, rerank, LLM, and total latency; these are returned
  inline in every `/api/ask` response and shown in the UI's context inspector.
- **Prometheus** histograms/counters at `/metrics`: stage latency, request
  latency, throughput, documents/chunks indexed, answers refused.

## 7. Evaluation & CI gate

`eval/evaluate.py` ingests a corpus, runs `eval/benchmark.json` through the real
pipeline, and computes:

| Metric              | Question it answers                                        |
|---------------------|------------------------------------------------------------|
| retrieval_accuracy  | Did we retrieve a chunk from the correct document?         |
| context_precision   | What fraction of the context was actually relevant?        |
| answer_correctness  | Is the answer semantically close to the reference?         |
| citation_accuracy   | Did the answer cite the correct source?                    |
| hallucination_rate  | Did it assert content it shouldn't (incl. failing to refuse)? |

Each metric has a threshold; the harness exits non-zero on a breach, so CI
blocks a regression before it ships. Without an API key it runs in
**retrieval-only** mode (no LLM cost) and still gates retrieval quality; add
`ANTHROPIC_API_KEY` as a secret to gate answer quality too.

## 8. Storage model

- **Qdrant** holds vectors + payload (`document_id`, provenance, text). The
  `document_id` payload index enables filtered search (ask within a subset) and
  per-document deletion.
- **SQLite registry** is the source of truth for document lifecycle
  (`processing → ready/failed`) and stores chunk text so the BM25 index can be
  rebuilt on startup and citations can return exact source text without a vector
  round-trip.

Both are wrapped behind small interfaces (`core/vectorstore.py`,
`storage/registry.py`) so Qdrant→pgvector or SQLite→Postgres is a contained,
single-file change.

## 9. Extensibility (deliberately easy to add later)

The seams were designed so these need no core refactor:

- **Authentication / multi-user.** Add auth middleware; scope documents with an
  `owner_id` column and a Qdrant payload filter. Retrieval already supports
  filtering by `document_ids`.
- **Streaming responses.** `core/llm.py` is the only LLM touch-point; swap
  `messages.create` for the streaming API and stream through a FastAPI
  `StreamingResponse`.
- **Local / alternative LLMs.** Implement the same `generate(system, user)`
  interface in a new class and inject it.
- **Background ingestion at scale.** Upload already models an async
  `processing` state; move `pipeline.ingest_document` onto a task queue
  (Celery/RQ/Arq) and mark ready on completion.
- **Larger keyword search.** Replace the in-memory BM25 with Elasticsearch/
  OpenSearch behind the same `search()` shape.
```
