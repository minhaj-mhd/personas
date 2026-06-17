---
title: "Memory Layer Overview"
type: reference
status: wip
updated: 2026-06-17
---

# 🧠 Memory Layer Overview (the product feature)

This is the **application's** persistent memory — distinct from this dev vault. The platform's
reason to exist. See IMPLEMENTATION_PLAN §6.

## Two tiers, reassembled every turn
- **Short-term**: last N messages (start N=12), token-budgeted.
- **Long-term**: rolling Gemini summaries + extracted facts/preferences/goals/topics, embedded and
  stored in `memories`; retrieved by cosine similarity scoped to `persona_id`, ranked by
  `similarity × importance`, top-k (start k=5), **always** including the latest summary.

## Prompt assembly order
`system_prompt` → long-term (summary + retrieved facts) → recent window → current user input.

## Definition of done (the proof)
The **resume-recall test**: mention facts, close the session, open a *new* session with the same
persona → it recalls them. Memory is not "working" until this is green. Cite the test.

## Tuning knobs
`SHORT_TERM_MESSAGES`, `SUMMARIZE_THRESHOLD`, `RETRIEVE_TOP_K`, importance weights — log any change.

## Notes log
- _(none yet)_
