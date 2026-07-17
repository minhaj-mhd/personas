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

    # MCP — Google Sheets access for live sessions (Model Context Protocol).
    # When enabled, the app launches the configured MCP server over stdio, exposes its
    # tools to the live agent, and forwards tool calls to it. Point COMMAND/ARGS at a
    # Google Sheets MCP server you run (with your own Google credentials); pass any
    # secrets the server needs via MCP_SHEETS_ENV. Disabled by default — off means the
    # live sessions behave exactly as before. See MCP_GOOGLE_SHEETS.md.
    MCP_SHEETS_ENABLED: bool = False
    MCP_SHEETS_COMMAND: str = "npx"
    MCP_SHEETS_ARGS: list[str] = []  # e.g. ["-y", "@your/google-sheets-mcp"]
    MCP_SHEETS_ENV: dict[str, str] = {}  # extra env vars for the MCP server process

    # Memory configuration
    SHORT_TERM_MESSAGES: int = 12
    SUMMARIZE_THRESHOLD: int = 10
    # Caps how many unsummarized messages go into a single Ollama call. Without this, a
    # large backlog (e.g. a long-running Live session, or one where a prior attempt
    # failed and left messages unsummarized) gets stuffed into one request and reliably
    # times out — which then leaves the backlog even bigger for the next attempt.
    # Measured on dev hardware against local qwen3:8b: a 30-message batch (~6.1k prompt
    # tokens) took ~114s, and 15-message batches averaged ~138s and occasionally breached
    # even a 180s timeout once the GPU had been under sustained load. 10 keeps each call
    # well inside the timeout with headroom for that slowdown.
    SUMMARIZE_BATCH_SIZE: int = 10
    # Per-call timeout (seconds) for the Ollama summarization request. Generous margin
    # over a batch's measured runtime so a momentarily busy GPU doesn't spuriously fail.
    SUMMARIZE_TIMEOUT: float = 180.0
    # Extra attempts (with exponential backoff) for a batch before giving up. A single
    # transient timeout shouldn't abandon the rest of the backlog — only a batch that
    # fails every attempt halts the drain (and the next session resumes from the
    # watermark anyway).
    SUMMARIZE_MAX_RETRIES: int = 2
    RETRIEVE_TOP_K: int = 5

    # Voice configuration
    ELEVENLABS_API_KEY: Optional[str] = None

    # Load env vars from .env file at repo root if present
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


settings = Settings()
