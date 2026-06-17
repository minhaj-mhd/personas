---
title: "Memory Layer Overview"
type: reference
status: active
updated: 2026-06-17
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
| **Embeddings Service** | Generates 768-dimension vector arrays from strings using Google's `text-embedding-004` model. Supports single and batch queries. | [embeddings.py](file:///c:/Users/loq/Desktop/learn/personas/app/services/embeddings.py) |
| **Memory Service** | Splits documents using a word-aligned sliding window chunker. Runs cosine distance searches using `pgvector` operators (`<->`) to retrieve semantically matched facts. | [memory.py](file:///c:/Users/loq/Desktop/learn/personas/app/services/memory.py) |
| **Summarizer Service** | Checks message watermarks, runs asynchronous Gemini summarizers using structured Pydantic schemas, updates narrative summaries, and extracts user facts. | [summarizer.py](file:///c:/Users/loq/Desktop/learn/personas/app/services/summarizer.py) |

---

## 🧪 The Proof of Correctness (Definition of Done)

The memory layer is verified using automated integration tests located in [test_memory.py](file:///c:/Users/loq/Desktop/learn/personas/app/tests/test_memory.py). 

The key test case is **`test_cross_session_resume_recall`**. This test runs a complete simulation:
1. **Session 1**: The user tells a persona a unique fact (e.g. *"I have a pet turtle named Shelly"*).
2. **Summary Trigger**: The system runs the summarizer to extract this fact and store its embedding in the database.
3. **Session 2**: A brand new session is opened for the same persona. The user asks: *"What pet do I have?"*
4. **Assert Check**: The test asserts that the database retrieval successfully locates the turtle fact and injects it into the prompt assembly, proving that the persona has cross-session memory.
