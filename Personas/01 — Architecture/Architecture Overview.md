---
title: "Architecture Overview"
type: reference
status: active
updated: 2026-06-17
---

# 🏛️ Architecture Overview

The canonical spec is **`IMPLEMENTATION_PLAN.md`** at the repo root — link to it, don't fork it.
This note is the vault-side pointer + the short version.

## Locked decisions
- **Backend**: FastAPI (async), single app container also serving the UI.
- **Frontend**: Jinja2 templates + HTMX (server-rendered, light — no Node build). Voice client is the only real JS.
- **LLM**: Gemini, single-provider — `gemini-2.5-flash` (chat), `gemini-2.5-pro` (summaries), `text-embedding-004` (embeddings).
- **DB**: Postgres + pgvector (relational + vectors in one store).
- **Voice**: turn-based pipeline first (browser STT/TTS), Gemini Live API later.
- **Auth**: **none** — single-user personal project. Add a `users` table + JWT later only if it goes multi-user.

## Phase roadmap (MVP = 0–4)
- P0 Scaffold · P1 Persona CRUD + dashboard · P2 Text conversation loop · P3 **Memory layer (the differentiator)** · P4 Voice · P5 Enhancements.

## Open links
- [[02 — Backend/Backend Overview]] · [[03 — Memory Layer/Memory Layer Overview]] · [[05 — Frontend/Frontend Overview]]
