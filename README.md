# RAG Knowledge Assistant

A production-oriented Retrieval-Augmented Generation system. Upload your own
documents and ask questions in natural language; answers come **only** from the
uploaded material, every claim is **cited**, and the model **refuses** when the
documents don't contain the answer.

```
Upload → Extract → Clean → Chunk (overlap) → Embed → Index (Qdrant + BM25)
Ask → Hybrid retrieve (BM25 + vector, RRF) → Cross-encoder rerank
    → Grounded prompt → Claude → Answer + citations + inspectable context
```

## Highlights

- **Hybrid retrieval** — BM25 keyword search fused with vector similarity via
  Reciprocal Rank Fusion, then **cross-encoder reranking** for precision.
- **Grounded answers with citations** — inline `[n]` markers map to source
  document + page/section. Hard refusal when evidence is insufficient.
- **Every format** — PDF, DOCX, TXT, Markdown, with page/section provenance.
- **Observability built in** — structured JSON logs, per-request tracing of
  every stage, and Prometheus metrics at `/metrics`.
- **Evaluation pipeline** — benchmark dataset + metrics (retrieval accuracy,
  context precision, answer correctness, citation accuracy, hallucination rate)
  wired into CI as a **quality gate**.
- **Reproducible** — one `docker compose up` brings up Qdrant, the API, and the
  web UI.
- **Modular** — ingestion, preprocessing, embeddings, retrieval, reranking,
  prompting, and LLM interaction are each isolated and independently testable.

## Tech stack

| Layer        | Choice                                                    |
|--------------|-----------------------------------------------------------|
| API          | FastAPI                                                   |
| Frontend     | React + Vite                                              |
| Vector DB    | Qdrant                                                    |
| Embeddings   | `BAAI/bge-small-en-v1.5` (local, sentence-transformers)   |
| Reranker     | `cross-encoder/ms-marco-MiniLM-L-6-v2` (local)            |
| Keyword      | BM25 (`rank-bm25`)                                        |
| LLM          | Claude (Anthropic)                                        |
| Registry     | SQLite                                                    |
| Metrics      | Prometheus client                                         |

---

## Quick start (Docker — recommended)

```bash
cp backend/.env.example backend/.env
# edit backend/.env and set ANTHROPIC_API_KEY
docker compose up --build
```

Then open **http://localhost:8080**. (First question is slower — the embedding
and reranker models download once and are cached in the `model_cache` volume.)

## Local development (without Docker)

**1. Start Qdrant**

```bash
docker run -p 6333:6333 qdrant/qdrant:v1.12.4
```

**2. Backend**

```bash
cd backend
python -m venv .venv && . .venv/Scripts/activate   # Windows
# source .venv/bin/activate                          # macOS/Linux
pip install --index-url https://download.pytorch.org/whl/cpu torch==2.5.1
pip install -r requirements.txt
cp .env.example .env   # set ANTHROPIC_API_KEY
uvicorn app.main:app --reload
```

API docs: http://localhost:8000/docs · Metrics: http://localhost:8000/metrics

**3. Frontend**

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 (the dev server proxies `/api` to the backend).

---

## Tests & evaluation

```bash
cd backend
pytest -q tests                 # fast unit tests (pure logic, no services)
python -m eval.evaluate         # ingest corpus, run benchmark, print metric report
python -m eval.evaluate --full  # include LLM answer/citation/hallucination metrics
```

`eval.evaluate` exits non-zero if any metric falls below its threshold — this is
what the CI **eval gate** uses to block quality regressions
(`.github/workflows/ci.yml`).

## API

| Method   | Path                     | Purpose                              |
|----------|--------------------------|--------------------------------------|
| `POST`   | `/api/documents`         | Upload & ingest a document           |
| `GET`    | `/api/documents`         | List documents + status/metadata     |
| `DELETE` | `/api/documents/{id}`    | Delete a document and its vectors    |
| `POST`   | `/api/ask`               | Ask a question → grounded answer     |
| `GET`    | `/health`                | Readiness + counts                   |
| `GET`    | `/metrics`               | Prometheus metrics                   |

Example:

```bash
curl -F "file=@handbook.pdf" http://localhost:8000/api/documents

curl -X POST http://localhost:8000/api/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "How many annual leave days do employees get?"}'
```

## Configuration

All knobs are environment variables — see [`backend/.env.example`](backend/.env.example)
(chunk size/overlap, top-k for each retriever, RRF constant, rerank cutoff, model
names, etc.).

## Design

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the rationale behind hybrid
retrieval, reranking, the chunking strategy, and how hallucinations are
minimized — plus the intended path to auth, multi-user, streaming, and local
LLMs.

## Project layout

```
backend/
  app/
    api/         upload / ask / health routes
    core/        ingestion · preprocessing · embeddings · vectorstore ·
                 bm25 · retrieval · reranker · prompt · llm · pipeline
    storage/     SQLite registry
    config.py    env-driven settings      metrics.py   tracing + Prometheus
    logging_config.py                     schemas.py   API contract
    main.py      app wiring + middleware
  eval/          benchmark.json · metrics.py · evaluate.py · corpus/
  tests/         pure-logic unit tests
frontend/        React + Vite SPA (uploader, doc list, chat, citations, inspector)
docker-compose.yml   ·   .github/workflows/ci.yml
```
