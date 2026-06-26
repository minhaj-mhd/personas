"""One-time data fix: replace dead Google Cloud TTS voice names on existing personas
with valid Gemini Live prebuilt voices. Non-destructive (UPDATE by name) so it does
NOT cascade-delete conversations the way re-seeding would. Mirrors app/seeds/personas.py.
"""
import asyncio
from sqlalchemy import select
from app.db import async_session_maker
from app.models.persona import Persona

VOICE_BY_NAME = {
    "Alistair": "Charon",
    "Elena": "Aoede",
    "Professor Clara": "Zephyr",
    "Gideon": "Fenrir",
    "Marcus": "Orus",
    "Julian": "Puck",
    "Dr. Seraphina": "Leda",
}


async def main():
    async with async_session_maker() as session:
        personas = (await session.execute(select(Persona))).scalars().all()
        changed = 0
        for p in personas:
            new_voice = VOICE_BY_NAME.get(p.name)
            if new_voice and p.voice != new_voice:
                print(f"  {p.name!r}: {p.voice!r} -> {new_voice!r}")
                p.voice = new_voice
                changed += 1
        await session.commit()
        print(f"updated {changed} personas.")


if __name__ == "__main__":
    asyncio.run(main())
