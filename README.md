# Aura — Multi-Persona Voice AI with Persistent Memory

A stateful, multi-persona **voice** AI platform. Talk (by voice or text) to curated or
custom AI personas that **remember** you across sessions — facts, preferences, and the gist
of past conversations. Run them one-on-one, or convene a **panel** where a host hands the
floor between multiple personas. Give them documents and images to work from, share your
screen live, and (optionally) let them read and write your Google Sheets.

Single-user personal project — no auth. Reasoning/voice run on the **Gemini API**; the
memory layer (embeddings + summarization) runs locally on **Ollama**; storage is
**Postgres + pgvector**; the UI is server-rendered **FastAPI + Jinja2 + HTMX**.

---

## Features

- **Personas** — a seeded set of built-ins (interviewer, tutor, coach, debate partner,
  therapist-style listener, …) plus a **custom persona builder** with AI-assisted drafting.
- **Persistent memory (RAG)** — each turn reconstructs context from a rolling summary and
  semantically-retrieved facts scoped to the persona, so it "remembers" across sessions.
- **Live voice** — full-duplex voice via the **Gemini Live API**, with live transcripts and
  barge-in.
- **Voice panels** — a saved roster of personas in one room; a host greets you and routes to
  a panelist when you ask for them by name. Panels persist their **roster and full
  transcript** and can be resumed.
- **Documents & images** — upload `.txt/.md/.pdf` documents (chunked + embedded for recall)
  and images (shown to the agent as visual context), managed in separate **Documents /
  Images** tabs, for both single agents and panels.
- **Screen share & capture** — share your screen live into a session (~1 fps), or snapshot
  the current screen and upload it — on both single agents and panels.
- **Google Sheets via MCP** *(optional, off by default)* — bridge a Google Sheets **MCP**
  server into the live session so the agent can read/write your sheets. See
  [`MCP_GOOGLE_SHEETS.md`](MCP_GOOGLE_SHEETS.md).

## Tech stack

- **Backend:** Python 3.12, FastAPI, async SQLAlchemy 2.0 + Alembic, Pydantic v2
- **Database:** Postgres 16 + pgvector
- **AI:** Gemini API (chat + Live voice) via `google-genai`; **Ollama** for local embeddings
  (`nomic-embed-text`) and summarization (`qwen3:8b`)
- **Frontend:** Jinja2 templates + HTMX + Tailwind CSS (CDN); vanilla JS for the voice client
- **Tests:** pytest + pytest-asyncio (providers mocked, isolated `*_test` database)

## Repository layout

```
personas/
├── app/
│   ├── main.py              # FastAPI app + router mounting + static
│   ├── config.py            # env-driven settings
│   ├── models/              # SQLAlchemy models (persona, conversation, message,
│   │                        #   memory, panel, panel_message, asset)
│   ├── alembic/             # migrations
│   ├── api/                 # REST + WebSocket routers (personas, conversations,
│   │                        #   panels, assets, live_ws, panel_ws, …)
│   ├── services/            # gemini, gemini_live, embeddings, memory, summarizer,
│   │                        #   documents, assets, panel/, mcp/
│   ├── web/views.py         # server-rendered pages
│   ├── templates/           # Jinja2 (base, index, chat, panel, panels_hub, partials/)
│   ├── static/js/           # live.js (voice + screen share), panel.js, ws.js
│   ├── seeds/personas.py    # built-in persona seeding
│   └── tests/
├── docker-compose.yml       # Postgres + pgvector
├── IMPLEMENTATION_PLAN.md   # original architecture/roadmap (historical)
├── AGENTS.md                # coding-agent operating protocol
└── MCP_GOOGLE_SHEETS.md     # optional MCP Sheets integration
```

## Prerequisites

- **Python 3.12**
- **Docker** (for Postgres + pgvector) — or your own Postgres 16 with the `vector` extension
- **[Ollama](https://ollama.com/)** running locally, with the models pulled:
  ```bash
  ollama pull nomic-embed-text
  ollama pull qwen3:8b
  ```
- A **Gemini API key** (for chat and Live voice). Voice needs access to a Gemini **Live**
  model — set `LIVE_MODEL` in `.env` to one you can use.

## Setup

```bash
# 1. Clone and create a virtualenv
git clone https://github.com/minhaj-mhd/personas.git
cd personas
python -m venv .venv

# 2. Install (editable). Add the [mcp] extra only if you want Google Sheets access.
.venv/Scripts/python.exe -m pip install -e app            # Windows
# ./.venv/bin/python -m pip install -e app                # macOS/Linux

# 3. Configure environment
cp .env.example .env        # then fill in GEMINI_API_KEY (see "Configuration" below)

# 4. Start Postgres + pgvector
docker compose up -d db

# 5. Apply migrations and seed the built-in personas
cd app
../.venv/Scripts/python.exe -m alembic upgrade head
cd ..
.venv/Scripts/python.exe -m app.seeds.personas
```

## Run

```bash
# From the repo root, using the venv interpreter (not system/Store Python):
.venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000
```

Open <http://127.0.0.1:8000> — the dashboard. From there:

- **Open Voice Panels** (home CTA / nav) → create or resume a panel.
- A persona card → its sessions, knowledge base, and image uploads.
- Inside a chat or panel, **Go Live / Start** for voice, **Share Screen** / **Capture** for
  visual input.

> **Tip:** use headphones for voice — echo cancellation is unavailable on most setups, so
> speaker output can leak into the mic.

## Testing

Tests mock all providers and run against an isolated `<db>_test` database (created
automatically; the dev DB is never touched). Postgres must be running.

```bash
cd app
../.venv/Scripts/python.exe -m pytest -q
```

## Configuration

Settings are read from `.env` (see [`app/config.py`](app/config.py) for all defaults).
Common keys:

| Key | Purpose | Default |
|---|---|---|
| `DATABASE_URL` | Async Postgres URL | `postgresql+asyncpg://personas:personas@localhost:5432/personas` |
| `GEMINI_API_KEY` | Gemini API key (chat + voice) | — |
| `LIVE_MODEL` | Gemini **Live** model for voice | `gemini-3.1-flash-live-preview` |
| `LIVE_VOICE` | Default prebuilt voice | `Puck` |
| `OLLAMA_BASE_URL` | Local Ollama endpoint | `http://localhost:11434` |
| `OLLAMA_EMBED_MODEL` | Embedding model | `nomic-embed-text` |
| `SHORT_TERM_MESSAGES` / `SUMMARIZE_THRESHOLD` / `RETRIEVE_TOP_K` | Memory tuning | `12` / `10` / `5` |
| `MCP_SHEETS_ENABLED` | Enable Google Sheets via MCP | `false` |

Secrets live in `.env` (gitignored) — never commit them.

## Optional: Google Sheets via MCP

Off by default. When enabled, live sessions launch a configured Google Sheets **MCP**
server and expose its tools to the agent. Full setup, architecture, and safety notes are in
[`MCP_GOOGLE_SHEETS.md`](MCP_GOOGLE_SHEETS.md).

## Notes

- Schema changes go through **Alembic** only (no hand-edited DB). See [`AGENTS.md`](AGENTS.md)
  for the full engineering/operating protocol.
- The historical design doc [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) predates some
  choices (the memory layer moved to local Ollama; voice went Live-first) — this README
  reflects the current state.
