---
title: "End-to-End System Architecture"
type: reference
status: active
updated: 2026-07-13
---

# 🗺️ End-to-End System Architecture

The single, current, code-verified map of the whole platform: every model/provider, every
data table, and every flow from a mic frame to a persisted memory. This reflects **what the
code actually does today** (verified 2026-07-13), which has moved well past
[`IMPLEMENTATION_PLAN.md`](file:///c:/Users/loq/Desktop/learn/personas/IMPLEMENTATION_PLAN.md)
(the original plan) and the older vault overviews. Where a subsystem has its own deep-dive
note, this doc links to it rather than restating it.

> **Scope note.** Single-user personal app — **no auth**. One FastAPI process serves the JSON
> API, the WebSocket endpoints, and the server-rendered UI. Postgres+pgvector is the only
> datastore; local **Ollama** and cloud **Gemini** are the model providers.

---

## 1. Models & providers (the hybrid stack)

The system is deliberately **hybrid**: cloud Gemini for anything realtime/conversational,
local Ollama for the memory layer (quota-free, private, cheap).

| Role                                           | Provider · Model                                               | Where      | Called from                                                                                                                      |
| ---------------------------------------------- | -------------------------------------------------------------- | ---------- | -------------------------------------------------------------------------------------------------------------------------------- |
| **Text chat** (streamed replies)               | Gemini **`gemini-2.5-flash`** (`CHAT_MODEL`)                   | cloud      | [gemini.py](file:///c:/Users/loq/Desktop/learn/personas/app/services/gemini.py) `generate_chat_stream`                           |
| **Persona draft** (brief → structured persona) | Gemini `gemini-2.5-flash`, JSON schema output                  | cloud      | `gemini.py` `draft_persona`                                                                                                      |
| **Live voice** (full-duplex audio)             | Gemini Live **`gemini-3.1-flash-live-preview`** (`LIVE_MODEL`) | cloud      | [gemini_live.py](file:///c:/Users/loq/Desktop/learn/personas/app/services/gemini_live.py) → `client.aio.live.connect`            |
| **Embeddings** (768-dim)                       | Ollama **`nomic-embed-text`** (`OLLAMA_EMBED_MODEL`)           | local      | [embeddings.py](file:///c:/Users/loq/Desktop/learn/personas/app/services/embeddings.py) `/api/embed`                             |
| **Summaries + fact extraction**                | Ollama **`qwen3:8b`** (`OLLAMA_SUMMARY_MODEL`)                 | local      | [summarizer.py](file:///c:/Users/loq/Desktop/learn/personas/app/services/summarizer.py) `/api/chat` (JSON schema, `think:false`) |
| **Browser STT/TTS** (V1 fallback)              | Web Speech API (`SpeechRecognition` + `SpeechSynthesis`)       | browser    | [ws.js](file:///c:/Users/loq/Desktop/learn/personas/app/static/js/ws.js)                                                         |
| **External tools** (optional)                  | **MCP server over stdio** (e.g. Google Sheets)                 | subprocess | [mcp/client.py](file:///c:/Users/loq/Desktop/learn/personas/app/services/mcp/client.py)                                          |
| **Web grounding** (optional)                   | Gemini `GoogleSearch` tool in the Live session                 | cloud      | `gemini_live.build_live_config(enable_search=True)`                                                                              |

> ⚠️ **Config vs. reality.** `EMBED_MODEL=text-embedding-004` and `SUMMARY_MODEL=gemini-2.5-flash`
> still exist in [config.py](file:///c:/Users/loq/Desktop/learn/personas/app/config.py) but are
> **not used** — the memory layer runs entirely on the two Ollama models above. They're legacy
> knobs from the original single-provider plan. `CHAT_MODEL` and `LIVE_MODEL` **are** live.
> See [[Master Plan — Local Memory Models (Ollama) (Subagent-Ready)]].

**Voice modes** (all share the same audio engine and memory layer):
- **Text chat** — type or push-to-talk browser STT; server streams Gemini text; browser TTS speaks it. The zero-dependency fallback.
- **Voice L1** — single-agent Gemini Live: native audio in/out, VAD, barge-in, `recall_memory` tool. [[Live Voice Session]]
- **Voice L2** — host-led multi-agent **panel**: one Live session at a time, floor handed between personas. [[Master Plan — Voice Panel (Host-Led, Subagent-Ready)]]

---

## 2. Data model (Postgres + pgvector)

Seven tables. All ids are UUID; timestamps are `timestamptz`. Managed by Alembic
([migrations](file:///c:/Users/loq/Desktop/learn/personas/app/alembic/versions/)).
Full detail: [[Database Schema and Migrations]].

```
personas ─1:N─ conversations ─1:N─ messages
   │                  │
   │                  └───────────── (last_summarized_message_id → summarization watermark)
   │
   ├─1:N─ memories        (persona-scoped: RAG store — summaries, facts, document chunks)
   └─1:N─ assets          (persona-scoped images; also panel-scoped)

panels ─1:N─ panel_messages          (saved roster + persisted panel transcript)
panels ─1:N─ assets (panel-scoped)
```

- **personas** — identity + structured prompt fields (`personality_traits` JSON, `speaking_style`,
  `goals`, `constraints`, `domain_expertise`), assembled `system_prompt`, `voice`, `temperature`,
  `is_builtin`. 7 built-ins seeded ([seeds/personas.py](file:///c:/Users/loq/Desktop/learn/personas/app/seeds/personas.py)) — see [[Persona Catalog]].
- **conversations** — one chat/voice session for a persona; `last_summarized_message_id` is the rolling-summary watermark.
- **messages** — `role` (user/assistant/system), `content`, `audio_url?`, `token_count?`.
- **memories** — the RAG store. `memory_type ∈ {summary, fact, document}`, `content`, `embedding VECTOR(768)`,
  `importance_score`, `metadata_` JSON (`source`, `chunk_index`, optional `panel_id`). Keyed by
  **`persona_id`** so recall spans a persona's past sessions. (`preference/goal/topic` types from the
  original plan are not produced — the summarizer emits `summary` + `fact`; ingestion emits `document`.)
- **assets** — binary uploads (images) as `BYTEA`, scoped to **either** a persona **or** a panel. These
  are things the model *sees* (visual context), never chunked/embedded — the opposite of documents. `kind` leaves room for future upload types.
- **panels** — a saved multi-agent panel: `name` + ordered `persona_ids` JSON roster.
- **panel_messages** — persisted panel transcript lines (`speaker` label + optional `persona_id`; FK-free on persona so deleting a persona never erases panel history).

**Two distinct "memory" concepts** — do not conflate:
1. **Application memory layer** = `memories` table (RAG) — the product feature. [[Memory Layer Overview]]
2. **Agent vault** = this `Personas/` folder — coding-agent continuity notes.

---

## 3. Backend layout

FastAPI app ([main.py](file:///c:/Users/loq/Desktop/learn/personas/app/main.py)) mounts 9 routers.
Deep dive: [[Backend Overview]].

**Services** ([app/services/](file:///c:/Users/loq/Desktop/learn/personas/app/services/))
- `gemini.py` — Gemini text: streamed chat + structured persona draft.
- `gemini_live.py` — Live session config/tools, session-resumption classification (`recoverable_disconnect`), image priming, screen-frame input.
- `embeddings.py` — Ollama embeddings (batched 64, retry w/ backoff for cold-start).
- `memory.py` — RAG: `retrieve_context`, `get_preamble_memories`, `ingest_document`, `chunk_text` (500 chars / 100 overlap).
- `summarizer.py` — rolling summarization + fact extraction (Ollama qwen3, JSON schema).
- `prompt_builder.py` — `assemble_system_prompt`, `format_retrieved_memories`, `inject_memories_into_prompt`.
- `documents.py` — text/PDF → text (pypdf), for RAG ingestion.
- `assets.py` — image validation + `get_scope_images` (visual context retrieval).
- `mcp/client.py` — bridge any MCP server's tools ↔ Gemini `FunctionDeclaration`s (see §5.7).
- `panel/` — `router.py` (deterministic floor routing), `session.py` (in-memory `PanelState`), `persistence.py` (transcript write-back).
- `search.py` · `analytics.py` · `export.py` — pure helpers for the Phase-5 features.

**Routers**
- REST: `personas`, `conversations`, `panels`, `assets`, `analytics`.
- WebSocket: `voice_ws` (text chat), `live_ws` (Voice L1), `panel_ws` (Voice L2).
- Pages: `web/views.py`.

---

## 4. HTTP surface (REST + pages)

**REST (JSON, consumed by HTMX + fetch)**
```
Personas      GET/POST /api/personas · GET/PUT/DELETE /api/personas/{id}
              POST /api/personas/draft                     (AI draft from a brief)
              POST/GET/DELETE /api/personas/{id}/documents (RAG knowledge base)
Conversations POST/GET /api/conversations · GET/DELETE /api/conversations/{id}
              GET /api/conversations/{id}/messages
              GET /api/conversations/search?q=            (ILIKE + snippet + count)
              GET /api/conversations/{id}/export?format=md
              POST /api/conversations/{id}/summarize       (force rolling summary)
Panels        POST/GET /api/panels · GET/DELETE /api/panels/{id}
              GET /api/panels/{id}/messages
              POST/DELETE /api/panels/{id}/members[/{persona_id}]   (roster edit)
              POST/GET /api/panels/{id}/images
              POST/GET/DELETE /api/panels/{id}/documents   (shared RAG for whole roster)
Assets        GET/DELETE /api/assets/{id}                  (serve raw bytes / delete)
Analytics     GET /api/analytics                           (totals + per-persona + est. spoken min)
Health        GET /health · GET /web/health-badge
```

**Pages (Jinja2 + HTMX)** — [web/views.py](file:///c:/Users/loq/Desktop/learn/personas/app/web/views.py)
```
/                     dashboard grid (index.html)
/personas/new         persona builder form           /personas/{id}/edit  edit form
/personas/{id}        persona sessions + KB (conversations.html)
/chat/{conversationId} text or Live voice chat (chat.html)
/panels               panels hub — create/resume (panels_hub.html)
/panel/{panel_id}     live panel view + persisted transcript (panel.html)
```

---

## 5. The flows (end to end)

### 5.1 Text chat turn loop — `WS /ws/chat/{conversation_id}`
[voice_ws.py](file:///c:/Users/loq/Desktop/learn/personas/app/api/voice_ws.py)

```
browser (ws.js)                         server (voice_ws)                providers
──────────────                          ─────────────────                ─────────
type / PTT STT ──{user_message,text}──▶ 1. persist user Message
                                        2. load last SHORT_TERM_MESSAGES-1 history
                                        3. memory.retrieve_context() ────▶ Ollama embed (RAG)
                                        4. inject memories into system prompt
                                        5. gemini.generate_chat_stream() ▶ Gemini 2.5-flash
        ◀───────{token, delta}────────  stream tokens as they arrive
        render bubble                   6. persist assistant Message
        ◀────{message_complete,text}──  7. asyncio: summarizer.maybe_summarize()  (async)
   browser SpeechSynthesis speaks
```
- **Interrupt / barge-in:** `{interrupt}` (or a new `user_message`) cancels the in-flight generation task; partial reply is saved with a `[interrupted]` marker.
- Client auto-reconnects the WS after a 3s backoff on close.

### 5.2 Live voice L1 — `WS /ws/live/{conversation_id}`
[live_ws.py](file:///c:/Users/loq/Desktop/learn/personas/app/api/live_ws.py) · engine [live.js](file:///c:/Users/loq/Desktop/learn/personas/app/static/js/live.js) · [[Live Voice Session]]

```
1. Load conversation+persona. Build memory PREAMBLE (get_preamble_memories:
   latest summary + top-5 facts, NO embedding call) → system instruction.
2. build_live_config(): tools = [recall_memory (+ MCP tools if enabled)]
   (+ GoogleSearch if LIVE_ENABLE_SEARCH), voice, session_resumption, sliding-window compression.
3. gemini_live.connect() → open Live session. Prime it with the persona's reference IMAGES
   (prime_session_with_images, turn_complete=False = standing visual context).
4. Full-duplex, two concurrent tasks over ONE session:
   • uplink   : browser mic 16k PCM16 (binary) ─▶ session.send_realtime_input(audio)
                also JSON {image_frame} for screen-share ticks ─▶ send_realtime_input(video)
   • downlink : session.receive() (per-turn generator, looped) yields:
                  - audio bytes 24k PCM16 ─▶ browser (gapless Web Audio scheduling)
                  - input/output transcription deltas ─▶ {input_transcript}/{output_transcript}
                  - interrupted (barge-in) ─▶ flush playback
                  - turn_complete ─▶ emit final transcripts + persist_turn(user, model)
                  - tool_call ─▶ handle_tool_call (recall_memory / MCP) ─▶ send_tool_response
5. On disconnect: summarizer.maybe_summarize(force=True) writes back the session's memory.
```
- **`recall_memory` tool** (`NON_BLOCKING`): mid-session RAG. Model calls it → `retrieve_context` (with embedding) → results returned as a `FunctionResponse` (scheduled `WHEN_IDLE`). This is how a Live session pulls memory *during* talk, not just at the preamble.
- **Session resumption** (§5.5): drops are resumed transparently on the same browser WS.
- **Vision:** uploaded images prime the session; screen-share streams ~1fps JPEG frames; one-shot screen capture also supported. [assets.py](file:///c:/Users/loq/Desktop/learn/personas/app/services/assets.py)
- **Audio caveat (no AEC on this hardware):** the client **gates mic uplink while assistant audio is scheduled** to stop the model hearing itself — trades speaker barge-in for audible replies (use headphones for barge-in). See `live.js` `startAudioIOLoop`.

### 5.3 Voice panel L2 (host-led) — `WS /ws/panel/{panel_id}`
[panel_ws.py](file:///c:/Users/loq/Desktop/learn/personas/app/api/panel_ws.py) · client [panel.js](file:///c:/Users/loq/Desktop/learn/personas/app/static/js/panel.js) · [[Master Plan — Voice Panel (Host-Led, Subagent-Ready)]]

**Invariant: exactly ONE Gemini Live session open at a time** (the 1:1 audio constraint). The
"panel" is an in-memory [`PanelState`](file:///c:/Users/loq/Desktop/learn/personas/app/services/panel/session.py)
(roster, active speaker, shared transcript) — the host "hears" everyone via that transcript, not a parallel audio stream.

```
1. Client → {select_roster, persona_ids}. active_id = None ⇒ HOST holds the floor.
2. HOST session: greets in one line, and its ONLY job is to call route_to_agent when the
   user names a panelist (build_host_instruction — never answers questions itself).
3. Floor switch fires on EITHER path:
     (a) LLM tool: route_to_agent(agent_name) → resolve_agent_name() tolerant match, OR
     (b) deterministic: detect_route() regex first-name match on the input transcript.
   → close current session, open the NAMED agent's session.
4. New agent primed with build_agent_priming(): its OWN long-term memory preamble
   + the shared panel transcript so far ⇒ "switch with full context".
5. Agents can also call recall_memory and MCP tools; they re-route if the user names someone else.
6. If the panel is SAVED: every user/agent line is appended to panel_messages (resumable).
7. Reference images (panel-scoped) prime each speaker; documents ingested per-roster-persona
   tagged with panel_id (shared knowledge base).
```

### 5.4 RAG retrieval flow
[memory.py](file:///c:/Users/loq/Desktop/learn/personas/app/services/memory.py) · [[How RAG and Persistent Memory Work]]

Two retrieval paths, both scoped to `persona_id`:
- **`retrieve_context(persona, conv, text)`** (text chat + `recall_memory` tool):
  1. Always include the **latest `summary`** for the conversation (continuity).
  2. Embed `text` (Ollama) → **cosine-distance** search over the persona's non-summary memories
     (`fact` + `document`), keep `distance < 0.7`, order ascending, `limit` (default 5 / `RETRIEVE_TOP_K`).
  3. `format_retrieved_memories()` renders a `### LONG-TERM MEMORY & CONTEXT` block (summary + `- [source]: chunk` facts/docs).
- **`get_preamble_memories(persona, conv)`** (Live/panel session start, **no embedding call** for speed):
  latest `summary` + top-5 non-summary memories by `importance_score`, then recency.

### 5.5 Rolling summarization / memory write-back
[summarizer.py](file:///c:/Users/loq/Desktop/learn/personas/app/services/summarizer.py)

```
maybe_summarize(conv, force?):
  1. messages after last_summarized_message_id = "unsummarized block".
  2. if not force and block < SUMMARIZE_THRESHOLD (10): skip.
  3. Ollama qwen3:8b, JSON schema {summary, facts[]}, prev summary + new block as context.
  4. write memories: 1× summary (importance 0.5, NO embedding)
                     N× fact   (importance 0.8, embedded via Ollama)
  5. advance last_summarized_message_id watermark.
Triggered: async after each text turn (§5.1) AND force=True on Live/panel disconnect (§5.2/5.3).
```

### 5.6 Document ingestion (RAG knowledge base)
[documents.py](file:///c:/Users/loq/Desktop/learn/personas/app/services/documents.py) + `memory.ingest_document`
```
upload (.txt/.md/.pdf or pasted text)
  → extract_upload_text (pypdf for PDF; UTF-8 else; 400 on unsupported binary / image-only PDF)
  → chunk_text (500/100)  → Ollama embed each chunk
  → memories rows: memory_type='document', metadata {source, chunk_index, panel_id?}
Persona KB: POST /api/personas/{id}/documents.  Panel KB: POST /api/panels/{id}/documents
(ingests into EVERY roster persona tagged with panel_id).
```

### 5.7 MCP external-tool flow (e.g. Google Sheets) — optional, off by default
[mcp/client.py](file:///c:/Users/loq/Desktop/learn/personas/app/services/mcp/client.py)

The app does **not** rely on any model's native MCP support. It bridges MCP → Gemini function calling,
so it works even inside the Live API:
```
MCP_SHEETS_ENABLED → build_sheets_provider() launches the MCP server over stdio (npx …)
  → list_tools()  → json_schema_to_gemini_schema → FunctionDeclarations
  → added to the Live config's tools (extra_function_declarations)
When the model calls one: handle_tool_call → mcp_provider.dispatch(name, args)
  → MCP call_tool → text result → FunctionResponse back into the Live session.
```
Shared across L1 and every L2 speaker; a failure to start is non-fatal (session runs without it).
Config: `MCP_SHEETS_COMMAND/ARGS/ENV`. Reference: `MCP_GOOGLE_SHEETS.md`.

### 5.8 Session resumption / reconnect (Live + panel)
`gemini_live.recoverable_disconnect` + the reconnect loops in `live_ws`/`panel_ws`.
```
Live server issues a resumption handle (captured on each server_content).
On a RECOVERABLE upstream drop (WS 1006 abnormal, 1008 GoAway/session-duration, going-away,
keepalive timeout, "internal error", …) → reconnect with the handle to continue the SAME
logical session. Exponential backoff 0.5·2^n capped 5s, MAX_RECONNECTS=5 (budget resets when
a healthy new handle arrives). Fatal errors (bad auth/model, exhausted quota) are NOT retried.
Client keeps the mic/audio pipeline running across a resume ({reconnecting}→{resumed}); it does
NOT re-init audio (that's reserved for the first {ready}).
```

### 5.9 Persona creation (AI-assisted)
`POST /api/personas/draft` → Gemini structured-JSON draft (name, traits, style, goals, constraints,
expertise, temperature, voice) → user reviews/edits the form → `POST /api/personas` assembles the
`system_prompt` via `assemble_system_prompt` and persists (`is_builtin=false`).

### 5.10 Phase-5 utilities
- **Search** — `GET /api/conversations/search`: ILIKE over message content, grouped by conversation, `make_snippet` excerpt + match count.
- **Export** — `GET /api/conversations/{id}/export?format=md`: `render_conversation_markdown` → downloadable `.md` (pdf returns 400).
- **Analytics** — `GET /api/analytics`: totals + per-persona counts, user/assistant split, `estimate_speaking_minutes` (chars→words→min @150 wpm).

---

## 6. Orchestration — there is **no LangGraph**

The user's mental model mentioned "LangGraph flows"; the **actual code uses none**. `langgraph`
was *mentioned/installed* during panel planning and the design is described as "LangGraph-style,"
but no `StateGraph`/graph runtime appears anywhere in `app/`. Orchestration is:

- **Panel floor control** = a **deterministic router** ([`detect_route`](file:///c:/Users/loq/Desktop/learn/personas/app/services/panel/router.py), regex first-name / `@name` / host-phrase match) **plus** an **LLM `route_to_agent` function tool** for indirect/mispronounced address — resolved by `resolve_agent_name`. State is a plain in-memory `PanelState` dataclass.
- **Per-turn control** = the FastAPI async WebSocket loops themselves (asyncio tasks for uplink/downlink, `asyncio.create_task` for tool calls and summarization).
- **Tool use** = Gemini **function calling** (`recall_memory`, `route_to_agent`, MCP-bridged tools) handled manually via `send_tool_response` (the Live API has no automatic tool handling).

So: a hand-rolled, testable, deterministic control layer + Gemini function calling — **not** a graph framework.

---

## 7. Frontend

Server-rendered Jinja2 + HTMX + Tailwind/HTMX/FontAwesome via CDN (no Node build). The only real
JS is the three voice clients. [[Frontend Overview]].

| Client | File | Endpoint | Role |
|---|---|---|---|
| Text chat | [ws.js](file:///c:/Users/loq/Desktop/learn/personas/app/static/js/ws.js) | `/ws/chat/{id}` | streamed text + Web Speech STT/TTS, PTT (spacebar), auto-reconnect |
| Live voice | [live.js](file:///c:/Users/loq/Desktop/learn/personas/app/static/js/live.js) `LiveAudioClient` | `/ws/live/{id}` | mic 16k↑ / 24k↓ audio engine, screen-share, resume handling, mic-gating |
| Panel | [panel.js](file:///c:/Users/loq/Desktop/learn/personas/app/static/js/panel.js) `PanelAudioClient extends LiveAudioClient` | `/ws/panel/{id}` | `select_roster` handshake, `active_speaker`/`handoff` UI |

**WebSocket contracts (server → client):**
- chat: `token` · `message_complete` · `interrupted` · `error` · `info`
- live: `ready` · `resumed` · `reconnecting` · `input_transcript` · `output_transcript` · `interrupted` · `turn_complete` · `go_away` · `error`
- panel: `ready(roster)` · `active_speaker` · `transcript(speaker)` · `handoff` · `interrupted` · `turn_complete` · `reconnecting` · `resumed` · `error`

**Client → server:** chat `{user_message}`/`{interrupt}`; live/panel binary mic frames + JSON `{client_info}`/`{image_frame}`/`{stop|audio_end}`; panel first msg `{select_roster, persona_ids}`.

---

## 8. Configuration & runtime

[config.py](file:///c:/Users/loq/Desktop/learn/personas/app/config.py) (pydantic-settings, `.env`):
`GEMINI_API_KEY`, `CHAT_MODEL`, `LIVE_MODEL`, `LIVE_VOICE`, `LIVE_ENABLE_SEARCH`, `OLLAMA_*`,
`SHORT_TERM_MESSAGES=12`, `SUMMARIZE_THRESHOLD=10`, `RETRIEVE_TOP_K=5`, `MCP_SHEETS_*`, `TESTING`.

**Runtime deps:** Postgres+pgvector (Docker `personas-db`), local Ollama (`nomic-embed-text`,
`qwen3:8b`), a `GEMINI_API_KEY`. Server runs from the project `.venv`. Tests run against an
isolated `personas_test` DB with **all providers mocked** (`app/tests/`, ~15 suites incl.
`test_live_reconnect`, `test_panel_reconnect`, `test_mcp`, `test_assets`, `test_documents`).
Ops/dev gotchas: [[06 — Logs/Current Context]] and the agent memory note on the DB container.

---

## 9. Where to go deeper
- [[Architecture Overview]] · [[Backend Overview]] · [[Database Schema and Migrations]] · [[System Walkthrough]]
- [[Memory Layer Overview]] · [[How RAG and Persistent Memory Work]] · [[Memory in a Live Voice Session]]
- [[Live Voice Session]] · [[Master Plan — Live Voice (Subagent-Ready)]] · [[Master Plan — Voice Panel (Host-Led, Subagent-Ready)]] · [[Master Plan — Local Memory Models (Ollama) (Subagent-Ready)]]
- [[Persona Catalog]] · [[Frontend Overview]]
- Canonical original plan (diverged): [`IMPLEMENTATION_PLAN.md`](file:///c:/Users/loq/Desktop/learn/personas/IMPLEMENTATION_PLAN.md)
