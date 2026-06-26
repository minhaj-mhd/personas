"""Conversation search helpers.

Pure functions kept separate from the API so they are unit-testable without the DB.
"""


def make_snippet(content: str, query: str, radius: int = 60) -> str:
    """Return a short excerpt of `content` centered on the first occurrence of `query`,
    with ellipses where it was trimmed. Falls back to the head of the content."""
    if not content:
        return ""
    low = content.lower()
    ql = (query or "").lower()
    idx = low.find(ql) if ql else -1

    if idx == -1:
        head = content[: 2 * radius].strip()
        return head + ("…" if len(content) > 2 * radius else "")

    start = max(0, idx - radius)
    end = min(len(content), idx + len(query) + radius)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(content) else ""
    return prefix + content[start:end].strip() + suffix
