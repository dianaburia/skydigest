"""Application settings loaded from the .env file at project root."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    nasa_api_key: str
    anthropic_api_key: str
    database_url: str
    embedding_model: str = "BAAI/bge-m3"
    ask_daily_limit: int = 20  # /ask questions per IP per day (each costs API credits)
    cors_origins: list[str] = ["http://localhost:3000"]  # frontends allowed to call the API


@lru_cache
def get_settings() -> Settings:
    return Settings()
