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
        """
        async with async_session_maker() as session:
            # 1. Load the conversation details
            conversation = await session.get(Conversation, conversation_id)
            if not conversation:
                return

            # 2. Query all messages chronologically
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

            # 3. Fetch previous narrative summary if any exists
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

            # 4. Format messages for summarization prompt
            formatted_history = ""
            for msg in unsummarized:
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
                async with httpx.AsyncClient(timeout=120.0) as client:
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

                # 5. Add the new narrative summary to memories table
                new_summary_mem = Memory(
                    conversation_id=conversation_id,
                    persona_id=conversation.persona_id,
                    memory_type="summary",
                    content=result.summary,
                    importance_score=0.5,
                )
                session.add(new_summary_mem)

                # 6. Add individual facts with vector embeddings to memories table
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

                # 7. Update conversation watermark to the last message of the block
                conversation.last_summarized_message_id = unsummarized[-1].id
                conversation.updated_at = datetime.now(timezone.utc)
                await session.commit()
                logger.info(
                    f"Rolling summarization executed successfully for conversation: {conversation_id}"
                )
            except Exception as e:
                await session.rollback()
                # logger.exception logs the full traceback + exception type even when
                # str(e) is empty (e.g. an httpx/Ollama error with no message), which a
                # bare f"...: {e}" would swallow into a blank line.
                logger.exception(f"Rolling summarization failed: {e!r}")
