import asyncio
import logging
import httpx
from app.config import settings

logger = logging.getLogger(__name__)


class EmbeddingsService:
    # Ollama transiently 400s on the first request after it unloads the model
    # (cold-start runner race), so bound request size and retry with backoff.
    BATCH_SIZE = 64
    MAX_ATTEMPTS = 3

    def __init__(self):
        self.base_url = settings.OLLAMA_BASE_URL.rstrip("/")
        self.model = settings.OLLAMA_EMBED_MODEL

    async def _embed(self, inputs: list[str]) -> list[list[float]]:
        embeddings: list[list[float]] = []
        async with httpx.AsyncClient(timeout=60.0) as client:
            for start in range(0, len(inputs), self.BATCH_SIZE):
                batch = inputs[start : start + self.BATCH_SIZE]
                for attempt in range(1, self.MAX_ATTEMPTS + 1):
                    try:
                        resp = await client.post(
                            f"{self.base_url}/api/embed",
                            json={"model": self.model, "input": batch},
                        )
                        resp.raise_for_status()
                        embeddings.extend(resp.json()["embeddings"])
                        break
                    except (httpx.HTTPStatusError, httpx.TransportError) as e:
                        if attempt == self.MAX_ATTEMPTS:
                            raise
                        logger.warning(
                            f"Embed batch failed (attempt {attempt}/{self.MAX_ATTEMPTS}), retrying: {e}"
                        )
                        await asyncio.sleep(attempt)
        return embeddings

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
