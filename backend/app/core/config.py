from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "NyayaAI"
    app_env: str = "development"
    log_level: str = "INFO"
    api_prefix: str = "/api/v1"
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "nyayaai"
    postgres_user: str = "nyayaai"
    postgres_password: str = "nyayaai"
    database_url: str = "sqlite:///data/processed/nyayaai.db"
    ollama_base_url: str = "http://localhost:11434"
    generator_model: str = "llama3.1:8b"
    embedding_model: str = "BAAI/bge-m3"
    data_chunks_path: str = "data/processed/chunks.jsonl"
    data_documents_path: str = "data/processed/documents.jsonl"
    results_dir: str = "evaluation/results"
    rate_limit_per_minute: int = 120

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)


settings = Settings()
