---
title: "Architecture Overview"
type: reference
status: active
updated: 2026-06-25
---

# 🏛️ Architecture Overview

The canonical spec is **`IMPLEMENTATION_PLAN.md`** at the repo root — link to it, don't fork it.
This note is the vault-side pointer + the short version.

## Locked decisions
- **Backend**: FastAPI (async), single app container also serving the UI.
- **Frontend**: Jinja2 templates + HTMX (server-rendered, light — no Node build). Voice clients (`live.js`/`panel.js`) are the real JS.
- **LLM (hybrid)**: **Gemini** for realtime (`gemini-2.5-flash` text chat, `LIVE_MODEL` for Live voice) +
  **local Ollama** for the memory layer (`nomic-embed-text` embeddings, `qwen3:8b` summaries — quota-free).
- **DB**: Postgres + pgvector (relational + vectors in one store).
- **Voice**: shipped — V1 browser STT/TTS (fallback), **L1 single-agent Gemini Live**, **L2 host-led multi-agent panel** (LangGraph-style floor routing).
- **Auth**: **none** — single-user personal project. Add a `users` table + JWT later only if it goes multi-user.

## Phase roadmap
- ✅ P0 Scaffold · P1 Persona CRUD · P2 Text loop · P3 **Memory layer** · P4 Voice (V1 + Live L1)
- 🔨 **P5 Enhancements** (current): ✅ export · ⏳ search · ⏳ analytics · ✅ **Voice L2 host-led panel** (functionally complete; persistence pending)

## Open links
- [[02 — Backend/Backend Overview]] · [[03 — Memory Layer/Memory Layer Overview]] · [[05 — Frontend/Frontend Overview]]
