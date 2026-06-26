"""Voice-panel session state + context assembly (host-led handoff).

In-memory state for one panel WebSocket: the roster, who currently holds the floor, and the
shared transcript that lets the host "hear" the whole conversation. The actual Gemini Live
session objects are managed by the WS endpoint (P-3); this layer is the testable brain.

See [[Master Plan — Voice Panel (Host-Led, Subagent-Ready)]].
"""

from dataclasses import dataclass, field

from app.services.panel.router import PanelParticipant, RouteDecision, detect_route
from app.services.memory import MemoryService
from app.services.prompt_builder import format_retrieved_memories

USER_LABEL = "You"


@dataclass
class TranscriptEntry:
    speaker: str
    text: str


def build_panel_transcript_block(entries: list[TranscriptEntry], limit: int = 20) -> str:
    """Render the recent panel transcript as text to prime the next agent (pure)."""
    recent = [e for e in entries[-limit:] if e.text and e.text.strip()]
    if not recent:
        return ""
    lines = [f"{e.speaker}: {e.text.strip()}" for e in recent]
    return "PANEL CONVERSATION SO FAR:\n" + "\n".join(lines)


@dataclass
class PanelState:
    roster: list[PanelParticipant]
    active_id: str | None = None
    transcript: list[TranscriptEntry] = field(default_factory=list)
    host_name: str = "Host"

    def participant_by_id(self, persona_id: str | None) -> PanelParticipant | None:
        if persona_id is None:
            return None
        return next((p for p in self.roster if p.persona_id == persona_id), None)

    def name_for(self, persona_id: str | None) -> str:
        p = self.participant_by_id(persona_id)
        return p.name if p else self.host_name

    def record_user(self, text: str) -> None:
        if text and text.strip():
            self.transcript.append(TranscriptEntry(USER_LABEL, text.strip()))

    def record_agent(self, persona_id: str | None, text: str) -> None:
        if text and text.strip():
            self.transcript.append(
                TranscriptEntry(self.name_for(persona_id), text.strip())
            )

    def route(self, utterance: str) -> RouteDecision:
        return detect_route(utterance, self.roster, self.active_id)

    def apply_route(self, decision: RouteDecision) -> RouteDecision:
        """Mutate active speaker on a switch; return the decision for chaining."""
        if decision.action == "switch" and decision.target_id:
            self.active_id = decision.target_id
        return decision

    def transcript_text(self, limit: int = 20) -> str:
        return build_panel_transcript_block(self.transcript, limit)

    def handoff_line(self, to_name: str) -> str:
        """Short narration the host speaks when passing the floor to another agent."""
        return f"Let me bring in {to_name}."


async def build_agent_priming(persona_id, conversation_id, state: PanelState) -> str:
    """Context handed to an agent when it takes the floor: its own long-term memory preamble
    + the shared panel transcript so far. This is how 'switch with full context' works."""
    mems = await MemoryService().get_preamble_memories(persona_id, conversation_id)
    memory_block = format_retrieved_memories(mems)
    transcript_block = state.transcript_text()
    return "\n\n".join(b for b in (memory_block, transcript_block) if b)
