---
title: "Architecture Overview"
type: reference
status: active
updated: 2026-06-25
---

# 🏛️ Architecture Overview

> 📍 **For the full, current, code-verified end-to-end map** (every model, table, and flow),
> see **[[End-to-End System Architecture]]**. This note is the short version.

The original spec is **`IMPLEMENTATION_PLAN.md`** at the repo root — the build has since diverged
from it (see the end-to-end doc for what actually shipped).

## Locked decisions
- **Backend**: FastAPI (async), single app container also serving the UI.
- **Frontend**: Jinja2 templates + HTMX (server-rendered, light — no Node build). Voice clients (`live.js`/`panel.js`) are the real JS.
- **LLM (hybrid)**: **Gemini** for realtime (`gemini-2.5-flash` text chat, `LIVE_MODEL` for Live voice) +
  **local Ollama** for the memory layer (`nomic-embed-text` embeddings, `qwen3:8b` summaries — quota-free).
- **DB**: Postgres + pgvector (relational + vectors in one store).
- **Voice**: shipped — V1 browser STT/TTS (fallback), **L1 single-agent Gemini Live**, **L2 host-led multi-agent panel**. Floor routing is a **deterministic first-name router + a `route_to_agent` LLM tool** — *not* LangGraph (no graph runtime is used anywhere; see [[End-to-End System Architecture#6. Orchestration — there is no LangGraph]]).
- **Live robustness**: session **resumption/reconnect** on transient upstream drops (1006/1008/GoAway).
- **Multimodal**: uploaded **images** prime a session as visual context; **screen-share** streams frames; optional **MCP tool bridge** (e.g. Google Sheets) exposes external tools to the Live agent.
- **Auth**: **none** — single-user personal project. Add a `users` table + JWT later only if it goes multi-user.

## Phase roadmap
- ✅ P0 Scaffold · P1 Persona CRUD · P2 Text loop · P3 **Memory layer** · P4 Voice (V1 + Live L1)
- ✅ **P5 Enhancements**: export · search · analytics · **Voice L2 host-led panel** with **persistence** (saved panels + transcript)
- ➕ **Post-P5 (in code, not in original plan)**: Live/panel session resumption · image/asset visual context + screen-share · MCP tool bridge

## Open links
- [[02 — Backend/Backend Overview]] · [[03 — Memory Layer/Memory Layer Overview]] · [[05 — Frontend/Frontend Overview]]
