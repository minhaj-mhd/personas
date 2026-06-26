"""Unit tests for PanelState orchestration logic (pure; no DB, no network)."""

from app.services.panel.router import PanelParticipant
from app.services.panel.session import (
    PanelState,
    TranscriptEntry,
    build_panel_transcript_block,
)


def make_state():
    return PanelState(
        roster=[PanelParticipant("a1", "Alistair"), PanelParticipant("e1", "Elena")]
    )


def test_route_and_apply_switches_floor():
    s = make_state()
    d = s.apply_route(s.route("I want to talk to Alistair"))
    assert d.action == "switch"
    assert s.active_id == "a1"


def test_record_uses_correct_speaker_labels():
    s = make_state()
    s.active_id = "a1"
    s.record_user("Hi there")
    s.record_agent("a1", "Hello, I'm Alistair")
    assert s.transcript[0].speaker == "You"
    assert s.transcript[1].speaker == "Alistair"


def test_name_for_unknown_is_host():
    s = make_state()
    assert s.name_for(None) == "Host"
    assert s.name_for("nope") == "Host"
    assert s.name_for("e1") == "Elena"


def test_transcript_block_pure():
    entries = [TranscriptEntry("You", "hi"), TranscriptEntry("Alistair", "hello")]
    block = build_panel_transcript_block(entries)
    assert "PANEL CONVERSATION SO FAR" in block
    assert "You: hi" in block
    assert "Alistair: hello" in block


def test_transcript_block_empty():
    assert build_panel_transcript_block([]) == ""
    assert build_panel_transcript_block([TranscriptEntry("You", "   ")]) == ""


def test_handoff_line():
    s = make_state()
    assert s.handoff_line("Elena") == "Let me bring in Elena."


def test_full_handoff_sequence():
    s = make_state()
    # Start: call Alistair
    s.record_user("talk to Alistair")
    s.apply_route(s.route("talk to Alistair"))
    assert s.active_id == "a1"
    s.record_agent("a1", "Hi, Alistair here.")
    # Mid-conversation: call Elena -> floor switches, transcript carries history
    s.record_user("Elena, what is your take?")
    d = s.apply_route(s.route("Elena, what is your take?"))
    assert d.action == "switch"
    assert s.active_id == "e1"
    block = s.transcript_text()
    assert "Alistair: Hi, Alistair here." in block  # Elena gets the prior context
