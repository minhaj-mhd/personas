---
title: "Backend Overview"
type: reference
status: active
updated: 2026-06-25
---

# ⚙️ Backend Overview

The backend is built as an asynchronous FastAPI application, combining relational data management, background task workers, vector retrieval logic, and WebSocket communication in a single container.

---

## 🏛️ Codebase Structure

The backend source code resides inside the `app/` folder:

```
app/
├── alembic/              # Database migration definitions & schemas history
├── api/                  # JSON API routers (REST & WebSockets)
│   ├── conversations.py  # Session CRUD, summarize, export (md), search
│   ├── personas.py       # Persona CRUD and Knowledge Base document uploads
│   ├── voice_ws.py       # Text dialog turn streaming WebSocket (/ws/chat)
│   ├── live_ws.py        # Single-agent Gemini Live full-duplex voice (/ws/live)
│   └── panel_ws.py       # Multi-agent host-led voice panel (/ws/panel) — Voice L2
├── models/               # SQLAlchemy Declarative Models (conversation/memory/message/persona)
├── schemas/              # Pydantic payloads and serialization schemas
├── services/             # Core business logic and LLM integrations
│   ├── embeddings.py     # nomic-embed-text via Ollama (768-dim)
│   ├── gemini.py         # gemini-2.5-flash streaming generator (text chat)
│   ├── gemini_live.py    # Gemini Live config/tools (recall_memory, route_to_agent, voices)
│   ├── memory.py         # Chunker + pgvector retriever + Live preamble memories
│   ├── prompt_builder.py # System-instruction builder + context injector
│   ├── summarizer.py     # qwen3:8b via Ollama structured summarizer
│   ├── export.py         # Conversation → Markdown renderer
│   ├── search.py         # Search snippet helper
│   └── panel/            # Voice-panel brain: router.py (floor routing) + session.py (PanelState)
├── static/js/            # ws.js (text), live.js (single-agent audio engine), panel.js (panel client)
├── templates/            # Jinja2 HTML (index, chat, conversations, persona_form, panel)
├── web/views.py          # Dashboard, chat, persona form, /panel renderers
├── config.py             # Settings loader (.env): Gemini + Ollama + Live config
├── db.py                 # Async SQLAlchemy session setup & engine pooling
└── main.py               # App startup; mounts personas/conversations/voice_ws/live_ws/panel_ws/web routers
```

---

## 🚪 API Routers Layer (`app/api/`)

### 1. Persona Management ([personas.py](file:///c:/Users/loq/Desktop/learn/personas/app/api/personas.py))
- Handles CRUD configurations for custom personas.
- **Knowledge Base Endpoints**:
  - `POST /{id}/documents`: Ingests files or raw copy-paste texts. Invokes `MemoryService.ingest_document`.
  - `GET /{id}/documents`: Returns unique filenames of ingested documents for dashboard lists.
  - `DELETE /{id}/documents`: Wipes all document chunks associated with a persona.

### 2. Conversation Sessions ([conversations.py](file:///c:/Users/loq/Desktop/learn/personas/app/api/conversations.py))
- Conversation creation, history lists, delete.
- `POST /{id}/summarize`: Manual trigger → `SummarizerService.maybe_summarize(force=True)`.
- `GET /{id}/export?format=md`: Downloads the transcript as Markdown (`services/export.py`).
- `GET /search?q=&persona_id=`: Full-text search across messages with snippets (`services/search.py`). *(in progress)*

### 3. Text Dialogue WebSocket ([voice_ws.py](file:///c:/Users/loq/Desktop/learn/personas/app/api/voice_ws.py))
- `/ws/chat/{conversation_id}`. Streams tokens, injects RAG/memory, cancels on interrupt, schedules summarization.

### 4. Single-Agent Live Voice ([live_ws.py](file:///c:/Users/loq/Desktop/learn/personas/app/api/live_ws.py))
- `/ws/live/{conversation_id}`. Full-duplex Gemini Live: PCM in/out, native VAD/barge-in, transcripts,
  `recall_memory` tool (mid-session RAG), memory preamble at connect, summarize on disconnect.

### 5. Multi-Agent Voice Panel — Voice L2 ([panel_ws.py](file:///c:/Users/loq/Desktop/learn/personas/app/api/panel_ws.py))
- `/ws/panel/{conversation_id}`. Host-led panel: pick roster → host greets → call an agent by name →
  `route_to_agent` tool switches the floor (one Live session at a time) → next agent primed with the shared
  transcript + its own memory. See [[01 — Architecture/Master Plan — Voice Panel (Host-Led, Subagent-Ready)]].

---

## 🛠️ Service Components Layer (`app/services/`)

### 1. LLM Generation Service ([gemini.py](file:///c:/Users/loq/Desktop/learn/personas/app/services/gemini.py))
- Uses `Client.aio.models.generate_content_stream` to stream response chunks asynchronously.
- Connects to the **`gemini-2.5-flash`** model to minimize latency. (Live voice uses `gemini_live.py` / `LIVE_MODEL`.)

### 2. Embedding Generator ([embeddings.py](file:///c:/Users/loq/Desktop/learn/personas/app/services/embeddings.py))
- Uses local **`nomic-embed-text` via Ollama** (`/api/embed`) to generate 768-dimension vectors. Single + batch.
- *(Migrated off Gemini `text-embedding-004` to escape free-tier quotas — see [[Memory in a Live Voice Session]].)*

### 3. Memory & RAG Service ([memory.py](file:///c:/Users/loq/Desktop/learn/personas/app/services/memory.py))
- **Word-Aligned Sliding Window**: Chunks text documents on space boundaries to keep words intact.
- **Semantic retrieval**: Embeds query strings and retrieves facts/documents matching cosine distance criteria.

### 4. Prompt Assembler ([prompt_builder.py](file:///c:/Users/loq/Desktop/learn/personas/app/services/prompt_builder.py))
- Formats base persona settings.
- Appends narrative summaries and fact bullet points under a `### LONG-TERM MEMORY & CONTEXT` header.

### 5. Rolling Summarizer Service ([summarizer.py](file:///c:/Users/loq/Desktop/learn/personas/app/services/summarizer.py))
- Uses local **`qwen3:8b` via Ollama** (`/api/chat`, `format=` JSON schema, `think:false`) for structured output.
- Extracts summaries + user facts, embeds the facts (Ollama) and saves them as RAG search targets.

### 6. Live & Panel Services ([gemini_live.py](file:///c:/Users/loq/Desktop/learn/personas/app/services/gemini_live.py), [panel/](file:///c:/Users/loq/Desktop/learn/personas/app/services/panel/))
- `gemini_live.py`: builds the Live config — voice resolution, `recall_memory` + `route_to_agent` tools,
  language pin (`LIVE_LANGUAGE`), transcription, session resumption, sliding-window compression.
- `panel/router.py` + `panel/session.py`: the **testable panel brain** (floor routing, roster state, shared
  transcript, `build_agent_priming`). 17 unit tests cover it. Uses **LangGraph** (dependency) conceptually for orchestration.

---

## ⚙️ Configuration Setup (`app/config.py`)

Settings are managed using `pydantic-settings` to automatically validate variables defined in the `.env` file:

- `DATABASE_URL`: PostgreSQL connection string (e.g. `postgresql+asyncpg://user:pass@localhost:5432/db`).
- `GEMINI_API_KEY`: API key for Google GenAI (text chat + Live voice).
- `CHAT_MODEL`: Text generation target (`gemini-2.5-flash`).
- `LIVE_MODEL` / `LIVE_VOICE` / `LIVE_LANGUAGE`: Gemini Live model, default voice, and pinned language (`en-US`).
- **Ollama (local memory backends)**: `OLLAMA_BASE_URL` (default `http://localhost:11434`),
  `OLLAMA_EMBED_MODEL` (`nomic-embed-text`), `OLLAMA_SUMMARY_MODEL` (`qwen3:8b`). Memory layer requires Ollama running.
- `SHORT_TERM_MESSAGES` (12) · `SUMMARIZE_THRESHOLD` (10) · `RETRIEVE_TOP_K` (5).

> ⚠️ `SUMMARY_MODEL`/`EMBED_MODEL` Gemini settings exist but are **superseded** — embeddings + summaries
> now run locally on Ollama (`gemini-2.5-pro` had a free-tier quota of 0).
