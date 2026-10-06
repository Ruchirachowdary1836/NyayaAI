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

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)


settings = Settings()
