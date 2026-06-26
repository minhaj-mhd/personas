---
title: "Master Plan — Voice Panel (Host-Led Handoff)"
type: spec
status: active
updated: 2026-06-25
---

> ✅ **Status: functionally complete & user-tested working (2026-06-25).** P-1..P-4 built; routing via the
> `route_to_agent` tool (robust to mangled STT); polish shipped (English STT pin, agents follow current topic).
> Remaining: **P-5** (persistence + integration tests). Build log: [[06 — Logs/Conversations/Conv-2026-06-25-Phase5-Build-Loop|Phase 5 Build Loop]].

# 🎛️ Master Plan — Voice Panel (Host-Led Handoff)  ·  Voice L2

The multi-agent voice panel, designed **host-led** per the user's model (2026-06-25). Supersedes
the generic L2 sketch in [[05 — Frontend/Voice Session Roadmap — V1 to V5]] (§L2) with a concrete,
buildable design. Builds on **L1** (single-agent Live, shipped) and adds a **LangGraph** floor router.

## 🎯 Goal
User picks a roster (Host + 2–3 specialist personas). A **voice host** greets the user, then the
user verbally calls on an agent by name; the host routes the mic **1:1** to that agent (primed with
full context), monitors the conversation via transcript, and re-routes when the user calls another
agent — carrying the history forward.

## 🔄 The host-led flow
1. **Roster select** (UI) → open host Live session; agents opened lazily/kept warm.
2. **Host greets** (host Live session speaks).
3. **User addresses an agent** ("talk to Alistair") → router detects the name → mic re-routes 1:1 to
   that agent; agent session primed with: (a) its own memory preamble, (b) the shared panel transcript.
4. **While 1:1**, every user + agent line is transcribed into the **shared panel transcript** — this
   is how the host "hears" the conversation (text, not parallel audio).
5. **User calls another agent** → router detects new name in the transcript → host narrates handoff →
   mic re-routes to agent 2, primed with the full transcript → agent 2 answers in context.

## 🧠 The key refinement (why it works)
**Only ONE agent receives the mic at a time (1:1).** The host "hears" via the **live transcript**,
not by co-listening with a parallel always-on audio session. Two sessions both hearing the mic →
both VAD-trigger → both answer → echo/feedback. So: one active audio session + a text-level router/host.

## 🏗️ Architecture
```
            ┌──────────── PanelSession (server, per WS) ───────────┐
            │  roster[Host, Alistair, Elena]   active_id           │
            │  shared transcript[]             warm Live sessions  │
            └──────────────────────────────────────────────────────┘
 You ──🎤──▶ [ active agent's Live session ] ──▶ 🔊 reply
                 │ (input+output transcription)
                 ▼
        shared panel transcript ──▶ [ Router: detect addressed agent ]
                 │ switch?                         │ stay?
                 ▼                                 ▼
        Host narrates handoff → re-route mic   keep mic on active agent
        + prime next agent w/ transcript+memory
```
- **One Live session per persona** (own `system_instruction`, own **voice**, own `recall_memory`).
  Reuses [gemini_live.py](file:///c:/Users/loq/Desktop/learn/personas/app/services/gemini_live.py).
- **Router** (LangGraph) owns the floor: name-based detection now, LLM intent fallback later.
- **Context passing** = transcript relay: prime the next agent via `send_client_content` with the
  shared transcript; never pipe audio agent→agent.

## 🗄️ Data model (later slice)
A `panel_sessions` row + `panel_participants` (m2m persona↔panel) + reuse `messages` with a
`sender_persona_id` (nullable = user/host). Persistence can lag the in-memory orchestration.

## 🔌 WS protocol (additive to /ws/live) — `/ws/panel/{id}`
```
client → server:  <binary mic PCM>   {type:"select_roster", persona_ids:[...]}   {type:"interrupt"}
server → client:  <binary audio>  {type:"active_speaker", persona_id, name}
                  {type:"transcript", speaker, text, final}   {type:"handoff", from, to}
                  {type:"error"|"ready"}
```

## 🧩 Build slices
- **P-1 — Router core** ✅ `detect_route()` (`panel/router.py`) — 7 tests.
- **P-2 — PanelState orchestrator** ✅ `panel/session.py` — roster, active speaker, shared transcript, `build_agent_priming` — 7 tests.
- **P-3 — `/ws/panel/{id}` endpoint** ✅ `panel_ws.py` — one Live session at a time; host greet; `route_to_agent` tool switch; transcript priming.
- **P-4 — UI** ✅ `/panel` (`panel.html` + `panel.js extends LiveAudioClient`).
- **Polish** ✅ `route_to_agent` tool routing (robust to STT errors); English STT pin (`LIVE_LANGUAGE`); agents follow current topic.
- **P-5 — Persistence + integration tests** ⏳ panel models/migration; persist panel turns; integration test of the handoff.

## ⚠️ Risks
- Switch detection is name-based (call agents by name); indirect address needs the LLM fallback.
- Handoff latency (prime next session) — keep sessions warm.
- Concurrency: "free unlimited" ≠ unlimited *concurrent*; fine for 1 user + host + 2–3 agents.
- Echo: open mic + speakers; require `echoCancellation: true` / headphones.

## 🔗 Links
- [[05 — Frontend/Voice Session Roadmap — V1 to V5]] · [[03 — Memory Layer/Memory in a Live Voice Session]] · [[06 — Logs/Current Context]]
