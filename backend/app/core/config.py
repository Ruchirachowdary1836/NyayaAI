from __future__ import annotations

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_JWT_SECRET = "change-me-in-production"


class Settings(BaseSettings):
    app_name: str = "NyayaAI"
    app_env: str = "development"
    log_level: str = "INFO"
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    jwt_secret_key: str = DEFAULT_JWT_SECRET
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60
    # Bootstrap administrator, created on startup only if the username does not exist.
    initial_admin_username: str = ""
    initial_admin_password: str = ""
    database_url: str = "sqlite:///data/processed/nyayaai.db"
    ollama_base_url: str = "http://localhost:11434"
    generator_provider: str = "ollama"
    generator_api_key: str = ""
    generator_api_base_url: str = "https://api.openai.com/v1"
    generator_model: str = "llama3.1:8b"
    generator_timeout_seconds: float = 120.0
    # Characters of each retrieved passage sent to the model (query-focused window).
    qa_passage_chars: int = 1200
    embedding_model: str = "BAAI/bge-m3"
    # "local" runs sentence-transformers in-process (needs the 'dense' extra);
    # "openai" calls an OpenAI-compatible /embeddings API (e.g. Gemini) and stores vectors
    # in the database so they survive restarts on hosts with ephemeral disks.
    embedding_provider: str = "local"
    embedding_api_base_url: str = ""  # defaults to GENERATOR_API_BASE_URL
    embedding_api_key: str = ""  # defaults to GENERATOR_API_KEY
    embedding_dimensions: int | None = None  # truncate (Matryoshka) and renormalize
    embedding_batch_size: int = 50
    embedding_requests_per_minute: int = 60
    enabled_retrievers: list[str] = ["bm25"]
    hybrid_method: str = "rrf"
    hybrid_alpha: float = 0.7
    hybrid_rrf_k: int = 60
    data_chunks_path: str = "data/processed/chunks.jsonl"
    data_documents_path: str = "data/processed/documents.jsonl"
    index_dir: str = "data/indices"
    results_dir: str = "evaluation/results"
    rate_limit_per_minute: int = 120
    auth_rate_limit_per_minute: int = 10
    qa_rate_limit_per_minute: int = 10
    upload_max_bytes: int = 5 * 1024 * 1024
    upload_max_documents_per_user: int = 200
    experiment_max_queries: int = 25

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    @field_validator("hybrid_method")
    @classmethod
    def _validate_hybrid_method(cls, value: str) -> str:
        if value not in {"rrf", "weighted"}:
            raise ValueError("HYBRID_METHOD must be 'rrf' or 'weighted'")
        return value

    @field_validator("embedding_dimensions", mode="before")
    @classmethod
    def _empty_dimensions_means_unset(cls, value: object) -> object:
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator("embedding_provider")
    @classmethod
    def _validate_embedding_provider(cls, value: str) -> str:
        if value not in {"local", "openai"}:
            raise ValueError("EMBEDDING_PROVIDER must be 'local' or 'openai'")
        return value

    @property
    def resolved_embedding_api_base_url(self) -> str:
        return (self.embedding_api_base_url or self.generator_api_base_url).rstrip("/")

    @property
    def resolved_embedding_api_key(self) -> str:
        return self.embedding_api_key or self.generator_api_key

    @field_validator("hybrid_alpha")
    @classmethod
    def _validate_alpha(cls, value: float) -> float:
        if not 0 <= value <= 1:
            raise ValueError("HYBRID_ALPHA must be between 0 and 1")
        return value

    @property
    def is_production(self) -> bool:
        return self.app_env.casefold() == "production"

    def production_problems(self) -> list[str]:
        """Return configuration errors that make a production deployment unsafe."""
        problems: list[str] = []
        if self.jwt_secret_key == DEFAULT_JWT_SECRET or len(self.jwt_secret_key) < 32:
            problems.append("JWT_SECRET_KEY must be a unique value of at least 32 characters")
        if "*" in self.cors_origins:
            problems.append("CORS_ORIGINS must list explicit origins, not '*'")
        if self.database_url.startswith("sqlite"):
            problems.append("DATABASE_URL must point to a persistent server database")
        return problems


settings = Settings()
