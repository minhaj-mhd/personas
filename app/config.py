from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Database URL configuration
    DATABASE_URL: str = "postgresql+asyncpg://personas:personas@localhost:5432/personas"
    GEMINI_API_KEY: Optional[str] = None

    # Model configuration
    EMBED_MODEL: str = "text-embedding-004"
    CHAT_MODEL: str = "gemini-2.5-flash"
    SUMMARY_MODEL: str = "gemini-2.5-pro"

    # Memory configuration
    SHORT_TERM_MESSAGES: int = 12
    SUMMARIZE_THRESHOLD: int = 10
    RETRIEVE_TOP_K: int = 5

    # Voice configuration
    ELEVENLABS_API_KEY: Optional[str] = None

    # Load env vars from .env file at repo root if present
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
