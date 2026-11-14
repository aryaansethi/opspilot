"""Application settings, loaded from environment variables / backend/.env.

Every value has a safe local-development default so the stack runs with zero
configuration against docker-compose + Ollama. Nothing here is a real secret.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_JWT_SECRET = "dev-only-insecure-jwt-secret-change-me-0123456789"  # noqa: S105


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- app ---
    environment: Literal["local", "test", "production"] = "local"
    log_level: str = "INFO"
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = ["http://localhost:3000"]

    # --- database ---
    database_url: str = "postgresql+asyncpg://opspilot:opspilot@localhost:5433/opspilot"

    # --- auth ---
    jwt_secret: SecretStr = SecretStr(DEV_JWT_SECRET)
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 14
    refresh_cookie_name: str = "opspilot_refresh"
    login_rate_limit_per_minute: int = 10
    register_rate_limit_per_hour: int = 20
    ask_rate_limit_per_minute: int = 30
    investigation_rate_limit_per_minute: int = 10
    evaluation_rate_limit_per_hour: int = 30
    max_live_streams_per_user: int = 5
    cookie_secure: bool = False  # True in production (HTTPS)

    # --- AWS (LocalStack locally) ---
    aws_region: str = "us-east-1"
    aws_endpoint_url: str | None = "http://localhost:4566"
    aws_access_key_id: str = "test"
    aws_secret_access_key: SecretStr = SecretStr("test")
    s3_documents_bucket: str = "opspilot-documents"
    # Endpoint used only for browser-facing presigned URLs (set when the API runs inside Docker).
    s3_public_endpoint_url: str | None = None
    sqs_ingest_queue: str = "opspilot-ingest"
    max_upload_bytes: int = 20 * 1024 * 1024
    presign_ttl_seconds: int = 900

    # --- LLM / embeddings (Ollama exposes an OpenAI-compatible API) ---
    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: SecretStr = SecretStr("ollama")
    # qwen3:8b with a 16K context window; see docker/ollama/Modelfile
    llm_model: str = "opspilot-qwen3-8b"
    llm_timeout_seconds: float = 300.0
    # Qwen3 models "think" before answering by default; "/no_think" turns that off for speed.
    llm_prompt_suffix: str = " /no_think"
    embedding_model: str = "bge-m3"
    embedding_dim: int = 1024
    embedding_batch_size: int = 16

    # --- MCP servers (local processes; streamable HTTP) ---
    mcp_cloudwatch_url: str = "http://127.0.0.1:8101/mcp"
    mcp_github_url: str = "http://127.0.0.1:8102/mcp"

    # --- investigations ---
    sqs_investigate_queue: str = "opspilot-investigate"
    sqs_evaluate_queue: str = "opspilot-evaluate"
    investigation_timeout_seconds: int = 420
    investigation_max_tool_calls: int = 12
    investigation_max_window_hours: int = 24

    # --- evaluation ---
    evaluation_datasets_root: str = str(
        __import__("pathlib").Path(__file__).resolve().parents[3] / "evaluation" / "datasets"
    )
    evaluation_default_version: str = "v2"

    # --- retrieval ---
    chunk_target_tokens: int = 500
    chunk_overlap_tokens: int = 80
    retrieval_candidates: int = 50
    rrf_k: int = Field(default=60, ge=1)
    # Tuned on dataset v2's tune split (evaluation/experiments/fusion_sweep-v2.md): the lexical
    # list is noisy, so it gets half the vote of the vector list and only its top 10 count.
    fusion_lexical_weight: float = Field(default=0.5, ge=0)
    fusion_lexical_depth: int = Field(default=10, ge=1)
    rerank_enabled: bool = False
    rerank_model: str = "BAAI/bge-reranker-base"
    rerank_candidates: int = 30
    answer_context_chunks: int = 8

    @field_validator("aws_endpoint_url", "s3_public_endpoint_url", mode="before")
    @classmethod
    def _empty_is_none(cls, v: object) -> object:
        """An empty value (e.g. AWS_ENDPOINT_URL= in ECS) means "use real AWS"."""
        return None if v == "" else v

    @model_validator(mode="after")
    def _production_guards(self) -> "Settings":
        if self.environment == "production":
            if self.jwt_secret.get_secret_value() == DEV_JWT_SECRET:
                raise ValueError("JWT_SECRET must be set in production")
            if not self.cookie_secure:
                raise ValueError("COOKIE_SECURE must be true in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
