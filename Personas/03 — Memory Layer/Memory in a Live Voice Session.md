---
title: "Memory in a Live Voice Session"
type: guide
status: active
updated: 2026-06-25
---

# 🎙️🧠 Memory in a Live Voice Session

This document explains **how the memory layer feeds a Gemini Live (full-duplex voice) session** — specifically the question: *does the model automatically have context, or do we re-provide the summary on every turn?*

> [!important] The one-sentence answer
> **You never re-inject context per turn.** Gemini Live holds the *within-session* turn history automatically; long-term memory is injected **once at connect time** (preamble) and then pulled **on-demand mid-session** via the `recall_memory` tool. Compare this with the text-chat flow in [[How RAG and Persistent Memory Work]], where context is reassembled *every* turn.

---

## 🧩 Two kinds of context (they behave oppositely)

| Context kind | Who manages it | When it's provided |
|---|---|---|
| **Within-session turns** (what was said earlier *this* call) | **Gemini Live, automatically** — kept server-side in the session's context window for the life of the WebSocket. Bounded by `context_window_compression` (sliding window). | Never re-sent. Turn N automatically "sees" turns 1…N-1. |
| **Cross-session long-term memory** (facts/summary from *past* calls) | **Us** — injected from the `memories` table. | (a) **Once** at connect, baked into `system_instruction`. (b) **On-demand** during the call via the `recall_memory` tool. |

The mistake to avoid: thinking we must re-feed the rolling summary before each spoken reply. We don't — that's the difference between a stateless `generate_content` call (text chat) and a stateful Live *session*.

---

## 🔄 The full process, listed out

### ▶️ BEFORE the session — "warm start" (runs once, at connect)

Handled in [live_ws.py](file:///c:/Users/loq/Desktop/learn/personas/app/api/live_ws.py) when the `/ws/live/{conversation_id}` socket opens:

1. **Load** the `Conversation` + its `Persona` (system prompt, voice, temperature).
2. **Fetch preamble memory** — `MemoryService.get_preamble_memories(persona_id, conversation_id)` pulls the persona's durable context: the latest **rolling summary** + top **facts / preferences / goals**.
3. **Format** it into a text block via `format_retrieved_memories(...)`.
4. **Build the system instruction** — `build_system_instruction(persona.system_prompt, memory_block)` ([gemini_live.py](file:///c:/Users/loq/Desktop/learn/personas/app/services/gemini_live.py)) concatenates: persona prompt + memory block + a voice directive ("keep replies short & conversational; use `recall_memory` when the user references the past").
5. **Build the Live config** — `build_live_config(...)` attaches: the system instruction, the `recall_memory` tool (and optional Google Search), audio transcription (in + out), session resumption, and sliding-window compression.
6. **Open the session** — `client.aio.live.connect(model=LIVE_MODEL, config=config)`. The model is now primed with long-term memory **before the user says a word.**

### 🔊 DURING the session — continuous, per turn

Two concurrent tasks run for the life of the socket (see [[Master Plan — Live Voice (Subagent-Ready)]]):

7. **`uplink`** streams mic PCM16 frames → `session.send_realtime_input(...)`. (No need to mark turn boundaries — Gemini's built-in VAD detects start/stop of speech.)
8. **`downlink`** loops over `session.receive()` — which is a **per-turn generator**, so it's wrapped in an outer `while True:` to span the whole conversation. Per message it forwards: raw audio → browser, input/output **transcripts**, `interrupted` (barge-in), and `turn_complete`.
9. **Within-session memory = automatic.** The model already remembers everything said so far this call. Nothing is re-injected.
10. **On-demand recall (mid-session RAG).** If the user references something not in the preamble, the *model* emits a `recall_memory` tool call → we run `MemoryService.retrieve_context(persona_id, conversation_id, query)` (embed query → pgvector cosine top-K) → return it via `session.send_tool_response(...)`. The tool is **`NON_BLOCKING`**, so speech isn't stalled while the lookup runs.
11. **Persist each turn.** On every `turn_complete`, `persist_turn(...)` writes the user + assistant messages into the `messages` table — the raw transcript log and short-term history for any later text turns.

### ⏹️ AFTER the session — consolidate (runs once, on disconnect)

12. **`SummarizerService.maybe_summarize(conversation_id, force=True)`** fires in the `finally` block. It reads messages since the watermark, updates the **rolling narrative summary**, extracts new discrete **facts**, embeds them, and stores them in `memories`.
13. **The loop closes:** those new summary + facts become the **preamble** (step 2) of the *next* session. That's how the persona "remembers" across calls.

```
 PAST SESSIONS ──► summary + facts (memories table)
                        │
                        ▼  (step 2: preamble, ONCE at connect)
              ┌───────────────────────┐
              │  Live session opens    │
              │  model is "warm"       │
              └──────────┬─────────────┘
                         │  within-session turns: AUTOMATIC (no re-inject)
                         │  + on-demand recall_memory tool (RAG mid-call)
                         ▼
              ┌───────────────────────┐
              │  turn_complete → persist messages
              └──────────┬─────────────┘
                         ▼  (on disconnect)
                 maybe_summarize() ──► new summary + facts ──┐
                                                             │
                         ┌───────────────────────────────────┘
                         ▼
                 feeds the NEXT session's preamble
```

---

## 🆚 How this differs from the text-chat flow

- **Text chat** ([[How RAG and Persistent Memory Work]]): stateless `generate_content` per message → context (short-term window + summary + RAG hits) is **reassembled and re-sent every single turn**.
- **Live voice** (this doc): one stateful **session** → context is sent **once** at the top; the model retains turns itself; extra memory arrives only when the model *asks* via the tool.

---

## 🛠️ Model backend note (migration COMPLETE, 2026-06-25)

The *flow* above is independent of which models do the work. The memory backends have been moved
**local (Ollama)** to escape free-tier quota `429`s — this is now **shipped in code**, not pending:

- **Embeddings** (`recall_memory` + summarizer fact indexing): `text-embedding-004` → **`nomic-embed-text`** via Ollama ([embeddings.py](file:///c:/Users/loq/Desktop/learn/personas/app/services/embeddings.py)). Still **768-dim**, so the `Vector(768)` column is unchanged. Existing vectors were re-embedded once via [scripts/reembed_memories.py](file:///c:/Users/loq/Desktop/learn/personas/scripts/reembed_memories.py) (Gemini and Nomic vectors aren't comparable).
- **Summarization** (step 12): `gemini-2.5-pro` (free quota = 0 → always failed) → **`qwen3:8b`** via Ollama ([summarizer.py](file:///c:/Users/loq/Desktop/learn/personas/app/services/summarizer.py)), with JSON schema + thinking disabled.
- **The live voice conversation itself stays on Gemini Live** — that's the realtime/barge-in feature and it has free/unlimited quota.

> [!note] Consequence: the memory layer now depends on a running Ollama (`OLLAMA_BASE_URL`) with
> `nomic-embed-text` + `qwen3:8b` pulled. If Ollama is down, retrieval + summarization fail (logged,
> non-fatal) but the live/text conversation still runs on Gemini.

---

## 🔗 Related
- [[Memory Layer Overview]] — the two-tier architecture
- [[How RAG and Persistent Memory Work]] — the per-turn text-chat assembly
- [[Master Plan — Live Voice (Subagent-Ready)]] — the WS protocol & work packages
- [[Voice Session Roadmap — V1 to V5]] — where Live (L1) sits in the roadmap
