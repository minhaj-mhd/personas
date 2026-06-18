from google.genai import types
from app.services.gemini_live import (
    resolve_voice,
    recall_memory_declaration,
    build_live_config,
)
from app.services.prompt_builder import format_retrieved_memories
from app.config import settings
from dataclasses import dataclass
from typing import Dict, Any, Optional


@dataclass
class MockMemory:
    memory_type: str
    content: str
    metadata_: Optional[Dict[str, Any]] = None


def test_resolve_voice():
    # Valid voice
    assert resolve_voice("Kore") == "Kore"

    # Invalid voice
    assert resolve_voice("NonExistentVoice") == settings.LIVE_VOICE

    # None voice
    assert resolve_voice(None) == settings.LIVE_VOICE


def test_recall_memory_declaration():
    decl = recall_memory_declaration()
    assert decl.name == "recall_memory"
    assert decl.behavior == types.Behavior.NON_BLOCKING
    assert "query" in decl.parameters.properties
    assert "query" in decl.parameters.required


def test_build_live_config():
    system_instruction = "Hello, world!"
    voice = "Puck"
    temperature = 0.7

    # Test without search
    config_no_search = build_live_config(system_instruction, voice, temperature, False)
    assert config_no_search.response_modalities == ["AUDIO"]
    assert config_no_search.temperature == temperature
    assert (
        config_no_search.speech_config.voice_config.prebuilt_voice_config.voice_name
        == "Puck"
    )
    assert len(config_no_search.tools) == 1
    assert config_no_search.tools[0].function_declarations[0].name == "recall_memory"

    # Test with search
    config_with_search = build_live_config(system_instruction, voice, temperature, True)
    assert len(config_with_search.tools) == 2
    assert config_with_search.tools[1].google_search is not None


def test_format_retrieved_memories():
    # Empty list
    assert format_retrieved_memories([]) == ""

    # Summary only
    mem1 = MockMemory(memory_type="summary", content="User likes cats.")
    res1 = format_retrieved_memories([mem1])
    assert "### LONG-TERM MEMORY & CONTEXT" in res1
    assert "Narrative Summary of Past Conversations:\nUser likes cats." in res1

    # Fact only with metadata
    mem2 = MockMemory(
        memory_type="fact",
        content="User works at Google.",
        metadata_={"source": "FileA"},
    )
    res2 = format_retrieved_memories([mem2])
    assert (
        "Extracted Facts & Uploaded Reference Materials:\n- [FileA]: User works at Google."
        in res2
    )

    # Fact without metadata
    mem3 = MockMemory(memory_type="fact", content="User likes blue.")
    res3 = format_retrieved_memories([mem3])
    assert "Extracted Facts & Uploaded Reference Materials:\n- User likes blue." in res3

    # Both summary and fact
    res4 = format_retrieved_memories([mem1, mem2])
    assert "Narrative Summary of Past Conversations:\nUser likes cats." in res4
    assert (
        "Extracted Facts & Uploaded Reference Materials:\n- [FileA]: User works at Google."
        in res4
    )
