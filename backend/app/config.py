"""Centralized application configuration.

All runtime configuration is sourced from environment variables (12-factor).
A `.env` file is loaded automatically in development; in production the same
variables are injected by the orchestrator (Docker Compose, k8s, etc.).
"""
from __future__ import annotations

from functools import lru_cache
from typing import List, Union

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- App ----
    app_name: str = "Office Mate"
    environment: str = Field(default="development")
    log_level: str = Field(default="INFO")
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)
    # Accept JSON list, comma-separated, or a single origin string from env.
    cors_origins: List[str] = Field(
        default=["http://localhost:5173", "http://localhost:3000", "https://office-mate-five.vercel.app"]
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, value: Union[str, List[str], None]) -> List[str]:
        if value is None or value == "":
            return ["http://localhost:5173", "https://office-mate-five.vercel.app"]
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]
        raw = str(value).strip()
        if raw.startswith("["):
            import json

            parsed = json.loads(raw)
            return [str(v).strip() for v in parsed if str(v).strip()]
        return [part.strip() for part in raw.split(",") if part.strip()]

    # ---- Auth (employee ID + DOB) ----
    auth_secret: str = Field(default="office-mate-dev-secret-change-me")
    auth_token_hours: int = Field(default=24)
    seed_admin_employee_id: str = Field(default="ADMIN001")
    seed_admin_dob: str = Field(default="1990-01-15")
    seed_admin_name: str = Field(default="Office Admin")
    seed_employee_id: str = Field(default="EMP1001")
    seed_employee_dob: str = Field(default="1995-06-20")
    seed_employee_name: str = Field(default="Alex Employee")

    # ---- Storage ----
    data_dir: str = Field(default="./data")
    upload_dir: str = Field(default="./data/uploads")
    registry_db: str = Field(default="./data/registry.db")
    max_upload_mb: int = Field(default=25)
    # Files here are ingested on startup whenever the registry is empty. Free
    # hosts (Render) wipe the disk on every restart, so this is how the live
    # site keeps its documents.
    seed_docs_dir: str = Field(default="./seed_docs")

    # ---- Chunking ----
    chunk_size: int = Field(default=900, description="Target chunk size in characters.")
    chunk_overlap: int = Field(default=150, description="Overlap between adjacent chunks.")

    # ---- Embeddings ----
    # google = Gemini Embedding API (low RAM, for free Render)
    # local  = sentence-transformers (needs >1.5GB RAM)
    embedding_provider: str = Field(default="google")
    embedding_model: str = Field(default="gemini-embedding-001")
    embedding_device: str = Field(default="cpu")
    embedding_query_prefix: str = Field(
        default="Represent this sentence for searching relevant passages: "
    )
    embedding_dim: int = Field(default=768)
    # Google batchEmbedContents accepts at most 100 texts per request.
    embedding_batch_size: int = Field(default=100)

    # ---- Vector store (Qdrant) ----
    # Two modes:
    #  * Server mode (Docker/prod): set qdrant_url, leave qdrant_local_path empty.
    #  * Embedded mode (no Docker):  set qdrant_local_path to a folder — Qdrant then
    #    runs in-process and persists there, no server required.
    qdrant_url: str = Field(default="http://localhost:6333")
    qdrant_local_path: str | None = Field(default=None)
    qdrant_api_key: str | None = Field(default=None)
    qdrant_collection: str = Field(default="documents_g")

    # ---- Retrieval ----
    vector_top_k: int = Field(default=20, description="Candidates pulled from vector search.")
    bm25_top_k: int = Field(default=20, description="Candidates pulled from BM25.")
    rrf_k: int = Field(default=60, description="Reciprocal Rank Fusion constant.")
    rerank_top_n: int = Field(default=5, description="Chunks kept after cross-encoder rerank.")
    reranker_model: str = Field(default="cross-encoder/ms-marco-MiniLM-L-6-v2")
    # Off by default so free-tier hosts don't load torch cross-encoders.
    reranker_enabled: bool = Field(default=False)
    min_rerank_score: float = Field(
        default=-6.0,
        description="Below this cross-encoder score a chunk is treated as irrelevant. "
        "If nothing clears the bar, the LLM is told there is no evidence.",
    )
    # Evidence gate used when the cross-encoder is disabled: chunks whose cosine
    # similarity to the question is below this are treated as irrelevant.
    min_vector_score: float = Field(default=0.5)

    # ---- LLM ----
    # Providers: google (Gemini free), groq, xai (Grok), anthropic (Claude)
    llm_provider: str = Field(default="google")
    llm_model: str = Field(default="gemini-flash-latest")
    llm_max_tokens: int = Field(default=2048)
    # Total time budget for one answer, across all retries and fallback models.
    llm_timeout_seconds: float = Field(default=30.0)
    llm_base_url: str | None = Field(
        default=None,
        description="Override OpenAI-compatible base URL (groq/xai).",
    )
    # Generic key used if provider-specific key is unset.
    llm_api_key: str | None = Field(default=None)
    google_api_key: str | None = Field(default=None)
    gemini_api_key: str | None = Field(default=None)
    groq_api_key: str | None = Field(default=None)
    xai_api_key: str | None = Field(default=None)
    anthropic_api_key: str | None = Field(default=None)
    # Anthropic-only: output_config effort (ignored by other providers).
    llm_effort: str = Field(default="low", description="output_config effort: low|medium|high.")

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
