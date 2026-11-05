"""Application configuration loaded from environment variables or a local .env file."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the local Ollama service."""

    ollama_model: str | None = None
    ollama_base_url: str = "http://localhost:11434"
    llm_timeout_seconds: float = Field(default=30.0, gt=0)

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
