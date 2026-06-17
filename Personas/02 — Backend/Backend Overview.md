---
title: "Backend Overview"
type: reference
status: active
updated: 2026-06-17
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
│   ├── conversations.py  # Session CRUD and manual summarization endpoints
│   ├── personas.py       # Persona CRUD and Knowledge Base document uploads
│   └── voice_ws.py       # Real-time dialog turn streaming WebSocket loop
├── models/               # SQLAlchemy Declarative Models
│   ├── __init__.py       # Model package registry
│   ├── conversation.py   # Conversation session model
│   ├── memory.py         # pgvector Memory model (Facts, Summaries, Docs)
│   ├── message.py        # Message model
│   └── persona.py        # Persona configuration model
├── schemas/              # Pydantic payloads and serialization schemas
├── services/             # Core business logic and LLM integrations
│   ├── embeddings.py     # text-embedding-004 wrapper
│   ├── gemini.py         # gemini-2.5-flash streaming generator
│   ├── memory.py         # Chunker and pgvector semantic retriever
│   ├── prompt_builder.py # System instructions builder and context injector
│   └── summarizer.py     # gemini-2.5-pro structured summarizer
├── static/               # Client CSS and client-side JS (ws.js)
├── templates/            # Jinja2 HTML templates
├── web/                  # HTML Web views
│   └── views.py          # Dashboard, chat, and persona form renderers
├── config.py             # Settings loader from system environment (.env)
├── db.py                 # Async SQLAlchemy session setup & engine pooling
└── main.py               # Main application startup entrypoint
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
- Handles conversation creation and history lists.
- `POST /{id}/summarize`: Manual testing trigger. Invokes `SummarizerService.maybe_summarize` with `force=True`.

### 3. Dialogue WebSocket Loop ([voice_ws.py](file:///c:/Users/loq/Desktop/learn/personas/app/api/voice_ws.py))
- Connected at `/ws/chat/{conversation_id}`.
- Handles user inputs, manages prompt injection, processes cancellations on user interruptions, and schedules summarization background tasks.

---

## 🛠️ Service Components Layer (`app/services/`)

### 1. LLM Generation Service ([gemini.py](file:///c:/Users/loq/Desktop/learn/personas/app/services/gemini.py))
- Uses `Client.aio.models.generate_content_stream` to stream response chunks asynchronously.
- Connects to the **`gemini-2.5-flash`** model to minimize latency.

### 2. Embedding Generator ([embeddings.py](file:///c:/Users/loq/Desktop/learn/personas/app/services/embeddings.py))
- Uses **`text-embedding-004`** to generate 768-dimension vectors.
- Supports batch operations to embedding lists of strings.

### 3. Memory & RAG Service ([memory.py](file:///c:/Users/loq/Desktop/learn/personas/app/services/memory.py))
- **Word-Aligned Sliding Window**: Chunks text documents on space boundaries to keep words intact.
- **Semantic retrieval**: Embeds query strings and retrieves facts/documents matching cosine distance criteria.

### 4. Prompt Assembler ([prompt_builder.py](file:///c:/Users/loq/Desktop/learn/personas/app/services/prompt_builder.py))
- Formats base persona settings.
- Appends narrative summaries and fact bullet points under a `### LONG-TERM MEMORY & CONTEXT` header.

### 5. Rolling Summarizer Service ([summarizer.py](file:///c:/Users/loq/Desktop/learn/personas/app/services/summarizer.py))
- Uses **`gemini-2.5-pro`** with strict Pydantic schema validation (`response_schema`) to generate structured JSON outputs.
- Extracts summaries and user facts, embedding and saving the latter as search targets.

---

## ⚙️ Configuration Setup (`app/config.py`)

Settings are managed using `pydantic-settings` to automatically validate variables defined in the `.env` file:

- `DATABASE_URL`: PostgreSQL connection string (e.g. `postgresql+asyncpg://user:pass@localhost:5432/db`).
- `GEMINI_API_KEY`: API key for Google GenAI services.
- `CHAT_MODEL`: Generation target (`gemini-2.5-flash`).
- `SUMMARY_MODEL`: Structured summarization target (`gemini-2.5-pro`).
- `EMBED_MODEL`: Embedding target (`text-embedding-004`).
- `SHORT_TERM_MESSAGES`: Number of recent turns retained (default: `12`).
- `SUMMARIZE_THRESHOLD`: Turn limits before summarization triggers (default: `10`).
