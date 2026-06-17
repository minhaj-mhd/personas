---
title: "Live Voice Session (Phase 4)"
type: reference
status: wip
updated: 2026-06-17
---

# 🎙️ Live Voice Session — Phase 4 (pointer)

Full spec: **`VOICE_SESSION_PLAN.md`** at repo root →
[VOICE_SESSION_PLAN.md](file:///c:/Users/loq/Desktop/learn/personas/VOICE_SESSION_PLAN.md).
Searchable summary only — don't duplicate the spec body.

## Grounding (Real Code, Phase 4 V1 Shipped)
- **FastAPI Backend WebSocket Endpoint**: `/ws/chat/{id}` ([voice_ws.py](file:///c:/Users/loq/Desktop/learn/personas/app/api/voice_ws.py)) manages turn-based streaming, history retrieval, RAG injection, rolling summaries, and task cancellation (`interrupt` events that save partial replies with `[interrupted]`).
- **Voice V1 Client Integration**:
  - **Mic UI**: Added `#mic-btn` with Slate/Tailwind styling next to `#send-btn` in [chat.html](file:///c:/Users/loq/Desktop/learn/personas/app/templates/chat.html). Removed `required` input validation.
  - **Push-to-Talk (PTT)**: Built triggers in [ws.js](file:///c:/Users/loq/Desktop/learn/personas/app/static/js/ws.js) supporting:
    - **Mouse/Touch**: Holding down `#mic-btn` (starts `SpeechRecognition`), releasing or leaving stops it.
    - **Keyboard**: Holding down `Spacebar` (when `#message-input` is unfocused) starts it, releasing stops it.
  - **STT**: Uses browser-native Web Speech `SpeechRecognition`. Streams interim transcripts into the text box in real-time. Automatically fires a WebSocket `user_message` once speech finalizes.
  - **TTS**: Employs browser-native `SpeechSynthesis` upon `message_complete`. Strips markdown format symbols (`*`, `_`, `` ` ``) and `[interrupted]` suffixes before speaking. Searches for high-quality system/Google English voices.
  - **Barge-in / Speech Interruption**: Instantly calls `window.speechSynthesis.cancel()` if a new recording starts, if the user clicks `#interrupt-btn`, or if the server emits an `interrupted` event.

## Links
- [[03 — Memory Layer/Memory Layer Overview]] · [[02 — Backend/Backend Overview]] · [[06 — Logs/Current Context]]
