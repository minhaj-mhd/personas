"""Conversation export helpers.

Pure rendering functions kept separate from the API layer so they are trivially unit-testable
without spinning up the app or the DB.
"""

import re


def safe_filename(title: str | None, default: str = "conversation") -> str:
    """Turn a conversation title into a safe download filename stem (no extension)."""
    base = title or default
    cleaned = re.sub(r"[^A-Za-z0-9 _-]", "", base).strip()
    cleaned = re.sub(r"\s+", "_", cleaned)
    return (cleaned[:60] or default)


def render_conversation_markdown(conversation, persona, messages) -> str:
    """Render a conversation (its persona + ordered messages) as a Markdown document.

    `conversation` and `persona` may be None-safe ORM objects; `messages` is an ordered list.
    """
    title = getattr(conversation, "title", None) or "Untitled Session"
    persona_name = getattr(persona, "name", None) or "Assistant"

    lines: list[str] = [f"# {title}", ""]
    lines.append(f"**Persona:** {persona_name}")

    description = getattr(persona, "description", None)
    if description:
        lines.append(f"**Description:** {description}")

    created = getattr(conversation, "created_at", None)
    if created:
        lines.append(f"**Started:** {created.strftime('%B %d, %Y at %I:%M %p')}")

    lines.append(f"**Messages:** {len(messages)}")
    lines.append("")
    lines.append("---")
    lines.append("")

    for msg in messages:
        role = getattr(msg, "role", "")
        if role == "assistant":
            speaker = persona_name
        elif role == "user":
            speaker = "You"
        else:
            speaker = (role or "system").title()

        ts = ""
        created_at = getattr(msg, "created_at", None)
        if created_at:
            ts = created_at.strftime("%I:%M %p")

        heading = f"### {speaker}" + (f" · {ts}" if ts else "")
        lines.append(heading)
        lines.append("")
        lines.append(getattr(msg, "content", "") or "")
        lines.append("")

    return "\n".join(lines).strip() + "\n"
