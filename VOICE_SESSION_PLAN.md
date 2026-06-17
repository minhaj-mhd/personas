# Live Voice Session — Phase 4 Implementation Plan

Focused, code-grounded plan for adding **live voice** to the existing text chat. This is Phase 4
("Voice — mic STT + audio TTS loop") — the current active focus per the vault's Current Context.

> Grounded in the **real codebase** (Phases 0–3 shipped), not the idealized plan. It *extends*
> what exists; it does not rebuild it. Read [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md)
> §6 for the memory flow.

---

## 0. What already exists (do NOT rebuild)

The text conversation loop is done and the voice feature layers on top of it.

| Concern | Already implemented | Where |
|---|---|---|
| WebSocket chat | `/ws/chat/{conversation_id}` | [app/api/voice_ws.py](app/api/voice_ws.py) |
| Client WS controller + UI states | connect/reconnect, Thinking/Streaming, interrupt | [app/static/js/ws.js](app/static/js/ws.js), [app/templates/chat.html](app/templates/chat.html) |
| Streamed tokens | `generate_chat_stream(system_instruction, chat_history, user_message, temperature)` | [app/services/gemini.py](app/services/gemini.py) |
| Cancellable generation + **interrupt** | `asyncio.Task` cancel; persists partial reply + `[interrupted]` | voice_ws.py:139-159, 167-178 |
| Memory / RAG injection per turn | `MemoryService.retrieve_context(...)` → `inject_memories_into_prompt(...)` | app/services/memory.py, prompt_builder.py |
| Rolling summarization | `SummarizerService.maybe_summarize(conversation_id)` | app/services/summarizer.py |
| Persona `voice` field | `Persona.voice` (nullable String) — schema-ready, currently unused | app/models/persona.py:28 |

**Current protocol (real):**
```
client → server:  {type:"user_message", text}   {type:"interrupt"}
server → client:  {type:"token", delta}   {type:"message_complete", message_id, text}
                  {type:"interrupted", text}   {type:"error", detail}   {type:"info", detail}
```

**Key consequence:** the **MVP voice layer needs ZERO backend changes.** Web Speech STT fills the
same `user_message`, and browser `SpeechSynthesis` speaks the streamed `token`/`message_complete`
text. Backend work only starts at server-side TTS (V3) and server STT (V4).

---

## 1. Design choice: half-duplex streaming (keep the turn loop)

The system is already a turn-based streaming loop, which is exactly right for per-turn memory
injection. "Live feel" comes from streaming, not full duplex:
1. **Streaming STT** — interim transcript while you speak (local, no roundtrip).
2. **Streaming tokens** — already shipped; reply renders as it generates.
3. **Sentence-chunked TTS** — speak sentence 1 while sentence 2 is still generating.
4. **Barge-in** — speak over the assistant → reuse the existing `interrupt`.

Full-duplex via **Gemini Live API** is a later track (§9), slotting behind the same client modules.

---

## 2. Browser reality (decides the STT path)

| Capability | Chrome/Edge | Firefox | Safari |
|---|---|---|---|
| `SpeechRecognition` (Web Speech STT) | ✅ (audio → Google) | ❌ | ⚠️ flaky |
| `SpeechSynthesis` (TTS) | ✅ | ✅ | ✅ |
| `getUserMedia` + AudioWorklet/`MediaRecorder` | ✅ | ✅ | ✅ |

Single-user project → **target Chrome, use Web Speech for MVP.** Add the server STT path for
portability/quality later.

---

## 3. STT paths

- **Path 1 — Browser Web Speech (MVP, Chrome).** `SpeechRecognition`, `interimResults=true`. Interim
  text updates the UI; final transcript is sent as the existing `user_message{text}`. No audio on the
  wire, no backend change.
- **Path 2 — Server Gemini STT (V4 upgrade, portable).** Capture mic (AudioWorklet → 16 kHz PCM, or
  `MediaRecorder` opus), stream binary `audio_chunk` frames with client VAD marking utterance end;
  server transcribes via a new `GeminiSTT`. Emits the same `user_message` internally.

Wrap both behind a small client `SttSource` interface (`start/onInterim/onFinal/stop`).

---

## 4. TTS + playback

- **Option A — Browser `SpeechSynthesis` (MVP, zero-cost, no backend).** Speak each sentence as
  `token` deltas arrive (buffer to sentence boundaries) or on `message_complete`. Robotic but instant.
- **Option B — Server streaming TTS (V3, natural voice).** Extend voice_ws.py: as the LLM stream
  yields complete sentences, synthesize via a new `TTSProvider` (`app/services/tts/`) keyed on
  `persona.voice`, and emit ordered `tts_chunk{seq, ...}`. Client plays gaplessly via a Web Audio
  `AudioContext` queue ([app/static/js/audio-player.js], new). Transport: base64-in-JSON for MVP,
  binary frames if bandwidth matters.

Both must support **instant stop** for barge-in (`speechSynthesis.cancel()` / flush the audio queue).

---

## 5. Barge-in (mostly already there)

Server-side interrupt is **done** (cancel task + persist partial). Phase 4 adds the *client trigger*:
1. While speaking, keep STT armed. Web Speech `onspeechstart` (Path 1) or VAD (Path 2) = user talking over.
2. Client immediately: stop playback (`speechSynthesis.cancel()` / flush queue) → send the existing
   `{type:"interrupt"}` → start capturing the new utterance.
3. Server already cancels `active_generation_task`, persists `… [interrupted]`, emits `interrupted`.

Echo guard: prefer headphones, or default to **push-to-talk** (hold key/button to speak) for MVP —
it sidesteps the assistant's audio re-triggering the mic.

---

## 6. Client state machine (extends ws.js)

ws.js today tracks connection state + an action status ("Thinking"/"Streaming"). Add mic states:

```
   IDLE ──press talk──▶ LISTENING ──final transcript (send user_message)──▶ THINKING
     ▲                      ▲                                                  │ first token
     │  end session         │◀──────────── interrupt / new utterance ─────────┤
     │                      │                                                  ▼
     └───── queue drained ◀── SPEAKING ◀────── token + (TTS) ◀─────────────────┘
```
- **LISTENING**: mic on, show interim transcript. Final → reuse the existing send path (`user_message`).
- **THINKING / SPEAKING** wrap the existing `token` → `message_complete` handling; SPEAKING also drives TTS.
- Reuse `#interrupt-btn`, `#action-status`, `#status-text`; add a **mic button** to chat.html next to `#send-btn`.

Keep it in ws.js or a cooperating `voice.js` that shares `window.chatConfig` and the WS handle.

---

## 7. Protocol additions (only for V3/V4)

Additive — existing frames unchanged.
```
client → server (Path 2):  <binary audio frame>          {type:"audio_end"}
server → client (Opt B):   {type:"tts_meta", seq, mime, sentence}  then <binary frame>
                           (or {type:"tts_chunk", seq, b64})
server → client (Path 2):  {type:"stt_partial", text}
```
TTS chunks carry a monotonic `seq`; client plays in order and drops any chunk predating the last `interrupt`.

---

## 8. Build sub-phases (Phase 4)

| Step | Scope | Backend change? | Done when |
|---|---|---|---|
| **V1** | Mic button + Web Speech STT → `user_message`; `SpeechSynthesis` speaks the reply; push-to-talk | **None** | Hands-free single turn works on Chrome end to end. |
| **V2** | Sentence-buffer the token stream → speak per sentence; **mic barge-in** → existing `interrupt` | **None** | Can talk over the assistant; it stops + listens. |
| **V3** | Server streaming TTS (`app/services/tts/`, `TTSProvider`, `persona.voice`); `tts_chunk` frames; Web Audio gapless queue | voice_ws.py + new service + new js | Natural voice, gapless, instant stop on interrupt. |
| **V4** | Server STT path (`GeminiSTT`), binary `audio_chunk` frames, fallback when Web Speech absent | voice_ws.py + new service + js | Works on a non-Chrome browser. |
| **V5** | Gemini Live API full-duplex bridge (§9) | new bridge | Native overlapping turn-taking + interruption. |

**MVP voice = V1–V2** (client-only, no backend change).

---

## 9. Track B — Gemini Live API (V5, later)

- Open a Live session; `system_instruction` = the assembled persona prompt **+ a memory preamble**
  (latest summary + top retrieved facts from `MemoryService`) injected at session start.
- Stream mic PCM in; receive audio out; native VAD + interruption (drops most §5/§6 client code).
- **Memory caveat:** Live doesn't re-run RAG mid-session. Mitigate with (a) the start-of-session
  preamble, (b) a `recall_memory(query)` tool the model can call, (c) summarize the transcript back
  into `memories` on session end (reuse `SummarizerService`).
- Migration is cheap: reuse client audio capture/playback; swap the server pipeline behind `/ws/chat`.

---

## 10. Latency, errors, testing

**Latency** (target first audio ≤ ~1.2 s after speech ends): Web Speech finalizes locally (no hop);
`recent_buffer`/RAG already capped by `settings.SHORT_TERM_MESSAGES` + top-k; `gemini-2.5-flash`;
sentence-chunk so audio starts before generation finishes; persistent WS (already reconnects).

**Errors:** feature-detect `SpeechRecognition` (fallback: server STT or text box, which already
works); mic-denied → clear prompt, text still works; TTS failure → degrade to text for that turn;
LLM error already surfaces as `error`. WS drop already auto-reconnects (ws.js:49-53); conversation
is DB-backed so nothing is lost.

**Tests** (extend [app/tests/](app/tests/)): unit the sentence-splitter and the state-machine
transitions; an integration test asserting mic barge-in path still persists the partial with
`[interrupted]` (the existing behavior in test_chat.py style); manual Chrome smoke for V1/V2.

---

## 11. File touchpoints (real paths)

```
app/templates/chat.html        # add mic button + push-to-talk control
app/static/js/ws.js            # extend: STT capture, SpeechSynthesis, LISTENING/SPEAKING states, mic barge-in
app/static/js/audio-player.js  # NEW (V3): Web Audio gapless queue for server TTS
app/api/voice_ws.py            # extend (V3/V4): emit tts_chunk; accept audio frames + audio_end
app/services/tts/              # NEW (V3): TTSProvider + Gemini/ElevenLabs impls, keyed on persona.voice
app/services/stt/              # NEW (V4): STTProvider + GeminiSTT
app/services/gemini.py         # reuse existing generate_chat_stream
```

---
**Bottom line:** V1–V2 are a **pure client-side add-on** to the working text chat — mic (Web Speech)
in, browser speech out, barge-in via the `interrupt` you already have. Then V3 server TTS for a
natural voice, V4 server STT for portability, V5 Gemini Live for true full-duplex.
