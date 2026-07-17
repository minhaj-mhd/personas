import asyncio
import uuid
import logging
from datetime import datetime, timezone
from sqlalchemy import select
import re
import httpx
from pydantic import BaseModel
from app.db import async_session_maker
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.memory import Memory
from app.services.embeddings import EmbeddingsService
from app.config import settings

logger = logging.getLogger(__name__)


class SummaryOutput(BaseModel):
    summary: str
    facts: list[str]


class SummarizerService:
    def __init__(self):
        self.base_url = settings.OLLAMA_BASE_URL.rstrip("/")
        self.model = settings.OLLAMA_SUMMARY_MODEL
        self.embeddings_service = EmbeddingsService()

    async def maybe_summarize(
        self, conversation_id: uuid.UUID, force: bool = False
    ) -> None:
        """
        Asynchronously checks if a conversation session has enough unsummarized turns,
        updates the narrative summary, extracts facts/preferences, and embeds them.

        Processes the backlog in bounded batches (SUMMARIZE_BATCH_SIZE messages per
        Ollama call) instead of one shot: a large backlog stuffed into a single request
        reliably times out, which leaves the watermark stuck and the backlog even bigger
        on the next attempt. Each batch commits its own summary/facts/watermark update,
        so progress survives even if a later batch fails.
        """
        async with async_session_maker() as session:
            conversation = await session.get(Conversation, conversation_id)
            if not conversation:
                return

            stmt = (
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at.asc())
            )
            res = await session.execute(stmt)
            messages = res.scalars().all()
            if not messages:
                return

            # Find the watermark index
            start_idx = 0
            if conversation.last_summarized_message_id:
                for idx, msg in enumerate(messages):
                    if msg.id == conversation.last_summarized_message_id:
                        start_idx = idx + 1
                        break

            unsummarized = messages[start_idx:]
            if not force and len(unsummarized) < settings.SUMMARIZE_THRESHOLD:
                # Unsummarized block size is below threshold
                return

        batch_size = settings.SUMMARIZE_BATCH_SIZE
        max_retries = settings.SUMMARIZE_MAX_RETRIES
        offset = 0
        while offset < len(unsummarized):
            batch = unsummarized[offset : offset + batch_size]
            for attempt in range(max_retries + 1):
                if await self._summarize_batch(conversation_id, batch):
                    break
                if attempt < max_retries:
                    await asyncio.sleep(2**attempt)  # backoff before retrying the batch
            else:
                # Every attempt on this batch failed — stop rather than spin. The watermark
                # holds at the last successful batch, so a later run resumes from here.
                logger.error(
                    f"Summarization halted for {conversation_id}: a batch failed "
                    f"{max_retries + 1} attempts; {len(unsummarized) - offset} messages "
                    f"remain unsummarized."
                )
                break
            offset += len(batch)

    async def _summarize_batch(
        self, conversation_id: uuid.UUID, batch: list[Message]
    ) -> bool:
        """Summarizes one bounded batch of messages, committing its own summary/facts/
        watermark update. Returns True on success, False (after logging) on failure."""
        async with async_session_maker() as session:
            conversation = await session.get(Conversation, conversation_id)

            # Fetch previous narrative summary if any exists
            prev_summary = ""
            summary_stmt = (
                select(Memory)
                .where(Memory.conversation_id == conversation_id)
                .where(Memory.memory_type == "summary")
                .order_by(Memory.created_at.desc())
                .limit(1)
            )
            summary_res = await session.execute(summary_stmt)
            latest_summary_mem = summary_res.scalar_one_or_none()
            if latest_summary_mem:
                prev_summary = latest_summary_mem.content

            # Format messages for summarization prompt
            formatted_history = ""
            for msg in batch:
                formatted_history += f"{msg.role}: {msg.content}\n"

            prompt = "You are a rolling conversation summarizer and fact extractor.\n"
            if prev_summary:
                prompt += f"PREVIOUS NARRATIVE SUMMARY:\n{prev_summary}\n\n"
            prompt += f"NEW UNCONSOLIDATED MESSAGES:\n{formatted_history}\n\n"
            prompt += (
                "Task: Update the narrative summary to incorporate the new messages. "
                "Also, extract any new discrete user facts, preferences, or goals from the new messages. "
                "Return the results in the requested JSON structure."
            )

            try:
                # Request structured JSON response from Ollama
                async with httpx.AsyncClient(timeout=settings.SUMMARIZE_TIMEOUT) as client:
                    resp = await client.post(
                        f"{self.base_url}/api/chat",
                        json={
                            "model": self.model,
                            "messages": [{"role": "user", "content": prompt}],
                            "format": SummaryOutput.model_json_schema(),
                            "stream": False,
                            "think": False,
                            "options": {"temperature": 0.2},
                        },
                    )
                    resp.raise_for_status()
                    content = resp.json()["message"]["content"]

                # Safety net if an Ollama version ignores think:false
                content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
                result = SummaryOutput.model_validate_json(content)

                # Add the new narrative summary to memories table
                new_summary_mem = Memory(
                    conversation_id=conversation_id,
                    persona_id=conversation.persona_id,
                    memory_type="summary",
                    content=result.summary,
                    importance_score=0.5,
                )
                session.add(new_summary_mem)

                # Add individual facts with vector embeddings to memories table
                if result.facts:
                    embeddings = await self.embeddings_service.embed_texts(result.facts)
                    for fact, emb in zip(result.facts, embeddings):
                        fact_mem = Memory(
                            conversation_id=conversation_id,
                            persona_id=conversation.persona_id,
                            memory_type="fact",
                            content=fact,
                            embedding=emb,
                            importance_score=0.8,
                        )
                        session.add(fact_mem)

                # Update conversation watermark to the last message of this batch
                conversation.last_summarized_message_id = batch[-1].id
                conversation.updated_at = datetime.now(timezone.utc)
                await session.commit()
                logger.info(
                    f"Rolling summarization executed successfully for conversation: "
                    f"{conversation_id} ({len(batch)} messages)"
                )
                return True
            except Exception as e:
                await session.rollback()
                # logger.exception logs the full traceback + exception type even when
                # str(e) is empty (e.g. an httpx/Ollama error with no message), which a
                # bare f"...: {e}" would swallow into a blank line.
                logger.exception(f"Rolling summarization failed: {e!r}")
                return False
