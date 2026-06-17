---
title: "Backend Overview"
type: reference
status: wip
updated: 2026-06-17
---

# ⚙️ Backend Overview

FastAPI app under `app/`. JSON routers in `app/api/`, server-rendered pages in `app/web/views.py`,
business logic in `app/services/`. Schema changes go through **Alembic only**.

## Data model (see IMPLEMENTATION_PLAN §4)
`personas` · `conversations` · `messages` · `memories` (pgvector embedding(768)). **No `users`
table** — single-user. Memory is scoped by `persona_id`.

## Contracts
- **REST**: personas, conversations, messages, export. No `/auth` routes. (IMPLEMENTATION_PLAN §5)
- **WebSocket** `/ws/conversations/{id}`: `user_message`/`interrupt` in; `token`/`message_complete`/`tts_ready`/`memory_updated` out.

## Notes log
- _(none yet — record decisions, gotchas, and file links here as the backend is built)_
