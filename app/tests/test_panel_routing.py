"""Tests for the tolerant agent-name resolver used by the panel's route_to_agent tool."""

from app.api.panel_ws import resolve_agent_name
from app.services.panel.router import PanelParticipant

ROSTER = [
    PanelParticipant("a1", "Alistair"),
    PanelParticipant("e1", "Elena"),
    PanelParticipant("m1", "Marcus"),
]


def test_exact_and_case_insensitive():
    assert resolve_agent_name("Alistair", ROSTER).persona_id == "a1"
    assert resolve_agent_name("alistair", ROSTER).persona_id == "a1"
    assert resolve_agent_name("ELENA", ROSTER).persona_id == "e1"


def test_prefix_abbreviation():
    # The model normalizes mispronounced/abbreviated names; resolver tolerates prefixes.
    assert resolve_agent_name("Ali", ROSTER).persona_id == "a1"
    assert resolve_agent_name("Marc", ROSTER).persona_id == "m1"


def test_no_match_returns_none():
    assert resolve_agent_name("nobody", ROSTER) is None
    assert resolve_agent_name("", ROSTER) is None
