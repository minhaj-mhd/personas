---
title: "Memory Layer Overview"
type: reference
status: active
updated: 2026-06-25
---

# 🧠 Memory Layer Overview

The **Application Memory Layer** is the core feature that separates this platform from basic chat applications. It enables AI personas to recall details, preferences, and facts shared in past sessions, while letting you feed them reference documents (knowledge bases) to utilize during conversations.

---

## 🏛️ The Two-Tier Memory Architecture

To balance context limitations, database costs, and query speed, memory is divided into two distinct systems that merge dynamically before every generation turn:

```
                               ┌─────────────────────────┐
                               │       User Input        │
                               └────────────┬────────────┘
                                            │
                     ┌──────────────────────┴──────────────────────┐
                     ▼                                             ▼
       [ Tier 1: Short-Term Context ]                [ Tier 2: Long-Term Memory ]
   ┌───────────────────────────────────┐         ┌───────────────────────────────────┐
   │ Pulls last N messages from DB.    │         │ pgvector Semantic Retrieval &     │
   │ Preserves conversational flow     │         │ Rolling Summaries.                │
   │ (e.g. core references, pronouns). │         │ Preserves facts across sessions.  │
   └─────────────────┬─────────────────┘         └─────────────────┬─────────────────┘
                     │                                             │
                     └──────────────────────┬──────────────────────┘
                                            ▼
                               ┌─────────────────────────┐
                               │ Prompt Context Assembly │
                               └────────────┬────────────┘
                                            │
                                            ▼
                               ┌─────────────────────────┐
                               │   Gemini 2.5 API Call   │
                               └─────────────────────────┘
```

> [!note] Live voice sessions work differently
> The flow below describes the **per-turn text-chat assembly**. A **Gemini Live voice session** injects long-term memory only **once at connect** (then the model retains turns automatically + pulls more on-demand via a tool). See [[Memory in a Live Voice Session]].

### 1. Tier 1: Short-Term Context (Recent Conversation Window)
- **What it is**: A sliding window containing the last `SHORT_TERM_MESSAGES` (default: 12) turns of the active chat.
- **Why it is needed**: Enables the LLM to understand immediate pronouns (e.g. *"What did you say about it?"*), conversational context, and sentence flows.
- **Implementation**: Fetched from the `messages` table sorted by `created_at` inside [voice_ws.py](file:///c:/Users/loq/Desktop/learn/personas/app/api/voice_ws.py#L70-L81).

### 2. Tier 2: Long-Term Memory (Semantic & Narrative Context)
- **What it is**: Custom reference knowledge and extracted facts that persist across different chat sessions.
- **Why it is needed**: Bypasses context limits, controls Gemini token usage costs, and allows a single persona to remember details forever.
- **Implementation**: Managed by database vectors and pgvector searches, combining:
  1. **Narrative Summaries**: A paragraph summarizing the whole session, updated periodically.
  2. **User Facts**: Individual key facts (e.g., *"User lives in Seattle"* or *"User has a dog named Rex"*) extracted from chat and converted to embeddings.
  3. **RAG Documents**: Chunks of text files uploaded to the persona's knowledge base.

---

## ⚙️ Service Separation of Concerns

The memory layer is structured using three specialized service layers to keep logic separated and testable:

| Service | Primary Responsibility | Code File |
|---|---|---|
| **Embeddings Service** | Generates 768-dimension vector arrays from strings using the `nomic-embed-text (Ollama)` model. Supports single and batch queries. | [embeddings.py](file:///c:/Users/loq/Desktop/learn/personas/app/services/embeddings.py) |
| **Memory Service** | Splits documents using a word-aligned sliding window chunker. Runs cosine distance searches using the `pgvector` cosine operator (`<=>`, via `.cosine_distance()`) to retrieve semantically matched facts. | [memory.py](file:///c:/Users/loq/Desktop/learn/personas/app/services/memory.py) |
| **Summarizer Service** | Checks message watermarks, runs asynchronous `qwen3:8b (Ollama)` summarizers using structured JSON schemas, updates narrative summaries, and extracts user facts. | [summarizer.py](file:///c:/Users/loq/Desktop/learn/personas/app/services/summarizer.py) |

---

## 🧪 The Proof of Correctness (Definition of Done)

The memory layer is verified using automated integration tests located in [test_memory.py](file:///c:/Users/loq/Desktop/learn/personas/app/tests/test_memory.py). 

The key test case is **`test_cross_session_resume_recall`**. This test runs a complete simulation:
1. **Session 1**: The user tells a persona a unique fact (e.g. *"I have a pet turtle named Shelly"*).
2. **Summary Trigger**: The system runs the summarizer to extract this fact and store its embedding in the database.
3. **Session 2**: A brand new session is opened for the same persona. The user asks: *"What pet do I have?"*
4. **Assert Check**: The test asserts that the database retrieval successfully locates the turtle fact and injects it into the prompt assembly, proving that the persona has cross-session memory.

---

## ✅ Implementation Status — Plan → Code (2026-06-25)

Every capability below is **implemented and live** in the codebase. Verified against the running DB
(currently **6 summaries + 36 embedded facts**; all facts carry a vector, summaries don't).

| Capability | Status | Where |
|---|---|---|
| `memories` table — pgvector `Vector(768)`, persona-scoped, nullable `conversation_id`, `importance_score`, JSON `metadata` | ✅ Implemented | [models/memory.py](file:///c:/Users/loq/Desktop/learn/personas/app/models/memory.py) |
| **Local embeddings** — `nomic-embed-text` via Ollama (768-dim, single + batch) | ✅ Implemented · migrated **off** Gemini `text-embedding-004` | [embeddings.py](file:///c:/Users/loq/Desktop/learn/personas/app/services/embeddings.py) |
| **Document / knowledge-base ingestion** — word-aligned chunker (500/100 overlap), batch embed, `memory_type='document'`, `conversation_id=NULL` (persona-global) | ✅ Implemented (no docs ingested yet) | [memory.py](file:///c:/Users/loq/Desktop/learn/personas/app/services/memory.py) `chunk_text` / `ingest_document` |
| **Semantic retrieval** — pgvector cosine (`<=>`), persona-scoped, `distance < 0.7`, top-K (5), latest summary always prepended | ✅ Implemented | [memory.py](file:///c:/Users/loq/Desktop/learn/personas/app/services/memory.py) `retrieve_context` |
| **Rolling summarization** — `qwen3:8b` via Ollama, JSON schema (summary + facts), watermark, importance 0.5 (summary) / 0.8 (fact) | ✅ Implemented · migrated **off** `gemini-2.5-pro` (free quota = 0) | [summarizer.py](file:///c:/Users/loq/Desktop/learn/personas/app/services/summarizer.py) |
| **Prompt assembly / injection** — `### LONG-TERM MEMORY & CONTEXT` block | ✅ Implemented | [prompt_builder.py](file:///c:/Users/loq/Desktop/learn/personas/app/services/prompt_builder.py) |
| **Text-chat per-turn reassembly** — short window + latest summary + RAG hits | ✅ Implemented | [voice_ws.py](file:///c:/Users/loq/Desktop/learn/personas/app/api/voice_ws.py) |
| **Live-voice warm start** — preamble memories at connect (no embedding call) | ✅ Implemented | [memory.py](file:///c:/Users/loq/Desktop/learn/personas/app/services/memory.py) `get_preamble_memories` |
| **Live-voice mid-session RAG** — `recall_memory` `NON_BLOCKING` tool | ✅ Implemented | [live_ws.py](file:///c:/Users/loq/Desktop/learn/personas/app/api/live_ws.py) `handle_tool_call` |
| **Consolidation on Live disconnect** — `maybe_summarize(force=True)` | ✅ Implemented | [live_ws.py](file:///c:/Users/loq/Desktop/learn/personas/app/api/live_ws.py) `finally` |
| **One-time re-embed migration** (Gemini → Nomic vectors aren't comparable) | ✅ Script shipped | [scripts/reembed_memories.py](file:///c:/Users/loq/Desktop/learn/personas/scripts/reembed_memories.py) |
| **Cross-session resume-recall test** (definition of done) | ✅ Passing | [test_memory.py](file:///c:/Users/loq/Desktop/learn/personas/app/tests/test_memory.py) |

**Memory types actually produced:** `summary`, `fact`, `document`. The model enum also lists
`preference` / `goal` / `topic`, but the summarizer's `SummaryOutput` currently folds those into
`fact` — they're reserved for a future finer-grained extractor.

**External dependency note:** the memory layer now requires a running **Ollama** instance
(`OLLAMA_BASE_URL`, default `http://localhost:11434`) with `nomic-embed-text` + `qwen3:8b` pulled.
Only the realtime conversation (text chat + Live voice) still calls Gemini.
