---
title: "Persona Catalog"
type: reference
status: wip
updated: 2026-06-17
---

# 🎭 Persona Catalog

System-prompt template + built-in personas. See IMPLEMENTATION_PLAN §7.

## Template fields
`name` · `description` · `personality_traits` · `speaking_style` · `goals` · `constraints` ·
`domain_expertise` · `voice` · `temperature`. Backend assembles these into `system_prompt`.

## Built-in (seed, `is_builtin=true`)
- Interviewer (technical / HR / behavioral)
- Language Specialist (grammar, pronunciation, vocabulary)
- Teacher / Tutor
- Story Teller
- Career Coach
- Debate Partner
- Therapist-style Listener — **non-clinical**; keep disclaimer + crisis-resource escalation in prompt.

## Custom personas
User-built via the prompt-builder form → stored with `is_builtin=false`. Treat custom `system_prompt` as untrusted (prompt-injection aware).

## Notes log
- _(none yet)_
