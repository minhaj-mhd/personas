import logging
import httpx
from app.config import settings

logger = logging.getLogger(__name__)


class EmbeddingsService:
    def __init__(self):
        self.base_url = settings.OLLAMA_BASE_URL.rstrip("/")
        self.model = settings.OLLAMA_EMBED_MODEL

    async def _embed(self, inputs: list[str]) -> list[list[float]]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self.base_url}/api/embed",
                json={"model": self.model, "input": inputs},
            )
            resp.raise_for_status()
            return resp.json()["embeddings"]

    async def embed_text(self, text: str) -> list[float]:
        """
        Generates a 768-dimension vector embedding for a single text.
        """
        try:
            return (await self._embed([text]))[0]
        except Exception as e:
            logger.error(f"Error generating text embedding: {e}")
            raise

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """
        Generates 768-dimension vector embeddings for a list of texts in batch.
        """
        if not texts:
            return []
        try:
            return await self._embed(texts)
        except Exception as e:
            logger.error(f"Error generating batch text embeddings: {e}")
            raise
