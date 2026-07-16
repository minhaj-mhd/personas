---
title: "Current Context"
type: log
status: active
updated: 2026-07-13
---

# 📌 Current Context — Global Active Focus

The single source of "where are we right now." Keep **Current Focus** lean (≤ ~10 live items);
move finished items into the day's [[06 — Logs/Daily Logs/|Daily Log]].

## 🎯 Current Focus
- **🗺️ Full architecture re-synced to code (2026-07-13)**: authored **[[01 — Architecture/End-to-End System Architecture]]** — the current, code-verified end-to-end map (models/providers, all 7 tables, every flow, orchestration, frontend). Corrects drift: memory runs on Ollama; **there is NO LangGraph** (floor routing = deterministic router + `route_to_agent` tool); and several subsystems shipped since the last sync — **Live/panel session resumption**, **panel persistence** (saved panels + transcript), **image/asset visual context + screen-share**, and an optional **MCP tool bridge** (Google Sheets). Welcome/Architecture/Backend overviews updated to point at it.
- Implemented Phase 4 V1 Voice Loop (push-to-talk, spacebar, browser STT, cleaned SpeechSynthesis TTS) — now kept as the no-dependency **fallback**.
- **🔄 Voice REPLAN (2026-06-18): pivot Live-first.** Free unlimited Gemini Live access + mid-session RAG via a `recall_memory` NON_BLOCKING function tool make V2/V3/V4 redundant (Live has native audio in/out, VAD, and interruption). Full rationale + new plan: [[05 — Frontend/Voice Session Roadmap — V1 to V5]].
- **Completed today**: Voice L1 — Gemini Live single-agent free-talk (full duplex) implemented via subagent execution of [[01 — Architecture/Master Plan — Live Voice (Subagent-Ready)]].
- **Live L1 debugging (2026-06-19)**: root-caused & fixed the "agent talks once then disconnects" bug — `session.receive()` is a per-turn generator, now wrapped in `while True` in [[Master Plan — Live Voice (Subagent-Ready)]]'s WS endpoint. Also fixed summarizer `429` (free-tier `gemini-2.5-pro` quota = 0 → switched to `gemini-2.5-flash`). Awaiting user multi-turn retest on :8002.
- **🦙 Local memory models (Ollama) — ✅ DONE (2026-06-25)**: embeddings → `nomic-embed-text` and summarization → `qwen3:8b` are live in code ([embeddings.py](file:///c:/Users/loq/Desktop/learn/personas/app/services/embeddings.py), [summarizer.py](file:///c:/Users/loq/Desktop/learn/personas/app/services/summarizer.py)); existing vectors re-embedded via [scripts/reembed_memories.py](file:///c:/Users/loq/Desktop/learn/personas/scripts/reembed_memories.py). Transcription/conversation stays on Gemini Live ([[Memory in a Live Voice Session]]).
- **🧠 Memory layer docs synced to code (2026-06-25)**: added the full plan→implementation status matrix to [[03 — Memory Layer/Memory Layer Overview]]; fixed cosine operator docs (`<=>`); marked the Ollama migration complete. The memory layer is now **fully implemented** (RAG retrieval, document KB, rolling summaries, Live preamble + `recall_memory`, disconnect write-back).
- **🎛️ Voice L2 — Host-Led Panel ✅ WORKING (user-tested, 2026-06-25)**: `/panel` — pick roster → voice host
  greets → call an agent by name → `route_to_agent` tool switches the floor 1:1 with full context (shared transcript +
  per-persona memory) → re-routes on the next named agent. P-1..P-4 built + 17 tests; design in
  [[01 — Architecture/Master Plan — Voice Panel (Host-Led, Subagent-Ready)]]. `langgraph` installed. Polish shipped:
  English STT pin (`LIVE_LANGUAGE`), agents follow current topic. **Remaining: P-5 persistence + integration tests.**
- **🗂️ Phase 5 enhancements**: ✅ Markdown export (`/api/conversations/{id}/export`); ✅ conversation search (`/api/conversations/search`); ✅ analytics (`/api/analytics` — totals + per-persona stats + spoken-time estimate).
- _(Stale: the L1 "retest on :8002" note above is resolved — Live works.)_

## ✅ Next Steps
- [x] Decide whether to `git init` the project (ask user first).
- [x] Phase 0 — Scaffold: Docker Compose (app + Postgres/pgvector), FastAPI `/health`, Jinja `base.html`, Alembic baseline, `.gitignore`.
- [x] Phase 1 — Persona CRUD + dashboard (no auth — single-user project).
- [x] Phase 2 — Text conversation loop.
- [x] Phase 3 — Memory layer (the differentiator; resume-recall test = done).
- [x] Phase 4 — Voice V1 (Push-to-talk browser STT and SpeechSynthesis TTS) — kept as no-dependency fallback.
- [~] ~~Voice V2–V4 (sentence-buffer TTS, server TTS, server STT)~~ — DEPRECATED, superseded by Gemini Live native audio (see replan).
- [x] **Voice L1 — Gemini Live single-agent free-talk (full duplex)**: native VAD/barge-in, `recall_memory` NON_BLOCKING tool, session-end summary write-back. (Completed via subagents WP-1..5).
- [x] **Local memory models (Ollama)**: embeddings→`nomic-embed-text`, summary→`qwen3:8b`, one-time re-embed — DONE (2026-06-25). Plan: [[Master Plan — Local Memory Models (Ollama) (Subagent-Ready)]].
- [x] **Voice L2 — Host-led multi-agent voice panel** (`/panel`): host greets, `route_to_agent` floor switching, 1:1 audio, transcript relay — WORKING (user-tested).
- [x] **Phase 5 — Markdown export** (`/api/conversations/{id}/export?format=md`).
- [x] Phase 5 — Conversation search (`/api/conversations/search`, snippet + match count) — DONE.
- [x] Phase 5 — Analytics (`/api/analytics`, totals + per-persona + spoken-time estimate) — DONE.
- [x] Voice L2 — **P-5 persistence**: saved `panels` + `panel_messages` transcript (models/panel.py, panel/persistence.py, /api/panels, panels_hub) — DONE.
- [x] **Live/panel session resumption** on transient upstream drops (1006/1008/GoAway) — DONE (`recoverable_disconnect`, reconnect loops, `test_live_reconnect`/`test_panel_reconnect`).
- [x] **Image/asset visual context**: per-persona/panel image uploads primed into Live sessions + screen-share/capture (models/asset.py, services/assets.py, live.js) — DONE.
- [x] **MCP tool bridge** (optional, off by default): expose an MCP server's tools (e.g. Google Sheets) to the Live agent (services/mcp/client.py, `MCP_SHEETS_*`) — DONE.

## 🧵 Active Conversations
- [[06 — Logs/Conversations/Conv-2026-06-25-Phase5-Build-Loop|Phase 5 Build Loop]] (export, Voice L2 panel, search)


