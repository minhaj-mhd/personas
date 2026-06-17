---
title: "Frontend Overview"
type: reference
status: wip
updated: 2026-06-17
---

# 🖥️ Frontend Overview (server-rendered + HTMX)

Jinja2 templates served by FastAPI; HTMX for partial updates. No SPA, no Node build. See IMPLEMENTATION_PLAN §8.

## Pages (no auth — single user)
`/dashboard` (persona grid) · `/personas/{id}` (conversation list) ·
`/chat/{conversationId}` (voice chat) · `/personas/new` (prompt builder).

## The voice client (only real JS)
`static/js/voice.js` + `ws.js`. Mic → Web Speech `SpeechRecognition` → send `user_message` over WS →
stream `token` deltas into the assistant bubble → speak via `SpeechSynthesis`/`tts_ready`. Barge-in cancels + `interrupt`.
State machine: **idle → listening → thinking → speaking**.

## Discipline
Jinja autoescaping on all user content (persona names, messages). Never concatenate HTML.

## Notes log
- _(none yet)_
