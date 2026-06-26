---
title: "Master Plan — Local Memory Models (Ollama) (Subagent-Ready)"
type: plan
status: active
updated: 2026-06-19
---

# 🦙 Master Plan — Local Memory Models (Ollama)

> [!abstract] Objective
> Move the two **background memory jobs** — **embeddings** and **summarization** — off the Gemini cloud API onto a **local Ollama** runtime. This eliminates free-tier quota `429`s (which currently break summarization entirely — `gemini-2.5-pro` has free quota `0`), removes a network dependency, and keeps memory data on-device. **The live voice conversation stays on Gemini Live** (realtime/barge-in feature, free/unlimited quota, native transcription). See [[Memory in a Live Voice Session]].

> [!info] How to use this doc with subagents
> This plan is **self-contained**. Each Work Package (WP) lists its files, exact code, and acceptance test. Hand a subagent a single WP plus **§2 Shared Contracts**. Respect the dependency graph in **§4**. Do **not** change public method signatures — every change is internal.

---

## §1 — Verified facts (checked on this machine, 2026-06-19)

These were validated directly, not assumed:

- ✅ **Ollama is running** at `http://localhost:11434` (`GET /api/tags` responds).
- ✅ **`qwen3:8b` is pulled** (8.2B, Q4_K_M, tools+thinking, 40K ctx) — the summarizer model.
- ✅ **`/api/chat` structured output works**: with `"format": <JSON schema>` + `"think": false`, `qwen3:8b` returns **clean JSON matching the schema, with no `<think>` tags**. Verified with the `{summary, facts}` schema.
- ✅ **`httpx 0.28.1` is installed** in `.venv` (transitive via google-genai) → use it; **no new dependency**, no `ollama` pip package.
- ✅ **`EmbeddingsService` is the only embedding chokepoint** — consumed in exactly 3 call sites (see §2.4). Rewriting its internals updates all callers.
- ✅ **Embedding column is `Vector(768)`** ([memory.py:30](file:///c:/Users/loq/Desktop/learn/personas/app/models/memory.py#L30)).
- ⚠️ **`nomic-embed-text` not yet pulled.** It outputs **768-dim** (matches the column) — **WP-1 must pull it and confirm `dim == 768`** before anything else. A completion model (`qwen3`) returns `501 Not Implemented` on `/api/embed` — embeddings require a dedicated embedding model.

---

## §2 — Shared Contracts (read first, every WP depends on this)

### §2.1 Config keys (added in WP-1, used everywhere)
```python
# app/config.py — Settings
OLLAMA_BASE_URL: str = "http://localhost:11434"
OLLAMA_SUMMARY_MODEL: str = "qwen3:8b"
OLLAMA_EMBED_MODEL: str = "nomic-embed-text"
```
Leave the existing `EMBED_MODEL` / `SUMMARY_MODEL` (Gemini) keys in place — they become unused by these services but stay as documentation/fallback.

### §2.2 Ollama HTTP contracts

**Chat / summarization — `POST {OLLAMA_BASE_URL}/api/chat`** (✅ verified)
```jsonc
// request
{
  "model": "qwen3:8b",
  "messages": [{"role": "user", "content": "<prompt>"}],
  "format": { /* JSON schema, e.g. SummaryOutput.model_json_schema() */ },
  "stream": false,
  "think": false,                 // suppress qwen3 <think> reasoning tokens
  "options": {"temperature": 0.2}
}
// response (relevant field)
{ "message": {"role": "assistant", "content": "<JSON string matching schema>"}, "done": true }
```

**Embeddings — `POST {OLLAMA_BASE_URL}/api/embed`** (documented; WP-1 confirms dim)
```jsonc
// request — "input" accepts a string OR an array of strings
{ "model": "nomic-embed-text", "input": ["text a", "text b"] }
// response — "embeddings" is ALWAYS a list of vectors (length 1 for single input)
{ "embeddings": [[/*768 floats*/], [/*768 floats*/]], "model": "nomic-embed-text" }
```
Fallback for older Ollama (no `/api/embed`): `POST /api/embeddings` `{"model","prompt"}` → `{"embedding":[...]}` (single only).

### §2.3 Behavioral contract — graceful degradation
Both services already wrap their model call in `try/except` and log on failure. **Preserve this.** If Ollama is down, embedding/summary calls must fail softly (log + raise to the existing handler), never crash a live session.

### §2.4 `EmbeddingsService` public interface — MUST NOT CHANGE
```python
async def embed_text(self, text: str) -> list[float]          # returns 768 floats
async def embed_texts(self, texts: list[str]) -> list[list[float]]  # [] for empty input
```
Consumers that must keep working untouched:
- [memory.py:60](file:///c:/Users/loq/Desktop/learn/personas/app/services/memory.py#L60) — `embed_texts(chunks)` (document ingestion)
- [memory.py:106](file:///c:/Users/loq/Desktop/learn/personas/app/services/memory.py#L106) — `embed_text(user_text)` (retrieval query)
- [summarizer.py:122](file:///c:/Users/loq/Desktop/learn/personas/app/services/summarizer.py#L122) — `embed_texts(result.facts)` (fact indexing)

### §2.5 `SummaryOutput` schema — UNCHANGED
```python
class SummaryOutput(BaseModel):
    summary: str
    facts: list[str]
```

---

## §3 — Work Packages

### 🧱 WP-1 — Foundation: pull model + config  *(blocks everything)*
**Files:** `app/config.py` · shell
1. `ollama pull nomic-embed-text`
2. **Verify dimension** (must be 768):
   ```bash
   curl http://localhost:11434/api/embed -d '{"model":"nomic-embed-text","input":"ping"}'
   # confirm len(embeddings[0]) == 768
   ```
   - If `dim != 768`: STOP. The `Vector(768)` column must be altered and a full re-embed forced; escalate before proceeding.
3. Add the three `OLLAMA_*` keys from §2.1 to `Settings`.

**Acceptance:** `python -c "from app.config import settings; print(settings.OLLAMA_EMBED_MODEL)"` works; embed curl returns a 768-length vector.

---

### 🔢 WP-2 — `EmbeddingsService` → Ollama  *(depends on WP-1)*
**File:** `app/services/embeddings.py` — full drop-in replacement:
```python
import logging
import httpx
from app.config import settings

logger = logging.getLogger(__name__)


class EmbeddingsService:
    def __init__(self):
        self.base_url = settings.OLLAMA_BASE_URL.rstrip("/")
        self.model = settings.OLLAMA_EMBED_MODEL

    async def _embed(self, inputs: list[str]) -> list[list[float]]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self.base_url}/api/embed",
                json={"model": self.model, "input": inputs},
            )
            resp.raise_for_status()
            return resp.json()["embeddings"]

    async def embed_text(self, text: str) -> list[float]:
        try:
            return (await self._embed([text]))[0]
        except Exception as e:
            logger.error(f"Error generating text embedding: {e}")
            raise

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            return await self._embed(texts)
        except Exception as e:
            logger.error(f"Error generating batch text embeddings: {e}")
            raise
```
**Acceptance:** `embed_text("hello")` returns a list of 768 floats; `embed_texts([])` returns `[]`; `embed_texts(["a","b"])` returns 2 vectors.

---

### 📝 WP-3 — Summarizer model call → Ollama  *(depends on WP-1; parallel with WP-2)*
**File:** `app/services/summarizer.py`
1. **Imports:** remove `from google import genai` and `from google.genai import types`; add `import re` and `import httpx`.
2. **`__init__`:** drop the genai client; keep embeddings:
   ```python
   def __init__(self):
       self.base_url = settings.OLLAMA_BASE_URL.rstrip("/")
       self.model = settings.OLLAMA_SUMMARY_MODEL
       self.embeddings_service = EmbeddingsService()
   ```
3. **Replace the model call** (current [summarizer.py:95-108](file:///c:/Users/loq/Desktop/learn/personas/app/services/summarizer.py#L95-L108)) with:
   ```python
   try:
       async with httpx.AsyncClient(timeout=120.0) as client:
           resp = await client.post(
               f"{self.base_url}/api/chat",
               json={
                   "model": self.model,
                   "messages": [{"role": "user", "content": prompt}],
                   "format": SummaryOutput.model_json_schema(),
                   "stream": False,
                   "think": False,
                   "options": {"temperature": 0.2},
               },
           )
           resp.raise_for_status()
           content = resp.json()["message"]["content"]

       # Safety net if an Ollama version ignores think:false
       content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
       result = SummaryOutput.model_validate_json(content)
       # ... steps 5–7 (persist summary, embed+store facts, advance watermark) UNCHANGED ...
   ```
   Everything after parsing (`new_summary_mem`, the facts loop using `self.embeddings_service.embed_texts`, the watermark update, `commit`) stays **byte-for-byte the same**, including the existing `except` rollback handler.

**Acceptance:** Running `maybe_summarize(conv_id, force=True)` on a short test conversation creates a `summary` memory + ≥1 `fact` memory and logs success — **no `429`**.

---

### 🔁 WP-4 — One-time re-embed migration  *(depends on WP-2)*
**File:** `scripts/reembed_memories.py` (new)
> Existing vectors were made by `text-embedding-004`; Gemini and Nomic vectors are **not comparable** even at equal dimension. Every stored embedding must be regenerated **once**, or retrieval returns garbage.
```python
import asyncio
from sqlalchemy import select
from app.db import async_session_maker
from app.models.memory import Memory
from app.services.embeddings import EmbeddingsService

BATCH = 32

async def main():
    svc = EmbeddingsService()
    async with async_session_maker() as session:
        rows = (await session.execute(
            select(Memory).where(Memory.embedding.is_not(None))
        )).scalars().all()
        print(f"re-embedding {len(rows)} memories...")
        for i in range(0, len(rows), BATCH):
            chunk = rows[i:i + BATCH]
            embs = await svc.embed_texts([m.content for m in chunk])
            for m, e in zip(chunk, embs):
                m.embedding = e
        await session.commit()
        print("done.")

if __name__ == "__main__":
    asyncio.run(main())
```
Run once: `.venv\Scripts\python.exe scripts/reembed_memories.py`

**Acceptance:** script prints a count and `done.`; spot-check one memory's embedding length is 768.

---

### 📚 WP-5 — Docs sync  *(independent; parallel with WP-2/3)*
**Files:** vault
- [[Memory Layer Overview]] §"Service Separation": change Embeddings row from `text-embedding-004` → `nomic-embed-text (Ollama)`, Summarizer row → `qwen3:8b (Ollama)`.
- [[How RAG and Persistent Memory Work]] §1 and §4: update model names (`text-embedding-004`→nomic; `gemini-2.5-pro`→qwen3:8b) and note local HTTP backend.
- [[Memory in a Live Voice Session]] already carries the migration note — no change.

**Acceptance:** no remaining claim that embeddings/summaries use Gemini in those two docs.

---

### ✅ WP-6 — Verification  *(depends on WP-2, WP-3, WP-4)*
**Files:** `app/tests/test_memory.py` (existing)
1. Smoke: `embed_text("hello")` → `assert len == 768`.
2. Summarizer: force-summarize a seeded conversation → assert summary+facts persisted, no exception.
3. Regression: run `test_cross_session_resume_recall` (the turtle/pet test) → must pass **after** WP-4 re-embed.
4. Grep guard: `embeddings.py` and `summarizer.py` contain **no** `genai` / `generate_content` / `embed_content` references.

**Acceptance:** all three tests green; grep guard clean.

---

## §4 — Dependency graph & parallelization
```
WP-1 (pull + config)  ─┬─►  WP-2 (embeddings) ─►  WP-4 (re-embed) ─┐
                       ├─►  WP-3 (summarizer) ───────────────────►├─►  WP-6 (verify)
                       └─►  WP-5 (docs) ───────────────────────────┘   (also after 2&3)
```
- **WP-1 blocks all.** After it: **WP-2, WP-3, WP-5 run in parallel.**
- **WP-4 needs WP-2.** **WP-6 runs last** (after 2, 3, 4).

---

## §5 — Risks & mitigations
| Risk | Impact | Mitigation |
|---|---|---|
| `nomic-embed-text` dim ≠ 768 | DB insert fails | WP-1 verifies dim first; if mismatch, alter column + full re-embed (escalate) |
| Old Ollama lacks `/api/embed` | embed 404 | Fallback to `/api/embeddings` (`prompt`, single) — loop for batch |
| Ollama version ignores `think:false` | `<think>` pollutes JSON | Regex strip in WP-3 (already included) |
| Ollama not running | embed/summary fail | Existing try/except → soft fail + log; document "Ollama must be running" |
| Re-embed not run before use | retrieval mixes vector spaces → bad recall | Sequence WP-4 before WP-6; don't trust retrieval until done |
| First call cold-loads model | multi-second latency | Generous timeouts (30s embed / 120s chat); jobs are background, non-blocking |

---

## §6 — Definition of Done
- [ ] `nomic-embed-text` pulled, verified 768-dim; `OLLAMA_*` config present.
- [ ] `EmbeddingsService` uses Ollama; all 3 callers work unchanged.
- [ ] Summarizer uses Ollama `/api/chat`; produces `{summary, facts}`; **no 429**.
- [ ] All existing embeddings re-embedded once.
- [ ] `test_cross_session_resume_recall` passes; smoke + grep guard pass.
- [ ] Docs synced; **live voice path untouched and still working**.

---

## 🔗 Related
- [[Memory in a Live Voice Session]] — why transcription stays on Gemini Live
- [[Memory Layer Overview]] · [[How RAG and Persistent Memory Work]] — the systems being modified
- [[Master Plan — Live Voice (Subagent-Ready)]] — sibling subagent plan (same format)
- [[Current Context]] — active focus
