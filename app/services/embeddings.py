import logging
from google import genai
from app.config import settings

logger = logging.getLogger(__name__)

class EmbeddingsService:
    def __init__(self):
        # Initialize Google GenAI client
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)

    async def embed_text(self, text: str) -> list[float]:
        """
        Generates a 768-dimension vector embedding for a single text.
        """
        try:
            response = await self.client.aio.models.embed_content(
                model=settings.EMBED_MODEL,
                contents=text
            )
            return response.embeddings[0].values
        except Exception as e:
            logger.error(f"Error generating text embedding: {e}")
            raise e

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """
        Generates 768-dimension vector embeddings for a list of texts in batch.
        """
        if not texts:
            return []
        try:
            response = await self.client.aio.models.embed_content(
                model=settings.EMBED_MODEL,
                contents=texts
            )
            return [e.values for e in response.embeddings]
        except Exception as e:
            logger.error(f"Error generating batch text embeddings: {e}")
            raise e
