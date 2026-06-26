import asyncio
from sqlalchemy import select
from app.db import async_session_maker
from app.models.memory import Memory
from app.services.embeddings import EmbeddingsService

BATCH = 32

async def main():
    svc = EmbeddingsService()
    async with async_session_maker() as session:
        rows = (await session.execute(
            select(Memory).where(Memory.embedding.is_not(None))
        )).scalars().all()
        print(f"re-embedding {len(rows)} memories...")
        for i in range(0, len(rows), BATCH):
            chunk = rows[i:i + BATCH]
            embs = await svc.embed_texts([m.content for m in chunk])
            for m, e in zip(chunk, embs):
                m.embedding = e
        await session.commit()
        print("done.")

if __name__ == "__main__":
    asyncio.run(main())
