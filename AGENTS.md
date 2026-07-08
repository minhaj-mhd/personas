# 🤖 AI Agent Operating Protocol & Shared Memory Guide

Welcome! If you are an AI coding agent (Claude, Gemini, etc.) pair-programming with the user on
the **AI Multi-Persona Voice Agent Platform**, **you are required to read, understand, and
strictly adhere to this operating protocol.**

This protocol maintains a **cross-session memory layer** for *coding agents* inside the Obsidian
vault at `Personas/`. It ensures continuity, prevents repetitive questioning, keeps context
segregated across conversation threads, and stops the repo from rotting.

> ⚠️ **Two different "memory layers" — do not conflate them.**
> - **This `Personas/` Obsidian vault** = the *coding agent's* continuity notes (what we decided, what's next). Markdown.
> - **The application's memory layer** = the *product feature*: persona conversation history +
>   summarized long-term memory in **Postgres/pgvector**, defined in
>   [`IMPLEMENTATION_PLAN.md`](file:///c:/Users/loq/Desktop/learn/personas/IMPLEMENTATION_PLAN.md) §6.
>   When this file says "memory," it means the `docs/` vault unless it says "application memory layer."

---

## 🏛️ The `Personas/` Vault Structure

A fixed top-level taxonomy. One topic, one home.

- **`Welcome.md`**: Central entry point and navigation index (the map).
- **`AGENTS.md`** (repo root): This protocol. The single source of truth — do not duplicate its body elsewhere.
- **`01 — Architecture/`**: System design. The canonical spec is
  [`IMPLEMENTATION_PLAN.md`](file:///c:/Users/loq/Desktop/learn/personas/IMPLEMENTATION_PLAN.md) (kept at repo root); link to it, don't fork it.
- **`02 — Backend/`**: FastAPI app, data model, REST + WebSocket contracts. (No auth — single-user project.)
- **`03 — Memory Layer/`**: The *application's* short-term window, summarizer, RAG retrieval, prompt assembly.
- **`04 — Personas/`**: System-prompt template, built-in persona definitions, custom-persona rules.
- **`05 — Frontend/`**: Jinja2 templates, HTMX patterns, the voice client (`voice.js`) state machine.
- **`06 — Logs/`**: `Current Context.md` (global active focus), `Conversations/` (per-thread notes),
  `Daily Logs/` (`YYYY-MM-DD.md` archives).
- **`09 — Archive/`**: Obsolete decisions and superseded designs. One focused file per retired concept.

> The vault skeleton already exists. Keep it tidy per **Vault Hygiene** below; if a section folder
> is missing when you need it, create it under `Personas/` following this taxonomy.

---

## 🛠️ Tooling Conventions

Use the project's standard tools for their domain rather than ad-hoc scripts:

- **Database / schema**: change schema **only** via **Alembic migrations** — never hand-edit the
  DB or `CREATE TABLE` by hand. Use the async SQLAlchemy session/repository layer for queries.
- **LLM / embeddings / TTS**: go through the service interfaces (`services/gemini.py`,
  `services/embeddings.py`, `services/tts/`). Never scatter raw `google-genai` calls through routers.
- **Tests**: `pytest` with `pytest-asyncio`; providers (Gemini/embeddings/TTS) are **mocked**,
  and the DB points at a **test database / rolled-back transaction** — see Engineering Discipline §2.
- **Lint/format**: Ruff + Black before finishing a change.
- **MCP**: a **Google Sheets** integration via the Model Context Protocol is wired in but
  **disabled by default** (`MCP_SHEETS_ENABLED=false`). When enabled, live sessions launch a
  configured Sheets MCP server and expose its tools to the agent — see
  [`MCP_GOOGLE_SHEETS.md`](file:///c:/Users/loq/Desktop/learn/personas/MCP_GOOGLE_SHEETS.md)
  and `app/services/mcp/`. Prefer this MCP path over ad-hoc Sheets scripts. If you add
  another MCP server, document it here too.

---

## 🔄 The 4-Phase Agent Continuity Protocol

Execute your work in four distinct phases.

### 🚀 Phase 1: Bootstrapping (Initialization)
As your very first step in a new session you **MUST**:
1. Read **[`Welcome.md`](file:///c:/Users/loq/Desktop/learn/personas/Personas/Welcome.md)** for the system map.
2. Read **[`06 — Logs/Current Context.md`](file:///c:/Users/loq/Desktop/learn/personas/Personas/06%20—%20Logs/Current%20Context.md)** for the global active focus and next steps.
3. Check **`Personas/06 — Logs/Conversations/`** for an active log related to the current task; inherit its state.
4. Skim **[`IMPLEMENTATION_PLAN.md`](file:///c:/Users/loq/Desktop/learn/personas/IMPLEMENTATION_PLAN.md)** for the architecture and which phase (0–5) is in progress.

### 📂 Phase 2: Conversation Segregation
Isolate each work thread so model-tuning context doesn't pollute UI context:
1. Locate or create a note in **`Personas/06 — Logs/Conversations/`**.
2. **File naming**: `Conv-YYYY-MM-DD-Brief-Topic.md` (e.g. `Conv-2026-06-17-Memory-Layer-RAG.md`).
3. **Header template**:
   ```markdown
   ---
   title: "Conversation: [Brief Topic]"
   type: log
   status: active        # active | concluded
   updated: YYYY-MM-DD
   focus_area: "Memory Layer | Backend | Personas | Frontend | Voice | Infra/DB"
   ---

   # 💬 Conversation Context: [Brief Topic]

   ## 🎯 Objectives
   - [ ] Goal 1
   - [ ] Goal 2

   ## 💻 Files Touched
   - [main.py](file:///c:/Users/loq/Desktop/learn/personas/app/main.py)

   ## 📝 Compacted Session Log
   - **Initial state**: 1–2 sentence overview.
   - **Step 1**: action + rationale.

   ## 🔗 Memory Links
   - [[03 — Memory Layer/Prompt Assembly]]
   ```

### ✍️ Phase 3: Compact Logging & Backlinking
- **Be compact**: dense bulleted summaries of decisions and rationale — no raw log dumps or huge code blocks.
- **Backlink**: connect logs to vault docs with `[[Note Name]]` / `[[Folder/Note|Label]]`.
- **Absolute code links**: link the files you edit, e.g.
  `[prompt_builder.py](file:///c:/Users/loq/Desktop/learn/personas/app/services/prompt_builder.py)`, with line ranges when relevant.

### 💾 Phase 4: Teardown & Checkpoint
Before ending your turn/conversation you **MUST**:
1. Tick completed objectives; set the conversation `status` to `concluded` (or leave `active` if follow-ups remain).
2. Update **`06 — Logs/Current Context.md`**: keep **Current Focus** lean (≤ ~10 live items),
   refresh **Next Steps**, and reference your conversation file (`[[06 — Logs/Conversations/Conv-…|Conversation Log]]`).
3. **Git**: this repo is **not initialized yet**. On the first meaningful change, ask the user before
   running `git init`. Whenever a notable task/refactor completes, **proactively ask** whether to commit.
4. **Archive**: after a successful commit, append the compacted summary into the day's
   `06 — Logs/Daily Logs/YYYY-MM-DD.md` and delete the original conversation file.

---

## 🗂️ Vault Hygiene

1. **Every doc has YAML front-matter**: `title`, `type` (spec|reference|guide|log|archive|index),
   `status` (active|wip|concluded|superseded|archived), `updated`.
2. **One topic, one home.** A persona's rules live under `04 — Personas/`; memory-layer behavior under
   `03 — Memory Layer/`. Don't restate the architecture — link to `IMPLEMENTATION_PLAN.md`.
3. **`Welcome.md` is the index.** Keep it current by hand for now (the vault is small); if it
   grows, add a generator and switch to "generated, never hand-edited." Until then, update it when you add/move a doc.
4. **Filenames**: Title Case With Spaces, except dated logs (`YYYY-MM-DD.md`) and `Conv-YYYY-MM-DD-Topic.md`.
5. **The protocol has one source** — this `AGENTS.md`. Any vault pointer to it must stay a pointer, not a copy.

---

## 🧠 Application Memory & Evaluation Discipline

The persistent-memory feature is this product's whole reason to exist. Treat its correctness as load-bearing.

1. **The resume-recall test is the proof.** "The persona remembers across sessions" is only true when the
   automated resume-recall test (IMPLEMENTATION_PLAN §9, Phase 3 "done when") passes. Do not claim memory
   works — in notes, the README, or to the user — without it green. Cite the test.
2. **Claims require artifacts.** Don't write "verified", "remembers", or "context preserved" unless a
   test or run actually checked it. If you didn't verify it, say what was **not** verified.
3. **Determinism in tests.** LLM/embedding/TTS calls are mocked in tests; assert on the **assembled prompt
   and retrieval ranking**, not on the model's free-text output.
4. **Cost discipline.** Every Gemini and embedding call costs money and latency. Use `gemini-2.5-flash`
   for chat, summarize only past the threshold, cache embeddings, and never loop API calls in tests.
   No batch/experimental sweeps of model calls without the user's say-so.
5. **Don't silently change memory tuning.** `SHORT_TERM_MESSAGES`, `SUMMARIZE_THRESHOLD`, `RETRIEVE_TOP_K`,
   importance weights — changing these changes behavior. Note the change and the reasoning in your conversation log.

---

## ⚔️ Engineering Discipline (hard rules)

1. **Secrets never enter git.** `GEMINI_API_KEY` and DB URLs live in `.env` (gitignored).
   Add `.env`, `__pycache__/`, `*.db`, `node_modules/`, and scratch outputs to `.gitignore` **before** the first commit.
2. **Tests must never touch production/dev state or real providers.** Run against a sandbox/test DB
   (or a rolled-back transaction) and mock Gemini/embeddings/TTS. Before finishing, confirm no real DB rows
   or `.env` were mutated by the test run.
3. **Never weaken an assertion, tolerance, or guard to make something pass.** If a real input fails a guard,
   the guard is working — stop and report, don't loosen it.
4. **Schema changes go through Alembic.** No hand-edited DB state, no manual `CREATE TABLE`. Migrations are reviewable and reversible.
5. **Escape user content in templates.** Persona names, messages, and custom prompts are user-supplied —
   rely on Jinja autoescaping; never build HTML by string concatenation. Treat custom `system_prompt`
   text as untrusted (prompt-injection aware) when it can affect other users.
6. **Respect async.** FastAPI handlers are `async`; never block the event loop with sync I/O or `time.sleep`
   in a request/WebSocket path — use the async DB session and async provider clients.
7. **Persona safety is a hard constraint.** The therapist-style listener is **non-clinical**: keep the
   disclaimer and crisis-resource escalation text in its system prompt. Don't remove safety constraints to "improve" replies.
8. **Windows file-encoding discipline.** PowerShell `Out-File`/`>>` defaults to UTF-16 and corrupts UTF-8
   `.md`/`.json`/`.py` files. Always pass `-Encoding utf8`, or use proper file-editing tools instead of shell redirection.
9. **Fill your conversation note for real.** A header-only note defeats the cross-session memory system.
   Log decisions, evidence, and file links as you go — the next agent (and any audit) depends on it.
10. **Verify inherited claims before building on them.** A previous agent's "done"/"works" status is an
    input to check (re-run the test, re-read the code), not a fact to assume.

---
*Follow this protocol exactly. It preserves context, prevents repeated mistakes, and keeps our shared memory trustworthy.*
