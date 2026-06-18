---
title: "Voice Session Roadmap — Live-First (Replanned)"
type: reference
status: active
updated: 2026-06-18
---

# 🎙️ Voice Session Roadmap — Live-First (Replanned 2026-06-18)

> **🔄 REPLAN (2026-06-18).** The original V1→V5 ordering deferred the Gemini **Live API** to last and
> built V2–V4 to *simulate* a live feel — because Live was assumed **costly** and **incompatible with
> per-turn RAG**. Both blockers are gone, so we **pivot Live-first**. This doc supersedes §8's ordering
> in [VOICE_SESSION_PLAN.md](file:///c:/Users/loq/Desktop/learn/personas/VOICE_SESSION_PLAN.md).
> Pointer: [[05 — Frontend/Live Voice Session]].

## Why we replanned (what changed)

| Old assumption | Reality now | Consequence |
|---|---|---|
| Live API is costly | **Free unlimited access** to Gemini Live (`gemini-3.1-flash-live` / `2.5-flash-live`) | Cost no longer gates Live |
| Live can't re-run RAG mid-session | **Function calling** → a `recall_memory` **NON_BLOCKING** tool, schedulable `WHEN_IDLE`/`SILENT` (+ Google Search grounding) — [Live API tools](https://ai.google.dev/gemini-api/docs/live-api/tools) | Memory Layer transfers to Live |
| Need server TTS for natural voice (V3) | Live has **native audio out** + per-session voice | V3 redundant |
| Need server STT for portability (V4) | Live takes **raw `getUserMedia` PCM** in any browser | V4 redundant |
| Need manual sentence-buffer TTS + barge-in (V2) | Live has **native VAD + native interruption** | V2 redundant |

**Net:** V2/V3/V4 were scaffolding to fake a live feel. With free Live + tool-RAG they're dead work.
Keep V1 as a fallback; build the real thing (Live) next.

## Revised milestone map

| Step | Scope | Status |
|---|---|---|
| **V1** | Mic + Web Speech STT, `SpeechSynthesis` TTS, push-to-talk | ✅ Shipped (`f4ee245`) — **kept as fallback** |
| ~~V2~~ | ~~Sentence-buffer TTS + manual barge-in~~ | 🚫 **Deprecated** — Live native VAD/interruption |
| ~~V3~~ | ~~Server streaming TTS (`app/services/tts/`)~~ | 🚫 **Deprecated** — Live native audio out (`persona.voice` → Live voice ID) |
| ~~V4~~ | ~~Server STT (`GeminiSTT`), binary audio frames~~ | 🚫 **Deprecated** — Live native audio in (cross-browser via `getUserMedia`) |
| **L1** | **Gemini Live single-agent free-talk (full duplex)** | ▶ **NEW primary focus** |
| **L2** | **Multi-agent voice panel (Live + LangGraph)** | ⏭ Later — builds on L1 + the LangGraph track |

**Sequencing:** L1 first (validates Live end-to-end, lowest effort/highest payoff) → LangGraph
text group chat in parallel (tomorrow's agenda) → **L2 fuses them**.

---

## ✅ V1 — Hands-free single turn (SHIPPED, now the fallback)

**Goal:** Speak a turn and hear the reply on Chrome with **no backend change** — Web Speech STT fills
the existing `user_message{text}`, browser `SpeechSynthesis` speaks the streamed reply.

**Status:** Done (commit `f4ee245`; docs `c359a8f`). **Role after replan:** the zero-dependency
**fallback** when Live is unavailable / not desired.

**What was built**
- **Mic UI** — `#mic-btn` (Slate/Tailwind) next to `#send-btn` in
  [chat.html](file:///c:/Users/loq/Desktop/learn/personas/app/templates/chat.html); `required` removed
  from `#message-input`.
- **Push-to-Talk** in [ws.js](file:///c:/Users/loq/Desktop/learn/personas/app/static/js/ws.js):
  hold `#mic-btn` (mouse/touch) or hold **Spacebar** (when input unfocused) to record; release stops.
- **STT** — Web Speech `SpeechRecognition`, `interimResults=true`; interim streams to the box, final
  auto-fires `user_message`. No audio on the wire.
- **TTS** — `SpeechSynthesis` on `message_complete`; strips markdown + `[interrupted]`; prefers
  Google/system English voices.
- **Basic barge-in** — `speechSynthesis.cancel()` on new recording / `#interrupt-btn` / server `interrupted`.
- **Fix:** streaming bubble + text-node pointers now reset on socket `error`.

**Done when:** ✅ hands-free single turn on Chrome end-to-end.

---

## 🚫 Deprecated — V2 / V3 / V4 (superseded by Live)

Kept for the record; **do not build** unless we deliberately want a Live-free path.

- **V2 — sentence-buffer TTS + manual barge-in.** Superseded by Live's **native VAD + native
  interruption**. The whole client state machine + sentence splitter become unnecessary in Live mode.
- **V3 — server streaming TTS (`app/services/tts/`, `tts_chunk`, Web Audio queue).** Superseded by
  Live's **native audio output**. *Surviving concept:* `Persona.voice`
  ([persona.py:28](file:///c:/Users/loq/Desktop/learn/personas/app/models/persona.py)) now maps to a
  **Live session voice ID** at session config — no server-side TTS provider needed.
- **V4 — server STT (`GeminiSTT`, binary frames).** Superseded by Live's **native audio input**;
  `getUserMedia` works in Firefox/Safari, so Live *also* solves the portability goal V4 existed for.

---

## ▶ L1 — Gemini Live single-agent free-talk (NEW PRIMARY FOCUS)

**Goal:** A genuine **live session** with one persona — continuous open mic, native VAD, native
barge-in, natural voice — with memory preserved. This is the highest-payoff, lowest-effort use of the
free Live access, and it de-risks the audio plumbing L2 reuses.

**Why easiest:** no orchestrator, no transcript relay, no floor control. The Live API natively handles
turn-taking and interruption for one model vs. one user.

**What to build (Track B bridge behind `/ws/chat` or a new `/ws/live/{conversation_id}`)**
1. **Session open** — set `system_instruction` = assembled persona prompt **+ a memory preamble**
   (latest summary + top facts from `MemoryService`); set the **session voice** from `persona.voice`.
2. **Audio I/O** — client captures mic via `getUserMedia({ audio: { echoCancellation: true }})` →
   stream PCM in; play audio out via a Web Audio queue. Reuse capture/playback for L2.
3. **Mid-session RAG (the corrected design)** — register a **`recall_memory(query)`** function tool
   with `behavior: "NON_BLOCKING"` and `scheduling: "WHEN_IDLE"` (or `"SILENT"`) so retrieval doesn't
   stall/cut speech. On a tool call: run `MemoryService.retrieve_context()` → reply with
   `session.send_tool_response([FunctionResponse(...)])`. **Live has no auto tool handling — we write
   this glue.** Optionally enable **Google Search** grounding alongside it.
4. **Memory write-back** — capture the transcript (enable input/output transcription) and run
   `SummarizerService` at **session end** to fold facts back into `memories` for cross-session recall.
5. **Reconnect** — handle session **resumption tokens** + `GoAway`; existing ws.js auto-reconnect does
   *not* restore a Live session by itself.

**Done when:** open-mic free-talk with one persona — talk over it and it stops; it recalls memory
mid-session via the tool; the session summarizes back into the Memory Layer on close.

**Risks / notes (none cost-related):**
- **Echo** — open mic + speakers can re-trigger the agent's VAD. Mitigate with headphones or browser
  AEC (`echoCancellation: true`). The single biggest real-world snag.
- **Session duration cap** — long sessions need resumption to continue.
- **Context compression is lossy** — `recall_memory` + session-end summary offset this.
- **Voice mapping** — Live exposes a fixed prebuilt voice set; `persona.voice` must map onto it.
- **RAG is model-triggered, not deterministic** — nudge via system instruction ("check memory before
  answering personal questions") + the start-of-session preamble for baseline grounding.

---

## ⏭ L2 — Multi-agent voice panel (Live + LangGraph)

**Goal:** A moderated voice "panel" — user + 2–3 personas (e.g. Alistair + Elena), one speaking at a
time, distinct voices, each with its own memory — coordinated by a LangGraph routing graph.

**Status:** Later. Depends on **L1** (audio plumbing) and the **LangGraph text group-chat** track
(orchestration). This is V5 + the multi-agent track fused.

**Architecture**
- **One Live session per persona** — own `system_instruction`, own **voice**, own `recall_memory`
  scoped to that persona's memories. Keep sessions warm to avoid connect latency.
- **LangGraph router owns the floor** — the Live API has **no cross-session awareness**; each session's
  native VAD would otherwise answer simultaneously. The router decides who holds the mic, routes the
  user's audio only to the active speaker, and gates the others.
- **Transcript relay, not audio relay** — feed a finished speaker's **output transcript** (text) into
  the next agent's session via `send_client_content`. Piping audio agent→agent causes VAD feedback loops.
- **Barge-in** — user interrupting tells the router to stop the current speaker and re-route.

**Done when:** user + 2–3 personas hold a coherent, turn-managed voice conversation with distinct
voices and per-persona memory.

**Risks / notes:**
- ⚠️ **Not** a free-for-all of simultaneous overlapping duplex — audio feedback + lack of cross-session
  arbitration make that infeasible. It's **orchestrated, sequential** turn-taking.
- **Concurrency limits** — "free unlimited" usage ≠ unlimited *concurrent* sessions; fine for one user
  with 2–3 agents, not for dozens.
- **System instruction is fixed at setup** — hence one session per persona (parallel, warm), not one
  shared session morphing personas.

---

## Cross-cutting: latency, errors, testing

- **Latency** — Live streams audio natively (no per-turn STT/TTS hop); `recall_memory` NON_BLOCKING so
  retrieval doesn't stall speech; `MemoryService` already capped by `settings.SHORT_TERM_MESSAGES` + top-k.
- **Errors / resilience** — mic-denied → fall back to V1 text/Web Speech (still works); Live session
  drop → resumption token, else restart with preamble; conversation is DB-backed so nothing is lost.
- **Tests** ([app/tests/](file:///c:/Users/loq/Desktop/learn/personas/app/tests/)) — unit the
  `recall_memory` tool-response glue (tool call → `retrieve_context` → `send_tool_response`); assert
  session-end summary writes to `memories`; L2: unit the router's floor-control transitions; manual
  smoke for echo/barge-in.

## Links
- [[05 — Frontend/Live Voice Session]] · [[05 — Frontend/Frontend Overview]]
- [[02 — Backend/Backend Overview]] · [[03 — Memory Layer/Memory Layer Overview]]
- [[06 — Logs/Current Context]]
- [Gemini Live API — Tools](https://ai.google.dev/gemini-api/docs/live-api/tools)
