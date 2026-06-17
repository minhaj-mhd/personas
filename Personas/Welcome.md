---
title: "Welcome — Persona Platform Dev Memory"
type: index
status: active
updated: 2026-06-17
---

# 🧭 Welcome — Development Memory Vault

This Obsidian vault is the **coding agent's cross-session memory** for the **AI Multi-Persona Voice Agent Platform**. Read this map first, then [[06 — Logs/Current Context|Current Context]] for the active focus.

> The operating rules live in **`AGENTS.md`** at the repo root (see [[AI Operating Protocol]] for the pointer).
> The canonical architecture spec is **`IMPLEMENTATION_PLAN.md`** at the repo root.

> ⚠️ Don't confuse this **dev memory vault** (markdown, for agents) with the **application's memory layer** (Postgres/pgvector, the product feature). See [[03 — Memory Layer/Memory Layer Overview]].

---

## 🗺️ Map of Content

| Section | Purpose | Primary Docs & Entries |
|---|---|---|
| **01 — Architecture** | System design, Stack decisions, Request lifecycle | [[01 — Architecture/Architecture Overview]] · [[01 — Architecture/System Walkthrough\|System Walkthrough]] · [[01 — Architecture/Database Schema and Migrations\|Database Schema & Migrations]] |
| **02 — Backend** | FastAPI app, Database schemas, REST + WebSocket | [[02 — Backend/Backend Overview]] |
| **03 — Memory Layer** | Short-term window, Rolling summaries, Semantic RAG | [[03 — Memory Layer/Memory Layer Overview]] · [[03 — Memory Layer/How RAG and Persistent Memory Work\|How RAG & Memory Work]] |
| **04 — Personas** | System-prompt template, Built-in + Custom catalogs | [[04 — Personas/Persona Catalog]] |
| **05 — Frontend** | Jinja2 templates, HTMX fragments, ws.js client | [[05 — Frontend/Frontend Overview]] |
| **06 — Logs** | Active focus, Concluded conversation threads, Daily logs | [[06 — Logs/Current Context]] |
| **09 — Archive** | Superseded designs and retired decisions | [[09 — Archive/Archive Index]] |

---

## 🚦 Current Status
- **Phase**: Phase 3 — Memory Layer & RAG (Completed & Fully Documented).
- **Core Proof**: Automated cross-session resume-recall integration tests are fully passing.
- **Next**: Phase 4 — Voice integration (Browser-based STT & TTS).
