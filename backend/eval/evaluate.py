"""Evaluation harness.

Ingests the corpus in ``eval/corpus/`` into a (temporary) collection, runs every
benchmark question through the real pipeline, computes the metrics in
``metrics.py``, prints a report, and exits non-zero if any metric falls below the
configured threshold. That non-zero exit is what lets CI block a regression.

Modes:
  * Retrieval-only (default when ANTHROPIC_API_KEY is absent): evaluates
    retrieval_accuracy and context_precision — no LLM calls, so it runs in CI
    for free against a Qdrant service container.
  * Full (when ANTHROPIC_API_KEY is present or --full is passed): additionally
    evaluates answer_correctness, citation_accuracy and hallucination_rate.

Usage:
    python -m eval.evaluate                 # auto mode
    python -m eval.evaluate --full          # force LLM eval
    python -m eval.evaluate --retrieval-only
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path
from typing import List

import numpy as np

# Windows consoles default to cp1252 and choke on non-ASCII output. Force UTF-8.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

# Ensure the package root is importable when run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.core import pipeline  # noqa: E402
from app.core.embeddings import embedder  # noqa: E402
from app.deps import registry  # noqa: E402
from eval import metrics as M  # noqa: E402

CORPUS_DIR = Path(__file__).parent / "corpus"
BENCHMARK = Path(__file__).parent / "benchmark.json"

# Quality gates. Tune per corpus; CI fails if a metric drops below its floor.
THRESHOLDS = {
    "retrieval_accuracy": 0.85,
    "context_precision": 0.50,
    "answer_correctness": 0.80,
    "citation_accuracy": 0.80,
    "hallucination_rate": 0.10,  # upper bound
}


def ingest_corpus() -> None:
    print(f"Ingesting corpus from {CORPUS_DIR} ...")
    for path in sorted(CORPUS_DIR.glob("*")):
        if path.is_file():
            data = path.read_bytes()
            doc_id = str(uuid.uuid4())
            registry.create_document(doc_id, path.name, path.suffix.lstrip("."), len(data))
            pipeline.ingest_document(doc_id, path.name, data)
            print(f"  [ok] {path.name}")


def run(use_llm: bool) -> List[M.QuestionResult]:
    spec = json.loads(BENCHMARK.read_text(encoding="utf-8"))
    results: List[M.QuestionResult] = []

    for q in spec["questions"]:
        qr = M.QuestionResult(
            question=q["question"],
            expected_answer=q["expected_answer"],
            expected_sources=q.get("expected_sources", []),
            answerable=q.get("answerable", True),
        )

        if use_llm:
            resp = pipeline.answer_question(qr.question, document_ids=None, top_n=None)
            qr.retrieved_sources = list({c.filename for c in resp.retrieved_context})
            qr.cited_sources = list({c.filename for c in resp.citations})
            qr.answer = resp.answer
            qr.grounded = resp.grounded
            if qr.answerable and qr.grounded:
                qr.answer_similarity = _similarity(resp.answer, qr.expected_answer)
        else:
            # Retrieval-only: exercise hybrid retrieve + rerank, skip the LLM.
            from app.metrics import Trace
            from app.core.retrieval import hybrid_retrieve
            from app.core.reranker import reranker

            trace = Trace()
            fused = hybrid_retrieve(qr.question, None, trace)
            hydrated = pipeline._hydrate(fused)
            top = reranker.rerank(
                qr.question, hydrated, settings.rerank_top_n, settings.min_rerank_score
            )
            qr.retrieved_sources = list({c["filename"] for c in top})

        results.append(qr)
        print(f"  - {qr.question[:60]:<60} sources={qr.retrieved_sources}")

    return results


def _similarity(a: str, b: str) -> float:
    va = np.array(embedder.embed_query(a))
    vb = np.array(embedder.embed_query(b))
    return M.cosine(va, vb)


def gate(report: dict, use_llm: bool) -> bool:
    """Return True if all applicable thresholds pass."""
    ok = True
    print("\n=== Evaluation Report ===")
    for name, value in report.items():
        if name == "num_questions":
            print(f"  {name:22} {value}")
            continue
        if not use_llm and name in {"answer_correctness", "citation_accuracy", "hallucination_rate"}:
            print(f"  {name:22} skipped (retrieval-only mode)")
            continue
        threshold = THRESHOLDS.get(name)
        if value != value:  # NaN
            print(f"  {name:22} n/a")
            continue
        upper_bound = name == "hallucination_rate"
        passed = value <= threshold if upper_bound else value >= threshold
        flag = "PASS" if passed else "FAIL"
        cmp = "<=" if upper_bound else ">="
        print(f"  {name:22} {value:<8} (need {cmp} {threshold})  [{flag}]")
        ok = ok and passed
    return ok


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true", help="Force LLM evaluation.")
    parser.add_argument("--retrieval-only", action="store_true", help="Skip LLM evaluation.")
    args = parser.parse_args()

    has_key = bool(settings.anthropic_api_key)
    use_llm = args.full or (has_key and not args.retrieval_only)
    print(f"Mode: {'FULL (with LLM)' if use_llm else 'RETRIEVAL-ONLY'}")

    from app.core.vectorstore import vector_store

    vector_store.ensure_collection()
    ingest_corpus()
    results = run(use_llm)
    report = M.summarize(results)
    passed = gate(report, use_llm)

    (Path(__file__).parent / "last_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print("\nOverall:", "PASS" if passed else "FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
