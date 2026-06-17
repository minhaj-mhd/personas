import uuid
import logging
from sqlalchemy import select
from app.db import async_session_maker
from app.models.memory import Memory
from app.services.embeddings import EmbeddingsService

logger = logging.getLogger(__name__)

def chunk_text(text: str, chunk_size: int = 500, overlap: int = 100) -> list[str]:
    """
    Splits text into overlapping word-aligned chunks.
    """
    if not text:
        return []
    chunks = []
    words = text.split()
    current_chunk_words = []
    current_length = 0
    
    for word in words:
        current_chunk_words.append(word)
        current_length += len(word) + 1
        
        if current_length >= chunk_size:
            chunks.append(" ".join(current_chunk_words))
            # Create overlap
            overlap_length = 0
            overlap_words = []
            for w in reversed(current_chunk_words):
                overlap_length += len(w) + 1
                overlap_words.insert(0, w)
                if overlap_length >= overlap:
                    break
            current_chunk_words = overlap_words
            current_length = overlap_length
            
    if current_chunk_words:
        chunks.append(" ".join(current_chunk_words))
        
    return chunks

class MemoryService:
    def __init__(self):
        self.embeddings_service = EmbeddingsService()

    async def ingest_document(self, persona_id: uuid.UUID, filename: str, text: str) -> None:
        """
        Ingests a document text: chunks it, embeds each chunk, and saves to database.
        """
        chunks = chunk_text(text)
        if not chunks:
            logger.info(f"Skipped ingesting empty document: {filename}")
            return
            
        embeddings = await self.embeddings_service.embed_texts(chunks)
        
        async with async_session_maker() as session:
            for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
                memory = Memory(
                    persona_id=persona_id,
                    memory_type="document",
                    content=chunk,
                    embedding=emb,
                    metadata_={"source": filename, "chunk_index": i}
                )
                session.add(memory)
            await session.commit()
        logger.info(f"Successfully ingested document: {filename} with {len(chunks)} chunks.")

    async def retrieve_context(
        self,
        persona_id: uuid.UUID,
        conversation_id: uuid.UUID | None,
        user_text: str,
        limit: int = 5
    ) -> list[Memory]:
        """
        Retrieves relevant context (narrative summaries + semantically matched memories).
        """
        memories = []
        
        async with async_session_maker() as db:
            # 1. Always pull the latest narrative summary for the active session (if any)
            if conversation_id:
                summary_stmt = (
                    select(Memory)
                    .where(Memory.conversation_id == conversation_id)
                    .where(Memory.memory_type == "summary")
                    .order_by(Memory.created_at.desc())
                    .limit(1)
                )
                summary_res = await db.execute(summary_stmt)
                latest_summary = summary_res.scalar_one_or_none()
                if latest_summary:
                    memories.append(latest_summary)

            # 2. Embed user query and fetch semantically matching facts or document chunks
            try:
                query_embedding = await self.embeddings_service.embed_text(user_text)
                distance = Memory.embedding.cosine_distance(query_embedding)
                
                # Fetch top matching records (excluding raw summary type which is not retrieved by distance)
                stmt = (
                    select(Memory)
                    .where(Memory.persona_id == persona_id)
                    .where(Memory.memory_type != "summary")
                    .where(distance < 0.7) # Cosine similarity threshold (distance < 0.7 means similarity > 0.3)
                    .order_by(distance.asc())
                    .limit(limit)
                )
                res = await db.execute(stmt)
                matching_records = res.scalars().all()
                memories.extend(matching_records)
            except Exception as e:
                logger.error(f"Failed semantic memory retrieval: {e}")
                
        return memories
