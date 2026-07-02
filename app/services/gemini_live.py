import logging
from google import genai
from google.genai import types
from app.config import settings

logger = logging.getLogger(__name__)

VALID_VOICES = {"Puck", "Charon", "Kore", "Fenrir", "Aoede", "Leda", "Orus", "Zephyr"}


def resolve_voice(persona_voice: str | None) -> str:
    if persona_voice and persona_voice in VALID_VOICES:
        return persona_voice
    return settings.LIVE_VOICE


def build_system_instruction(base_prompt: str, memory_block: str) -> str:
    directive = (
        "You have access to a 'recall_memory' tool. Call it whenever the user references "
        "past conversations, facts, or preferences. Keep your spoken replies concise, natural, "
        "and conversational (1-4 sentences) as you are communicating via audio."
    )
    parts = [base_prompt]
    if memory_block:
        parts.append(memory_block)
    parts.append(directive)
    return "\n\n".join(parts)


def recall_memory_declaration() -> types.FunctionDeclaration:
    return types.FunctionDeclaration(
        name="recall_memory",
        description="Search past conversations for facts, preferences, goals, or documents.",
        behavior=types.Behavior.NON_BLOCKING,
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "query": types.Schema(
                    type=types.Type.STRING,
                    description="The specific fact or topic to recall.",
                )
            },
            required=["query"],
        ),
    )


def route_to_agent_declaration() -> types.FunctionDeclaration:
    """Tool the host/agents call to hand the live floor to another panelist. Robust to
    mispronounced/abbreviated names because the model resolves the intent, not a regex."""
    return types.FunctionDeclaration(
        name="route_to_agent",
        description=(
            "Hand the live conversation over to another panelist. Call this the moment the user "
            "asks to speak with, or directs their question to, a specific panelist by name — even "
            "if the name is abbreviated or slightly mispronounced."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "agent_name": types.Schema(
                    type=types.Type.STRING,
                    description="The panelist to switch to, e.g. 'Alistair' or 'Elena'.",
                )
            },
            required=["agent_name"],
        ),
    )


def _transcription_config() -> types.AudioTranscriptionConfig:
    """Plain transcription config (auto-detect language).

    NOTE: `language_codes` is ONLY supported on the Gemini Enterprise Agent Platform, NOT the
    Developer API — passing it makes the Live session reject the config and disconnect immediately.
    So we leave language auto-detection on. (`LIVE_LANGUAGE` is retained for future Enterprise use.)
    """
    return types.AudioTranscriptionConfig()


def build_live_config(
    system_instruction: str,
    voice: str,
    temperature: float,
    enable_search: bool,
    routing: bool = False,
) -> types.LiveConnectConfig:

    fns = [recall_memory_declaration()]
    if routing:
        fns.append(route_to_agent_declaration())
    tools = [types.Tool(function_declarations=fns)]
    if enable_search:
        tools.append(types.Tool(google_search=types.GoogleSearch()))

    return types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        system_instruction=types.Content(
            parts=[types.Part.from_text(text=system_instruction)]
        ),
        temperature=temperature,
        tools=tools,
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
            )
        ),
        input_audio_transcription=_transcription_config(),
        output_audio_transcription=_transcription_config(),
        session_resumption=types.SessionResumptionConfig(),
        context_window_compression=types.ContextWindowCompressionConfig(
            sliding_window=types.SlidingWindow()
        ),
    )


class GeminiLiveService:
    def __init__(self, client: genai.Client | None = None):
        self.client = client or genai.Client(api_key=settings.GEMINI_API_KEY)

    def connect(self, config: types.LiveConnectConfig):
        return self.client.aio.live.connect(model=settings.LIVE_MODEL, config=config)
