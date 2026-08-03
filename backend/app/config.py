"""Centralized application configuration.

All runtime configuration is sourced from environment variables (12-factor).
A `.env` file is loaded automatically in development; in production the same
variables are injected by the orchestrator (Docker Compose, k8s, etc.).
"""
from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import Field
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
    cors_origins: List[str] = Field(default=["http://localhost:5173", "http://localhost:3000"])

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

    # ---- Chunking ----
    chunk_size: int = Field(default=900, description="Target chunk size in characters.")
    chunk_overlap: int = Field(default=150, description="Overlap between adjacent chunks.")

    # ---- Embeddings ----
    embedding_model: str = Field(default="BAAI/bge-small-en-v1.5")
    embedding_device: str = Field(default="cpu")
    # bge models want an instruction prefix on the *query* side only.
    embedding_query_prefix: str = Field(
        default="Represent this sentence for searching relevant passages: "
    )
    embedding_dim: int = Field(default=384)

    # ---- Vector store (Qdrant) ----
    # Two modes:
    #  * Server mode (Docker/prod): set qdrant_url, leave qdrant_local_path empty.
    #  * Embedded mode (no Docker):  set qdrant_local_path to a folder — Qdrant then
    #    runs in-process and persists there, no server required.
    qdrant_url: str = Field(default="http://localhost:6333")
    qdrant_local_path: str | None = Field(default=None)
    qdrant_api_key: str | None = Field(default=None)
    qdrant_collection: str = Field(default="documents")

    # ---- Retrieval ----
    vector_top_k: int = Field(default=20, description="Candidates pulled from vector search.")
    bm25_top_k: int = Field(default=20, description="Candidates pulled from BM25.")
    rrf_k: int = Field(default=60, description="Reciprocal Rank Fusion constant.")
    rerank_top_n: int = Field(default=5, description="Chunks kept after cross-encoder rerank.")
    reranker_model: str = Field(default="cross-encoder/ms-marco-MiniLM-L-6-v2")
    min_rerank_score: float = Field(
        default=-6.0,
        description="Below this cross-encoder score a chunk is treated as irrelevant. "
        "If nothing clears the bar, the LLM is told there is no evidence.",
    )

    # ---- LLM ----
    # Providers: google (Gemini free), groq, xai (Grok), anthropic (Claude)
    llm_provider: str = Field(default="google")
    llm_model: str = Field(default="gemini-flash-latest")
    llm_max_tokens: int = Field(default=2048)
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
