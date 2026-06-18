import logging
from typing import AsyncGenerator, List
from google import genai
from google.genai import types
from app.config import settings

logger = logging.getLogger(__name__)


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
