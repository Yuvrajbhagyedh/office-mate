"""Evaluation metric implementations.

All metrics are computed from a list of per-question results produced by
`evaluate.py`. They are deliberately transparent (no black-box scorer) so a
reviewer can see exactly how each number is derived:

* retrieval_accuracy  — did at least one retrieved chunk come from an expected
                        source document? (recall@k at the document level)
* context_precision   — of the chunks fed to the LLM, what fraction came from an
                        expected source? (signal-to-noise of the context)
* answer_correctness  — semantic similarity between the generated answer and the
                        reference answer (embedding cosine), averaged.
* citation_accuracy   — did the answer cite an expected source document?
* hallucination_rate  — fraction of answers that are NOT grounded: either the
                        model answered a question whose reference is
                        "unanswerable", or its answer is semantically far from
                        the reference while still asserting content.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np


@dataclass
class QuestionResult:
    question: str
    expected_answer: str
    expected_sources: List[str]
    answerable: bool
    retrieved_sources: List[str] = field(default_factory=list)
    cited_sources: List[str] = field(default_factory=list)
    answer: str = ""
    grounded: bool = True
    answer_similarity: Optional[float] = None  # filled when an LLM answer exists


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = (np.linalg.norm(a) * np.linalg.norm(b)) or 1e-9
    return float(np.dot(a, b) / denom)


def retrieval_accuracy(results: List[QuestionResult]) -> float:
    answerable = [r for r in results if r.answerable]
    if not answerable:
        return 1.0
    hits = sum(
        1 for r in answerable if set(r.retrieved_sources) & set(r.expected_sources)
    )
    return hits / len(answerable)


def context_precision(results: List[QuestionResult]) -> float:
    total, relevant = 0, 0
    for r in results:
        if not r.answerable:
            continue
        for src in r.retrieved_sources:
            total += 1
            if src in r.expected_sources:
                relevant += 1
    return relevant / total if total else 0.0


def answer_correctness(results: List[QuestionResult], threshold: float = 0.6) -> float:
    scored = [r.answer_similarity for r in results if r.answer_similarity is not None]
    if not scored:
        return float("nan")
    return float(np.mean([1.0 if s >= threshold else 0.0 for s in scored]))


def citation_accuracy(results: List[QuestionResult]) -> float:
    answerable = [r for r in results if r.answerable]
    if not answerable:
        return 1.0
    ok = sum(1 for r in answerable if set(r.cited_sources) & set(r.expected_sources))
    return ok / len(answerable)


def hallucination_rate(results: List[QuestionResult], sim_threshold: float = 0.5) -> float:
    """Fraction of responses that assert content they shouldn't.

    A response is counted as a hallucination when:
      * the question is unanswerable but the model still produced a grounded
        (non-refusal) answer, OR
      * the question is answerable, the model answered, but the answer is
        semantically far from the reference (similarity below threshold).
    """
    if not results:
        return 0.0
    bad = 0
    for r in results:
        if not r.answerable:
            if r.grounded:  # should have refused
                bad += 1
        else:
            if r.grounded and r.answer_similarity is not None and r.answer_similarity < sim_threshold:
                bad += 1
    return bad / len(results)


def summarize(results: List[QuestionResult]) -> dict:
    return {
        "retrieval_accuracy": round(retrieval_accuracy(results), 4),
        "context_precision": round(context_precision(results), 4),
        "answer_correctness": round(answer_correctness(results), 4),
        "citation_accuracy": round(citation_accuracy(results), 4),
        "hallucination_rate": round(hallucination_rate(results), 4),
        "num_questions": len(results),
    }
