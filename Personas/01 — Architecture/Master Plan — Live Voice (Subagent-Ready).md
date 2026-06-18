---
title: "Master Plan — Live Voice (Subagent-Ready)"
type: reference
status: active
updated: 2026-06-19
---

# 🗺️ Master Plan — Live Voice (Subagent-Ready)

Hand-off plan for building **Voice L1** (Gemini Live single-agent free-talk) and the follow-on
multi-agent work. Decomposed into **independent Work Packages (WPs)** with **shared contracts** so
parallel subagents integrate cleanly. Strategy/rationale: [[05 — Frontend/Voice Session Roadmap — V1 to V5]].

## 0. How subagents should use this doc
- **Read §2 (Shared Contracts) first.** They are the integration seams. A WP may *implement* a contract
  but must not *change its shape* without updating §2 here.
- Each WP is self-contained: **objective · files · steps · acceptance**. Pick a WP, stay in its files.
- Grounding is real (codebase + `google-genai 2.2.0` API already verified). Pointers are given; trust §2
  for exact API shapes rather than re-deriving.
- ⚠️ `app/config.py` **already has** the `LIVE_*` settings (landed as groundwork). Don't re-add.

---

## 1. Context snapshot
- **Product:** AI multi-persona voice agent with persistent memory. Stack: FastAPI + Jinja/HTMX,
  Postgres + pgvector, `google-genai` (Gemini), WebSocket streaming.
- **Shipped:** Phases 0–3 (persona CRUD, text chat loop, Memory Layer/RAG + rolling summaries) and
  **Voice V1** (Web Speech push-to-talk — kept as no-dependency fallback).
- **Pivot (2026-06-18):** Live-first. Free unlimited Gemini Live + tool-RAG ⇒ old V2/V3/V4 deprecated.
  Build **L1** next. See replan doc above.

---

## 2. SHARED CONTRACTS (authoritative — read first)

### 2.1 Config — `app/config.py` (DONE)
`LIVE_MODEL` (override per your Live model access), `LIVE_VOICE` (default `"Puck"`),
`LIVE_ENABLE_SEARCH` (bool), `LIVE_INPUT_SAMPLE_RATE=16000`, `LIVE_OUTPUT_SAMPLE_RATE=24000`.

### 2.2 Live WebSocket protocol — `/ws/live/{conversation_id}`
**Client → server**
- **Binary frame** = raw **PCM16, mono, 16 kHz** mic audio (stream continuously while live).
- JSON `{ "type": "audio_end" }` (optional, on stop) · `{ "type": "stop" }`.

**Server → client**
- **Binary frame** = raw **PCM16, mono, 24 kHz** model audio → enqueue & play in order.
- JSON events:
  - `{ "type": "ready", "voice": "<name>", "model": "<id>" }` — connected; client starts capture.
  - `{ "type": "input_transcript", "text": "...", "final": bool }` — user speech (STT of mic).
  - `{ "type": "output_transcript", "text": "...", "final": bool }` — assistant speech.
  - `{ "type": "interrupted" }` — barge-in detected → client **flushes playback queue immediately**.
  - `{ "type": "turn_complete" }` — model turn ended.
  - `{ "type": "info" | "error", "detail": "..." }` · `{ "type": "go_away" }` — server about to drop; resume.

### 2.3 `recall_memory` function tool (mid-session RAG)
- Declaration: `name="recall_memory"`, `behavior=types.Behavior.NON_BLOCKING`,
  params = OBJECT `{ query: STRING (required) }`.
- On a tool call: run `MemoryService.retrieve_context(persona_id, conversation_id, query)`, format via
  `format_retrieved_memories(...)`, reply with
  `types.FunctionResponse(id=fc.id, name="recall_memory", response={"result": <text>}, scheduling=types.FunctionResponseScheduling.WHEN_IDLE)`.
- Handle the call in a **spawned task** so the downlink keeps reading (NON_BLOCKING semantics).

### 2.4 Service signatures (target)
- `app/services/gemini_live.py`
  - `resolve_voice(persona_voice: str | None) -> str`
  - `build_system_instruction(base_prompt: str, memory_block: str) -> str`
  - `recall_memory_declaration() -> types.FunctionDeclaration`
  - `build_live_config(system_instruction: str, voice: str, temperature: float, enable_search: bool) -> types.LiveConnectConfig`
  - `class GeminiLiveService: connect(config) -> async context manager` (wraps `client.aio.live.connect(model=settings.LIVE_MODEL, config=config)`)
- `app/services/memory.py` — add `get_preamble_memories(persona_id, conversation_id) -> list[Memory]`
  (latest summary + top facts by importance/recency; **no embedding call**).
- `app/services/prompt_builder.py` — add `format_retrieved_memories(memories: list) -> str` (the
  `### LONG-TERM MEMORY & CONTEXT` block, `""` if empty); refactor `inject_memories_into_prompt` to reuse it.

### 2.5 SDK facts — `google-genai` 2.2.0 (verified)
- Connect: `async with client.aio.live.connect(model=..., config=types.LiveConnectConfig(...)) as session:`
- Send mic: `await session.send_realtime_input(audio=types.Blob(data=<pcm16>, mime_type="audio/pcm;rate=16000"))`
- Receive: `async for resp in session.receive():`
  - `resp.data` → audio bytes (play). `resp.text` → text.
  - `resp.server_content.input_transcription` / `.output_transcription` → `Transcription(text, finished)`.
  - `resp.server_content.interrupted` (bool) · `.turn_complete` (bool).
  - `resp.tool_call.function_calls[].{id,name,args}` · `resp.go_away` · `resp.session_resumption_update`.
- Tool reply: `await session.send_tool_response(function_responses=[...])`.
- `LiveConnectConfig` fields used: `response_modalities=["AUDIO"]`, `system_instruction`, `tools`,
  `speech_config=SpeechConfig(voice_config=VoiceConfig(prebuilt_voice_config=PrebuiltVoiceConfig(voice_name=...)))`,
  `input_audio_transcription=AudioTranscriptionConfig()`, `output_audio_transcription=AudioTranscriptionConfig()`,
  `session_resumption=SessionResumptionConfig()`, `context_window_compression=ContextWindowCompressionConfig(sliding_window=SlidingWindow())`, `temperature`.
- Tools list pattern: `[types.Tool(function_declarations=[recall_memory_declaration()])]` (+ append
  `types.Tool(google_search=types.GoogleSearch())` when `LIVE_ENABLE_SEARCH`).
- Valid prebuilt voices: `Puck, Charon, Kore, Fenrir, Aoede, Leda, Orus, Zephyr`.

---

## 3. Work Packages — L1

### WP-1 · Backend service layer  ·  *no deps (owns §2.3, §2.4)*
**Objective:** Pure, testable building blocks for a Live session.
**Files:** `app/services/gemini_live.py` (new), `app/services/prompt_builder.py` (add formatter +
refactor), `app/services/memory.py` (add `get_preamble_memories`).
**Steps:** implement the six `gemini_live` functions per §2.4/§2.5; `resolve_voice` falls back to
`settings.LIVE_VOICE` when persona.voice ∉ valid set; `build_system_instruction` appends a directive to
call `recall_memory` for personal/past references and to keep replies short and spoken.
**Acceptance:** module-level funcs importable & unit-testable **without** network/DB; `build_live_config`
returns AUDIO modality + `recall_memory` tool present with `NON_BLOCKING`; voice fallback works.

### WP-2 · Backend Live WS endpoint  ·  *deps: WP-1 contracts*
**Objective:** Implement `/ws/live/{conversation_id}` per §2.2.
**Files:** `app/api/live_ws.py` (new), `app/main.py` (register router).
**Steps:** load conversation+persona (mirror `voice_ws.py`); build preamble via
`get_preamble_memories` + `format_retrieved_memories` → `build_system_instruction` → `build_live_config`;
open session; send `ready`. Run **two concurrent tasks**: *uplink* (`websocket.receive()` → binary →
`send_realtime_input`; JSON control) and *downlink* (`session.receive()` → forward `resp.data` as bytes,
emit transcripts/interrupted/turn_complete, spawn tool-call handler per §2.3). Accumulate input/output
transcripts; on `turn_complete` persist user+assistant `Message` rows (assistant gets `[interrupted]`
suffix if cut). On disconnect: `asyncio.create_task(SummarizerService().maybe_summarize(conversation_id, force=True))`.
**Acceptance:** connect with valid `GEMINI_API_KEY` + Live model → speak → hear reply; transcripts
persist; barge-in emits `interrupted`; session end writes a summary into `memories`.

### WP-3 · Frontend audio I/O + controller  ·  *deps: §2.2 only — parallel to WP-1/2*
**Objective:** Capture mic → PCM16@16k up; play PCM16@24k down gaplessly; flush on interrupt.
**Files:** `app/static/js/live.js` (new).
**Steps:** `getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true}})`; capture
via AudioContext + worklet/ScriptProcessor, **downsample to 16 kHz**, Float32→Int16, `ws.send(buffer)`.
Playback AudioContext @24k: Int16→Float32 → AudioBuffer, schedule with a `nextStartTime` cursor; track
scheduled sources so `interrupted` stops/clears them. `ws.binaryType="arraybuffer"`; route ArrayBuffer→play,
text→JSON handler. Reuse `window.chatConfig.conversationId`.
**Acceptance:** standalone, full-duplex audio loop works against WP-2; `interrupted` cuts playback < ~150 ms.

### WP-4 · Frontend Live UI  ·  *deps: WP-3*
**Objective:** "Go Live" control + live status/transcripts in the chat page.
**Files:** `app/templates/chat.html` (add `#live-btn`, `#live-status`; include `live.js`).
**Steps:** toggle starts/stops the live session; show connecting/live/ended; render finalized
transcripts as existing user/assistant bubbles; interim text in the status line. Don't break the V1
text path (separate WS/endpoint).
**Acceptance:** one-click start/stop; visible state; mic-denied degrades gracefully to text path.

### WP-5 · Tests + lint + smoke  ·  *deps: WP-1/2*
**Files:** `app/tests/test_live.py` (new).
**Steps:** unit `format_retrieved_memories` (summary+fact), `resolve_voice` fallback, `build_live_config`
(modality + tool + behavior), `recall_memory_declaration`. Keep network/DB-free. Run `ruff` + full
`pytest`. Add manual Chrome smoke notes (headphones for echo).
**Acceptance:** `ruff` clean; full suite green; smoke steps documented.

---

## 4. Dependency graph & parallelization
```
WP-1 ───▶ WP-2 ───▶ WP-5
WP-3 ───▶ WP-4
(WP-1 ∥ WP-3 from the start — they share only §2 contracts)
```
Hand WP-1 and WP-3 to two agents immediately. WP-2 starts once WP-1's signatures exist; WP-4 once WP-3
lands. WP-5 last. **All agents treat §2 as frozen** — propose contract changes back here, don't fork them.

---

## 5. Future Work Packages (lower resolution)
- **WP-MA · LangGraph multi-agent *text* group chat.** Stateful router coordinating Alistair + Elena;
  per-persona memory; turn arbitration. Independent track; de-risks orchestration. (Tomorrow's agenda.)
- **WP-L2 · Multi-agent *voice* panel (Live + LangGraph).** One Live session per persona (own voice +
  `recall_memory`), **router owns the floor** (route user audio to active speaker only), **transcript
  relay** between agents (never audio→audio). Sequential turn-taking, not simultaneous duplex. Depends
  on WP-1..4 (audio plumbing) + WP-MA (orchestration).

---

## 6. Risks & guardrails
- **Echo** (open mic re-triggers VAD) → headphones / `echoCancellation`. Biggest real-world snag.
- **Session caps / GoAway** → handle `session_resumption` handle; restart with preamble on expiry.
- **Context compression is lossy** → `recall_memory` + session-end summary offset it.
- **RAG is model-triggered** → nudge in system instruction + ship the start-of-session preamble.
- **Concurrency** (L2) → "free unlimited" ≠ unlimited concurrent sessions; fine for 2–3 personas.
- **Voice mapping** → `persona.voice` must map onto the prebuilt set (`resolve_voice` enforces).

## Links
- [[05 — Frontend/Voice Session Roadmap — V1 to V5]] · [[03 — Memory Layer/Memory Layer Overview]]
- [[02 — Backend/Backend Overview]] · [[06 — Logs/Current Context]]
- [VOICE_SESSION_PLAN.md](file:///c:/Users/loq/Desktop/learn/personas/VOICE_SESSION_PLAN.md) · [Gemini Live API — Tools](https://ai.google.dev/gemini-api/docs/live-api/tools)
