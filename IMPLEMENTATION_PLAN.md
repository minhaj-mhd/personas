# AI Multi-Persona Voice Agent Platform — Implementation Plan

> **📌 Status (2026-06-25):** This is the *original* plan. Build has progressed through **Phase 5**.
> What actually shipped differs in places — the **memory layer runs on local Ollama** (`nomic-embed-text` +
> `qwen3:8b`), not Gemini embeddings; **voice went Live-first** (Gemini Live single-agent **L1** + a host-led
> **multi-agent voice panel L2**) rather than the turn-based pipeline below. For current state, see the vault:
> `Personas/06 — Logs/Current Context.md`, `Personas/03 — Memory Layer/`, and
> `Personas/01 — Architecture/Master Plan — Voice Panel (Host-Led, Subagent-Ready).md`.

A stateful, multi-persona voice AI platform. Each agent has a distinct identity, persistent
memory, and conversational style. Users switch personas, talk by voice, and resume past
sessions with full contextual continuity. Reasoning runs on the **Gemini API**, backend on
**FastAPI**, frontend served by **Jinja2 + HTMX**, with a dedicated **memory layer** combining
recent history and summarized long-term knowledge. Single-user personal project — no auth.

---

## 1. Key Architecture Decisions (recommendations + rationale)

These are the forks that shape everything else. Defaults are chosen for a fast, correct MVP
that still scales. Each notes the alternative if you want to change course.

| Decision | Recommendation | Why | Alternative |
|---|---|---|---|
| **Voice pipeline** | **Turn-based pipeline first** (STT → Gemini text → TTS), upgrade to streaming later | The memory layer is the differentiator. A turn-based loop lets you inject retrieved memories into the prompt **every turn** with full control. Cleaner to build and debug. | Gemini **Live API** (native bidirectional audio) for lowest latency — adopt in Phase 5. Memory injection mid-session is harder there. |
| **STT (speech-to-text)** | Browser **Web Speech API** for MVP (free, zero infra), server **Gemini audio** transcription as fallback/upgrade | Ships instantly, no audio upload. | Whisper (local/API), Deepgram, Azure Speech for accuracy/streaming. |
| **TTS (text-to-speech)** | Browser **SpeechSynthesis** for MVP, **Gemini TTS** / ElevenLabs for natural voices | Zero-cost baseline; swap per-persona `voice` later. | ElevenLabs (best quality), OpenAI TTS, Azure. Abstract behind a `TTSProvider` interface. |
| **LLM** | Gemini `gemini-2.5-flash` for dialogue (fast, cheap), `gemini-2.5-pro` for summarization quality | Flash keeps conversation latency low; summaries are infrequent so quality pays off. | All-flash to cut cost. |
| **Embeddings** | Gemini `text-embedding-004` (768-dim) | Single-provider, strong quality. | OpenAI `text-embedding-3-small`. |
| **Database** | **Postgres + pgvector** | One store for relational data *and* vector search — no separate vector DB to run for MVP. | Qdrant/FAISS when vector volume or filtering needs grow (Phase 5). SQLite only for throwaway local dev. |
| **Frontend** | **FastAPI + Jinja2 + HTMX** (server-rendered, light) | One Python codebase, no Node build step; keeps FastAPI's native async/WebSocket that the voice loop needs. | Next.js/React SPA if the UI later grows into a rich client app. |
| **Auth** | **None for now** — single-user personal app | Nothing to log into or secure; everything belongs to "the" user. Skips a whole subsystem. | Add a `users` table + JWT (or Clerk/Auth0) later *only* if it goes multi-user. |
| **Realtime transport** | **WebSocket** for streaming tokens + audio status; REST for CRUD | Streaming token output makes voice feel responsive. | SSE (one-way) if you drop client→server streaming. |

**Single-provider bias:** STT, LLM, TTS, and embeddings can all be Gemini. That keeps one API
key, one billing surface, and consistent behavior — recommended for MVP. All four are wrapped
behind interfaces so any can be swapped.

---

## 2. Tech Stack

**Backend**
- Python 3.12, **FastAPI**, Uvicorn
- **SQLAlchemy 2.0** (async) + **Alembic** migrations
- **Postgres 16 + pgvector**
- **Pydantic v2** (schemas/validation), `pydantic-settings` (config)
- `google-genai` (Gemini SDK)
- **Jinja2** templates (`fastapi.templating`) for server-rendered pages
- `pytest`, `httpx`, `pytest-asyncio` (tests)

**Frontend (server-rendered, light — no Node toolchain)**
- **Jinja2** templates served directly by FastAPI
- **HTMX** for partial updates (persona grid, conversation list, message history) without a SPA
- **Tailwind CSS** via CDN/Play build (drop-in; no build step required)
- Vanilla **JS/TS** only where genuinely interactive: the voice client
- Web Speech API (`SpeechRecognition`, `SpeechSynthesis`)
- native **WebSocket** for streaming tokens

**Infra / Dev**
- **Docker Compose** (api+web, db) for local dev — a single app container
- Ruff + Black (py)
- GitHub Actions CI (lint, test)

---

## 3. Repository Structure

```
personas/
├── docker-compose.yml
├── .env.example
├── README.md
├── IMPLEMENTATION_PLAN.md
│
└── app/                          # single FastAPI app (API + server-rendered UI)
    ├── pyproject.toml
    ├── alembic/                  # migrations
    ├── main.py                   # FastAPI app, router mounting, static mount, CORS
    ├── config.py                 # settings (env-driven)
    ├── db.py                     # async engine, session dependency
    ├── models/                   # SQLAlchemy ORM models
    │   ├── persona.py
    │   ├── conversation.py
    │   ├── message.py
    │   └── memory.py
    ├── schemas/                  # Pydantic request/response models
    ├── api/                      # JSON routers (consumed by HTMX + voice client)
    │   ├── personas.py
    │   ├── conversations.py
    │   ├── messages.py
    │   └── voice_ws.py           # WebSocket chat endpoint
    ├── web/                      # page routers returning Jinja templates / HTMX partials
    │   └── views.py              # /, /dashboard, /personas/{id}, /chat/{id}, /personas/new
    ├── services/
    │   ├── gemini.py             # LLM client wrapper (chat + summarize)
    │   ├── embeddings.py         # embedding generation
    │   ├── memory.py             # short-term window + long-term retrieve/write
    │   ├── summarizer.py         # rolling conversation summarization
    │   ├── prompt_builder.py     # assembles the final prompt
    │   └── tts/                  # TTSProvider interface + impls
    ├── core/
    │   └── deps.py               # shared dependencies (DB session, pagination)
    ├── seeds/personas.py         # built-in persona definitions
    ├── templates/                # Jinja2
    │   ├── base.html             # layout, HTMX + Tailwind CDN includes
    │   ├── dashboard.html        # persona grid
    │   ├── conversations.html    # conversation list for a persona (resume / new)
    │   ├── chat.html             # voice chat interface
    │   ├── persona_form.html     # custom persona builder
    │   └── partials/             # HTMX fragments (message row, persona card, conv row)
    └── static/
        ├── css/                  # any non-CDN overrides
        └── js/
            ├── voice.js          # mic STT, audio TTS playback, voice-state machine
            └── ws.js             # WebSocket client (streamed tokens -> DOM)
```

Note: no auth for now — single user. If multi-user is added later, introduce a `users` table, an
httpOnly cookie session, and one auth dependency; nothing else in this layout needs to move.

---

## 4. Data Model

Refined from the brief — single-user, so **no `users` table**; adds persona seeding,
summarization bookkeeping, and proper types/indexes. Vector column uses pgvector.

```sql
-- PERSONAS  (built-in: seeded with is_builtin=true; custom: user-created)
personas(
  id UUID PK,
  name TEXT NOT NULL,
  description TEXT,
  system_prompt TEXT NOT NULL,        -- assembled from the template in §7
  personality_traits JSONB,           -- {tone, formality, verbosity, ...}
  speaking_style TEXT,
  goals TEXT,
  constraints TEXT,
  domain_expertise TEXT,
  voice TEXT,                         -- voice id for TTS provider
  temperature REAL DEFAULT 0.8,
  is_builtin BOOLEAN DEFAULT false,   -- seeded persona vs user-created
  created_at TIMESTAMPTZ DEFAULT now()
)

-- CONVERSATIONS
conversations(
  id UUID PK,
  persona_id UUID FK->personas NOT NULL,
  title TEXT,
  last_summarized_message_id UUID NULL,  -- summarization watermark
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
)
INDEX (persona_id, updated_at DESC)

-- MESSAGES
messages(
  id UUID PK,
  conversation_id UUID FK->conversations NOT NULL,
  role TEXT CHECK (role IN ('user','assistant','system')),
  content TEXT NOT NULL,
  audio_url TEXT NULL,                 -- optional stored audio
  token_count INT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
)
INDEX (conversation_id, created_at)

-- MEMORY STORE
memories(
  id UUID PK,
  conversation_id UUID FK->conversations NOT NULL,
  persona_id UUID FK->personas NOT NULL,  -- enables cross-conversation recall per persona
  memory_type TEXT CHECK (memory_type IN ('summary','fact','preference','goal','topic')),
  content TEXT NOT NULL,               -- the summarized text / fact
  embedding VECTOR(768),               -- pgvector; NULL for 'summary' if not retrieved by similarity
  importance_score REAL DEFAULT 0.5,
  created_at TIMESTAMPTZ DEFAULT now()
)
INDEX USING ivfflat (embedding vector_cosine_ops)
INDEX (persona_id, memory_type)
```

Scoping note: `memories` keyed by `persona_id` (not only `conversation_id`) so a persona can
recall facts across past sessions. If multi-user lands later, add `user_id` here and to the
retrieval filter. Set `cross_persona_shared_memory` as a later flag if you want shared facts.

---

## 5. Backend Design

### REST endpoints
```
GET    /personas                 -> built-ins + custom
POST   /personas                 -> create custom (prompt builder)
GET    /personas/{id}
PATCH  /personas/{id}
DELETE /personas/{id}

GET    /conversations?persona_id=        -> list (resume points)
POST   /conversations                    -> start new {persona_id, title?}
GET    /conversations/{id}               -> meta
GET    /conversations/{id}/messages      -> paginated history
DELETE /conversations/{id}
POST   /conversations/{id}/summarize     -> force summarization (admin/debug)
GET    /conversations/{id}/export?fmt=md|pdf
```

### WebSocket: `/ws/conversations/{id}`
No auth for now (single user). Message protocol (JSON):

```
client -> server:
  { "type": "user_message", "text": "<transcript>" }
  { "type": "interrupt" }                       # barge-in: stop generation

server -> client:
  { "type": "token", "delta": "..." }           # streamed LLM tokens
  { "type": "message_complete", "message_id": "...", "text": "..." }
  { "type": "tts_ready", "audio_url": "..." }    # if server-side TTS
  { "type": "memory_updated" }                   # summary/fact written
  { "type": "error", "detail": "..." }
```

### Per-turn flow (the core loop)
```
1. Receive user_message over WS.
2. Persist user message.
3. memory.build_context(conversation, user_text):
     a. short-term  = last N messages (token-budgeted)
     b. long-term   = vector search memories by embed(user_text),
                      filtered to persona_id, top-k by similarity*importance
4. prompt_builder.assemble(persona.system_prompt, long_term, short_term, user_text)
5. Stream Gemini response (temperature = persona.temperature) -> emit tokens.
6. Persist assistant message.
7. summarizer.maybe_summarize(conversation):
     if unsummarized_messages > threshold:
        summarize older block -> write 'summary' memory (+embedding),
        extract facts/preferences/goals -> write typed memories,
        advance last_summarized_message_id.
8. (optional) server TTS -> emit tts_ready.
```

---

## 6. Memory Layer Design

This is the heart of the platform. Two tiers, assembled fresh each turn.

### Short-term memory (recent window)
- Pull the last **N messages** (start N=12) for the conversation.
- Enforce a **token budget** (e.g. 2k tokens). If exceeded, drop oldest first — but those are
  already captured in summaries, so nothing is lost.

### Long-term memory (summarized + retrieved)
- **Summarization (rolling):** when unsummarized messages exceed a threshold (e.g. 10), send
  that block to Gemini with a summarization prompt that emits: (1) a concise narrative summary,
  (2) discrete user **facts**, **preferences**, **goals**, **topics**. Store each as a typed
  `memories` row; embed facts/preferences/goals for retrieval.
- **Retrieval (RAG):** embed the current user input, cosine-search `memories` scoped to
  `persona_id`, rank by `similarity * importance_score`, take top-k (start k=5).
  Always also include the **most recent `summary`** memory regardless of similarity (continuity).
- **Importance scoring:** default 0.5; bump facts/goals (0.8), decay topics over time. Tune later.

### Prompt assembly (`prompt_builder`)
```
[SYSTEM]
  <persona.system_prompt>            # identity, style, goals, constraints, expertise

[LONG-TERM MEMORY]
  Summary of past sessions: <latest summary>
  Known facts/preferences/goals:
    - <retrieved memory 1>
    - <retrieved memory 2> ...

[RECENT CONVERSATION]
  user: ...
  assistant: ...
  (last N, token-budgeted)

[CURRENT USER INPUT]
  user: <current text>
```

### Resume behavior
On reopening a conversation, the first turn naturally rebuilds context: latest summary + recent
tail + retrieved facts. No special "load" step needed beyond fetching history for display — the
agent "remembers" because the prompt is reconstructed from persisted memory every turn.

---

## 7. Persona System

### System-prompt template
Custom personas are assembled from structured fields so the prompt builder (UI) stays simple:
```
You are {name}, {description}.
PERSONALITY: {personality_traits as prose}
SPEAKING STYLE: {speaking_style}   # concise, warm, Socratic, etc.
GOALS: {goals}
CONSTRAINTS: {constraints}         # e.g. "never give medical advice"
DOMAIN EXPERTISE: {domain_expertise}
Always stay in character. Keep spoken responses natural and conversational (1-4 sentences
unless asked to elaborate), since the user is talking, not reading.
```

### Seed personas (built-in, `is_builtin`)
Interviewer (technical / HR / behavioral variants) · Language Specialist (grammar,
pronunciation, vocabulary) · Teacher/Tutor · Story Teller · Career Coach · Debate Partner ·
Therapist-style Listener (explicit **non-clinical** constraint, with a safety/escalation note).

### Custom personas
`personas/new` form maps 1:1 to persona fields → backend assembles `system_prompt`. Editable;
stored with `is_builtin=false`.

---

## 8. Frontend Design (server-rendered + HTMX)

Pages are Jinja2 templates served by FastAPI. HTMX handles partial updates (lists, history,
forms) so there's no SPA. Only the **voice chat** page carries real custom JS.

**Routes / flow** (all server-rendered)
```
/ , /dashboard         -> persona grid (built-ins + custom)  [Home]
/personas/{id}         -> conversation list (resume / new)
/chat/{conversationId} -> voice chat interface
/personas/new          -> custom persona builder (form -> POST /api/personas)
```

**HTMX usage (no JS needed)**
- Persona grid / conversation list: plain server-rendered pages.
- "New conversation": `hx-post` → returns a redirect/partial to the chat page.
- Persona builder: form `hx-post` to `/api/personas`, swaps in a success partial.
- Loading older history: `hx-get` paginated `partials/message_row` fragments.

**Voice chat page (the centerpiece — the only real JS, `voice.js` + `ws.js`)**
- Chat page renders existing history server-side (instant resume); JS attaches for live turns.
- Mic button → Web Speech `SpeechRecognition` → interim + final transcript shown live.
- On final transcript: send `user_message` over the WebSocket.
- Stream `token` deltas appended into the assistant bubble in the DOM.
- On `message_complete`: speak via `SpeechSynthesis` (or play `tts_ready` audio).
- Barge-in: if the user starts speaking while the assistant talks, cancel synthesis + send `interrupt`.
- A tiny **state machine** drives the UI: idle → listening → thinking → speaking.

**State**
- Server is the source of truth (DB). Page loads render current state directly.
- The only client-side state is the live voice session (WS handle, transcript buffer, playback
  flag) held in `voice.js` — no client state library needed.

---

## 9. Phased Roadmap

Each phase ends in something runnable. Estimates assume one focused developer.

### Phase 0 — Scaffold (0.5 wk)
- Docker Compose (single app container + Postgres+pgvector). `.env.example`. Health-check endpoint.
- Alembic baseline. FastAPI app with Jinja2 `base.html` + static mount + Tailwind/HTMX CDN. CI (lint+test).
- **Done when:** `docker compose up` serves a rendered base page + API `/health`.

### Phase 1 — Persona CRUD + dashboard (0.5 wk)
- Persona model + endpoints, seed built-in personas, custom-persona builder.
- Dashboard grid template (built-ins + custom).
- **Done when:** the dashboard renders the personas and a custom persona can be created/edited.

### Phase 2 — Text conversation loop (1 wk)
- Conversation + Message models/endpoints. Gemini service (streaming).
- WebSocket chat (text only), `prompt_builder` with persona prompt + short-term window.
- Chat UI: type a message, see streamed reply, history persists + resumes.
- **Done when:** stateful **text** chat with a persona works and resumes.

### Phase 3 — Memory layer (1.5 wk)
- Embeddings service, `memories` table + pgvector index.
- Summarizer (rolling) + typed fact/preference/goal extraction.
- Retrieval + full prompt assembly (long-term tier). Importance scoring.
- **Done when:** start a session, mention facts, close it, start a **new** session with the same
  persona → it recalls those facts. This is the core proof.

### Phase 4 — Voice (1 wk)
- Browser STT (mic → transcript) and TTS (speak replies). Voice-state UI, barge-in/interrupt.
- Per-persona `voice` selection. Optional server-side Gemini/ElevenLabs TTS behind interface.
- **Done when:** full hands-free voice conversation, end to end.

### Phase 5 — Enhancements (ongoing, pick by value)
- Streaming voice via **Gemini Live API** (lowest latency).
- Qdrant/FAISS if vector volume warrants; cross-persona shared memory flag.
- Conversation search; export to Markdown/PDF; analytics dashboard (speaking time, topics).
- Emotion-adaptive speaking style; multi-provider TTS picker; prompt-builder polish.

**MVP = Phases 0–4** (~4–5 weeks). Phase 3 is the differentiator and the highest-risk piece —
protect time for it.

---

## 10. Testing Strategy
- **Unit:** prompt assembly (snapshot the assembled prompt), memory retrieval ranking,
  summarization parsing.
- **Integration:** conversation lifecycle, WS turn loop (mock Gemini), resume-recall
  test (the Phase 3 proof, automated).
- **Provider mocking:** wrap Gemini/embeddings/TTS behind interfaces; inject fakes in tests so
  the suite runs offline and deterministically.
- **UI/e2e:** Playwright against the rendered pages for dashboard→chat→resume; unit-test the
  `voice.js` state machine (idle/listening/thinking/speaking) in isolation.

## 11. Deployment
- **Containers:** one app container (Uvicorn/Gunicorn serving API + templates + static), managed Postgres w/ pgvector.
- **Hosts:** Fly.io / Render / Railway for app+db — a single service, no separate frontend deploy.
- **Secrets:** `GEMINI_API_KEY`, `DATABASE_URL`, TTS keys via env / secret store.
- **Migrations:** Alembic on deploy. **WSS:** serve WebSocket over TLS in prod.

## 12. Risks & Mitigations
| Risk | Mitigation |
|---|---|
| Voice latency feels sluggish | Stream tokens; start TTS on first sentence; move to Gemini Live API in P5. |
| Memory recall is noisy/irrelevant | Scope retrieval tightly (per persona), rank by similarity×importance, always include latest summary, keep k small; iterate on prompts. |
| Token/context blowup on long chats | Rolling summarization + token-budgeted window; summaries replace raw old turns. |
| Browser STT/TTS quality varies | Abstract providers; offer server Gemini/ElevenLabs upgrade. |
| Cost creep (LLM + embeddings) | Flash for chat, summarize infrequently, cache embeddings, batch where possible. |
| Therapist persona safety | Hard constraint in system prompt + non-clinical disclaimer + crisis-resource escalation text. |

## 13. Configuration (`.env.example`)
```
DATABASE_URL=postgresql+asyncpg://user:pass@db:5432/personas
GEMINI_API_KEY=
EMBED_MODEL=text-embedding-004
CHAT_MODEL=gemini-2.5-flash
SUMMARY_MODEL=gemini-2.5-pro
SHORT_TERM_MESSAGES=12
SUMMARIZE_THRESHOLD=10
RETRIEVE_TOP_K=5
# optional voice providers
ELEVENLABS_API_KEY=
```

---

## Immediate Next Steps
1. Confirm the four headline choices (turn-based voice first, Postgres+pgvector, FastAPI+Jinja2+HTMX, single-provider Gemini).
2. Scaffold Phase 0 (Docker Compose + FastAPI health + Jinja2 base page + Alembic baseline).
3. Build Phases 1→4 in order; treat the **Phase 3 resume-recall test** as the definition of done for "persistent memory."
```
