from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Database URL configuration
    DATABASE_URL: str = "postgresql+asyncpg://personas:personas@localhost:5432/personas"
    # Set by the test suite (conftest.py) before app modules import. Redirects all DB
    # access to an isolated "<dbname>_test" database so tests never touch dev data.
    TESTING: bool = False
    GEMINI_API_KEY: Optional[str] = None

    def model_post_init(self, __context) -> None:
        if self.TESTING and not self.DATABASE_URL.endswith("_test"):
            base, _, dbname = self.DATABASE_URL.rpartition("/")
            self.DATABASE_URL = f"{base}/{dbname}_test"

    # Model configuration
    EMBED_MODEL: str = "text-embedding-004"
    CHAT_MODEL: str = "gemini-2.5-flash"
    # NOTE: gemini-2.5-pro has a free-tier quota of 0 (every summarize call returns
    # 429 RESOURCE_EXHAUSTED), which silently breaks session-end summarization and the
    # long-term memory it feeds. Use flash, which has free quota. Override via .env if
    # you move to a paid tier and want pro-quality summaries.
    SUMMARY_MODEL: str = "gemini-2.5-flash"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_SUMMARY_MODEL: str = "qwen3:8b"
    OLLAMA_EMBED_MODEL: str = "nomic-embed-text"

    # Live voice (full-duplex) configuration — Voice L1
    # Override LIVE_MODEL via .env to point at whichever Live model you have access to
    # (e.g. a Gemini 3 Flash Live model). Must be a half-cascade/native-audio Live model.
    LIVE_MODEL: str = "gemini-3.1-flash-live-preview"
    LIVE_VOICE: str = (
        "Puck"  # default prebuilt voice when persona.voice is unset/invalid
    )
    # NOTE: NOT applied on the Gemini Developer API — `language_codes` is Enterprise-only and
    # crashes the Live session if sent. Retained for a future Enterprise/Vertex path; transcription
    # currently auto-detects language. (See gemini_live._transcription_config.)
    LIVE_LANGUAGE: str = "en-US"
    LIVE_ENABLE_SEARCH: bool = (
        False  # also expose Google Search grounding in the live session
    )
    LIVE_INPUT_SAMPLE_RATE: int = 16000  # PCM16 mono the client must stream up
    LIVE_OUTPUT_SAMPLE_RATE: int = 24000  # PCM16 mono the model streams back

    # Memory configuration
    SHORT_TERM_MESSAGES: int = 12
    SUMMARIZE_THRESHOLD: int = 10
    RETRIEVE_TOP_K: int = 5

    # Voice configuration
    ELEVENLABS_API_KEY: Optional[str] = None

    # Load env vars from .env file at repo root if present
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


settings = Settings()
