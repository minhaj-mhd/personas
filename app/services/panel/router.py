"""Voice-panel floor router (host-led handoff).

Pure, dependency-free logic so it is trivially unit-testable. The host "hears" the user's
utterance (its transcript) and routes the mic to whichever roster agent the user addresses by
name. This is the deterministic core of the panel; an LLM intent fallback for indirect address
is layered on top later (P-2+).

See [[Master Plan — Voice Panel (Host-Led, Subagent-Ready)]].
"""

import re
from dataclasses import dataclass


@dataclass
class PanelParticipant:
    persona_id: str
    name: str


@dataclass
class RouteDecision:
    action: str  # "stay" | "switch" | "to_host"
    target_id: str | None
    target_name: str | None
    reason: str


# Phrases that hand the floor back to the host/moderator (only when no agent is named).
HOST_PHRASES = (
    "host",
    "moderator",
    "who can help",
    "who should i",
    "introduce me",
    "the panel",
)


def _first_name(name: str) -> str:
    parts = (name or "").strip().split()
    return parts[0].lower() if parts else ""


def detect_route(
    utterance: str,
    roster: list[PanelParticipant],
    active_id: str | None,
) -> RouteDecision:
    """Decide who holds the floor after `utterance`.

    - If the user addresses a roster agent by (first) name or `@name` → switch to them
      (or `stay` if that's already the active speaker).
    - Else if the user asks for the host/moderator → `to_host`.
    - Else → `stay` with the current active speaker.
    """
    text = (utterance or "").lower()

    matched: PanelParticipant | None = None
    for p in roster:
        first = _first_name(p.name)
        if not first:
            continue
        if f"@{first}" in text or re.search(rf"\b{re.escape(first)}\b", text):
            matched = p
            break

    if matched is not None:
        if matched.persona_id == active_id:
            return RouteDecision(
                "stay", active_id, matched.name, f"addressed current agent {matched.name}"
            )
        return RouteDecision(
            "switch", matched.persona_id, matched.name, f"addressed {matched.name}"
        )

    if any(phrase in text for phrase in HOST_PHRASES):
        return RouteDecision("to_host", None, None, "addressed the host/moderator")

    return RouteDecision(
        "stay", active_id, None, "no agent addressed; staying with active speaker"
    )
