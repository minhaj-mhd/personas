---
title: "Welcome — Persona Platform Dev Memory"
type: index
status: active
updated: 2026-06-17
---

# 🧭 Welcome — Development Memory Vault

This Obsidian vault is the **coding agent's cross-session memory** for the
**AI Multi-Persona Voice Agent Platform**. Read this map first, then
[[06 — Logs/Current Context|Current Context]] for the active focus.

> The operating rules live in **`AGENTS.md`** at the repo root (see [[AI Operating Protocol]] for the pointer).
> The canonical architecture spec is **`IMPLEMENTATION_PLAN.md`** at the repo root.

> ⚠️ Don't confuse this **dev memory vault** (markdown, for agents) with the **application's
> memory layer** (Postgres/pgvector, the product feature). See [[03 — Memory Layer/Memory Layer Overview]].

---

## 🗺️ Map of Content

| Section | Purpose | Entry note |
|---|---|---|
| **01 — Architecture** | System design, stack decisions, phases | [[01 — Architecture/Architecture Overview]] |
| **02 — Backend** | FastAPI app, data model, REST + WebSocket (no auth) | [[02 — Backend/Backend Overview]] |
| **03 — Memory Layer** | Short-term window, summarizer, RAG retrieval, prompt assembly | [[03 — Memory Layer/Memory Layer Overview]] |
| **04 — Personas** | System-prompt template, built-in + custom personas | [[04 — Personas/Persona Catalog]] |
| **05 — Frontend** | Jinja2 templates, HTMX, the voice client | [[05 — Frontend/Frontend Overview]] |
| **06 — Logs** | Active focus, per-thread conversations, daily logs | [[06 — Logs/Current Context]] |
| **09 — Archive** | Superseded designs and retired decisions | [[09 — Archive/Archive Index]] |

---

## 🚦 Current Status
- **Phase**: Phase 0 — Scaffold (not started). Planning complete.
- **Stack locked**: FastAPI + Jinja2 + HTMX · Gemini (single-provider) · Postgres + pgvector · turn-based voice first · no auth (single-user).
- **Next**: see [[06 — Logs/Current Context|Current Context]].
