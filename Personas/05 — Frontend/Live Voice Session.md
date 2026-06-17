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

## Grounding (real code, Phases 0–3 shipped)
- Text chat already streams over **`/ws/chat/{id}`** ([voice_ws.py](file:///c:/Users/loq/Desktop/learn/personas/app/api/voice_ws.py)) with
  cancellable generation, **interrupt** (persists partial + `[interrupted]`), and per-turn RAG/memory.
- Client: [ws.js](file:///c:/Users/loq/Desktop/learn/personas/app/static/js/ws.js) + [chat.html](file:///c:/Users/loq/Desktop/learn/personas/app/templates/chat.html) — text form, interrupt button, Thinking/Streaming. **No mic/STT/TTS yet.**
- `Persona.voice` column exists (unused) → per-persona TTS voice is schema-ready.

## TL;DR
- **Half-duplex streaming** (keep the turn loop). Live feel = streaming STT + streaming tokens + sentence-chunked TTS + barge-in.
- **STT**: browser Web Speech (Chrome, MVP) → server Gemini STT (V4). **TTS**: browser `SpeechSynthesis` (MVP) → server streaming TTS (V3).
- **Barge-in**: server `interrupt` already works; Phase 4 just adds the client mic trigger.
- **Big point**: **V1–V2 need ZERO backend changes** — Web Speech fills `user_message`, `SpeechSynthesis` speaks the reply.

## Sub-phases
V1 mic + Web Speech + browser speech (push-to-talk) · V2 sentence-chunk + mic barge-in ·
V3 server streaming TTS · V4 server STT · V5 Gemini Live full-duplex. **MVP = V1–V2 (client-only).**

## Gotchas
- `SpeechRecognition` = Chrome/Edge only → target Chrome for MVP.
- Echo/false barge-in → headphones or **push-to-talk** default.

## Links
- [[03 — Memory Layer/Memory Layer Overview]] · [[02 — Backend/Backend Overview]] · [[06 — Logs/Current Context]] (Phase 4 = next focus)
