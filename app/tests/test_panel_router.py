"""Unit tests for the voice-panel floor router (pure logic; no DB, no network)."""

from app.services.panel.router import PanelParticipant, detect_route

ROSTER = [
    PanelParticipant("a1", "Alistair"),
    PanelParticipant("e1", "Elena"),
]


def test_switch_by_name_from_host():
    d = detect_route("I want to talk to Alistair", ROSTER, active_id=None)
    assert d.action == "switch"
    assert d.target_id == "a1"


def test_switch_mid_conversation():
    # Talking to Alistair, then calling Elena hands the floor to Elena.
    d = detect_route("Elena, what do you think about this?", ROSTER, active_id="a1")
    assert d.action == "switch"
    assert d.target_id == "e1"


def test_stay_when_addressing_current_agent():
    d = detect_route("Alistair, can you elaborate on that?", ROSTER, active_id="a1")
    assert d.action == "stay"
    assert d.target_id == "a1"


def test_stay_when_no_name():
    d = detect_route("tell me more about that", ROSTER, active_id="a1")
    assert d.action == "stay"
    assert d.target_id == "a1"


def test_at_mention():
    d = detect_route("@elena hello there", ROSTER, active_id="a1")
    assert d.action == "switch"
    assert d.target_id == "e1"


def test_name_is_word_boundary():
    # "Elena" must match as a word, not inside another word.
    d = detect_route("the calendar is full", ROSTER, active_id="a1")
    assert d.action == "stay"  # 'calendar' must NOT match 'Elena'/'Alistair'


def test_to_host():
    d = detect_route("who can help me with my resume?", ROSTER, active_id="a1")
    assert d.action == "to_host"
