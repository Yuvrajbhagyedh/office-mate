"""Performance instrumentation.

Two layers:

1. Prometheus metrics (histograms/counters) exposed at ``/metrics`` for
   dashboards and alerting.
2. A lightweight ``Stopwatch`` / ``Trace`` helper that records per-stage
   timings and returns them inline in the API response, so a caller can see
   exactly where time went for a single request (document processing,
   embedding, retrieval, reranking, LLM, total).

Keeping both means we get aggregate monitoring *and* per-request tracing from
one place, which is exactly what the spec asks for.
"""
from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Dict, Iterator

from prometheus_client import Counter, Histogram

# ---- Prometheus (aggregate) ----
STAGE_LATENCY = Histogram(
    "rag_stage_latency_seconds",
    "Latency of an individual pipeline stage.",
    labelnames=["stage"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
)
REQUEST_LATENCY = Histogram(
    "rag_request_latency_seconds",
    "End-to-end request latency.",
    labelnames=["endpoint"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60),
)
REQUESTS_TOTAL = Counter(
    "rag_requests_total", "Total requests handled.", labelnames=["endpoint", "status"]
)
DOCS_INGESTED = Counter("rag_documents_ingested_total", "Documents successfully ingested.")
CHUNKS_INDEXED = Counter("rag_chunks_indexed_total", "Chunks written to the vector store.")
ANSWERS_REFUSED = Counter(
    "rag_answers_refused_total", "Answers where the model declined for lack of evidence."
)


@dataclass
class Trace:
    """Collects per-stage timings for a single request."""

    timings_ms: Dict[str, float] = field(default_factory=dict)
    _t0: float = field(default_factory=time.perf_counter)

    @contextmanager
    def stage(self, name: str) -> Iterator[None]:
        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed = time.perf_counter() - start
            self.timings_ms[name] = round(elapsed * 1000, 2)
            STAGE_LATENCY.labels(stage=name).observe(elapsed)

    def record(self, name: str, seconds: float) -> None:
        self.timings_ms[name] = round(seconds * 1000, 2)
        STAGE_LATENCY.labels(stage=name).observe(seconds)

    def total_ms(self) -> float:
        return round((time.perf_counter() - self._t0) * 1000, 2)

    def as_dict(self) -> Dict[str, float]:
        out = dict(self.timings_ms)
        out["total"] = self.total_ms()
        return out


@contextmanager
def timed(seconds_sink: list) -> Iterator[None]:
    start = time.perf_counter()
    try:
        yield
    finally:
        seconds_sink.append(time.perf_counter() - start)
