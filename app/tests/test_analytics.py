import pytest
import pytest_asyncio
from datetime import datetime, timezone
from httpx import AsyncClient, ASGITransport

from app.db import async_session_maker
from app.main import app
from app.models import Persona, Conversation, Message
from app.services.analytics import estimate_speaking_minutes


@pytest_asyncio.fixture
async def db_session():
    async with async_session_maker() as session:
        yield session


async def surgical_cleanup(session, *, conversation_id=None, persona_id=None):
    from sqlalchemy import delete

    try:
        if conversation_id is not None:
            await session.execute(
                delete(Conversation).where(Conversation.id == conversation_id)
            )
        if persona_id is not None:
            await session.execute(delete(Persona).where(Persona.id == persona_id))
        await session.commit()
    except Exception:
        await session.rollback()


def test_estimate_speaking_minutes():
    assert estimate_speaking_minutes(0) == 0.0
    assert estimate_speaking_minutes(-5) == 0.0
    # 1500 chars -> 300 words -> 2.0 min at 150 wpm
    assert estimate_speaking_minutes(1500) == 2.0


@pytest.mark.asyncio
async def test_analytics_endpoint(db_session):
    try:
        persona = Persona(
            name="Stats Bot", system_prompt="You count.", is_builtin=False
        )
        db_session.add(persona)
        await db_session.commit()

        conv = Conversation(persona_id=persona.id, title="Stats Session")
        db_session.add(conv)
        await db_session.commit()

        db_session.add_all(
            [
                Message(conversation_id=conv.id, role="user", content="hi there", created_at=datetime.now(timezone.utc)),
                Message(conversation_id=conv.id, role="assistant", content="hello back", created_at=datetime.now(timezone.utc)),
                Message(conversation_id=conv.id, role="user", content="bye", created_at=datetime.now(timezone.utc)),
            ]
        )
        await db_session.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/api/analytics")
            assert resp.status_code == 200
            data = resp.json()
            assert data["totals"]["messages"] >= 3
            mine = [p for p in data["per_persona"] if p["persona_id"] == str(persona.id)]
            assert len(mine) == 1
            row = mine[0]
            assert row["conversations"] == 1
            assert row["messages"] == 3
            assert row["user_messages"] == 2
            assert row["assistant_messages"] == 1
            assert row["est_speaking_minutes"] >= 0.0
            assert row["last_active"] is not None
    finally:
        await surgical_cleanup(db_session, conversation_id=conv.id, persona_id=persona.id)
