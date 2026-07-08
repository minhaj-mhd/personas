import logging
from typing import AsyncGenerator, List
from google import genai
from google.genai import types
from app.config import settings
from app.schemas.personas import PersonaDraft

logger = logging.getLogger(__name__)

PERSONA_DESIGNER_INSTRUCTION = (
    "You are a persona designer for a voice-first AI agent platform. Given a short brief, "
    "design one complete, coherent voice persona and return ONLY the structured fields.\n\n"
    "Guidelines:\n"
    "- name: a fitting human first name or title, no quotes.\n"
    "- description: ONE concise sentence, lowercase, no leading 'is a' — it is rendered as "
    "'You are {name}, {description}.' (e.g. 'a warm cooking coach for nervous beginners').\n"
    "- personality_traits: 3-5 lowercase adjective keywords.\n"
    "- speaking_style: how they sound OUT LOUD — pace, tone, sentence length. Voice-first, so concise.\n"
    "- goals: what the persona actively tries to do for the user during a spoken session.\n"
    "- constraints: what it must never do, PLUS any safety guardrails the domain needs "
    "(e.g. a non-clinical disclaimer and crisis resources for therapy/health; no legal or "
    "financial advice where relevant).\n"
    "- domain_expertise: comma-separated fields of deep knowledge.\n"
    "- temperature: 0.6-0.8 for focused/professional personas, 0.85-1.0 for creative/expressive ones.\n"
    "- voice: pick the single prebuilt voice that best fits. Options:\n"
    "    Puck (upbeat, male), Charon (deep, informative, male), Fenrir (dynamic, excitable, male), "
    "Orus (firm, male), Aoede (breezy, warm, female), Kore (firm, female), "
    "Leda (gentle, youthful, female), Zephyr (bright, female).\n"
    "Keep everything natural for a spoken conversation."
)


class GeminiService:
    def __init__(self):
        # Initialize the client using API key from settings
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)

    async def generate_chat_stream(
        self,
        system_instruction: str,
        chat_history: List[types.Content],
        user_message: str,
        temperature: float = 0.8,
    ) -> AsyncGenerator[str, None]:
        """
        Asynchronously streams token deltas from Gemini.
        """
        contents = list(chat_history)
        contents.append(
            types.Content(role="user", parts=[types.Part.from_text(text=user_message)])
        )

        try:
            response = await self.client.aio.models.generate_content_stream(
                model=settings.CHAT_MODEL,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=temperature,
                ),
            )
            async for chunk in response:
                if chunk.text:
                    yield chunk.text
        except Exception as e:
            logger.error(f"Gemini API streaming error: {e}")
            raise e

    async def draft_persona(self, brief: str) -> PersonaDraft:
        """
        Uses Gemini structured output to turn a free-text brief into a complete,
        reviewable persona draft. Does not persist anything — the caller returns the
        draft to the UI so the user can cross-check and edit before creating.
        """
        try:
            response = await self.client.aio.models.generate_content(
                model=settings.CHAT_MODEL,
                contents=brief,
                config=types.GenerateContentConfig(
                    system_instruction=PERSONA_DESIGNER_INSTRUCTION,
                    temperature=0.7,
                    response_mime_type="application/json",
                    response_schema=PersonaDraft,
                ),
            )
        except Exception as e:
            logger.error(f"Gemini persona draft error: {e}")
            raise

        draft = response.parsed
        if not isinstance(draft, PersonaDraft):
            raise ValueError("Gemini returned no parseable persona draft")

        # Clamp to the temperature range the persona form's slider supports (0.0-1.5).
        draft.temperature = max(0.0, min(1.5, draft.temperature))
        return draft
