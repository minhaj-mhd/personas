import pytest
import pytest_asyncio
import uuid
from datetime import datetime, timezone
from httpx import AsyncClient, ASGITransport

from app.db import async_session_maker
from app.main import app
from app.models import Persona, Conversation, Message
from app.services.search import make_snippet


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


def test_make_snippet_centers_on_query():
    content = "The capital of France is Paris and it is lovely in the spring."
    s = make_snippet(content, "Paris", radius=10)
    assert "Paris" in s
    assert s.startswith("…")  # trimmed at the front
    assert s.endswith("…")  # trimmed at the back


def test_make_snippet_no_match_returns_head():
    content = "x" * 300
    s = make_snippet(content, "zzz", radius=50)
    assert s.endswith("…")
    assert len(s) <= 101


def test_make_snippet_empty():
    assert make_snippet("", "q") == ""


@pytest.mark.asyncio
async def test_search_endpoint(db_session):
    try:
        persona = Persona(
            name="Search Bot", system_prompt="You search.", is_builtin=False
        )
        db_session.add(persona)
        await db_session.commit()

        conv = Conversation(persona_id=persona.id, title="Search Session")
        db_session.add(conv)
        await db_session.commit()

        db_session.add_all(
            [
                Message(
                    conversation_id=conv.id,
                    role="user",
                    content="Tell me about photosynthesis in plants.",
                    created_at=datetime.now(timezone.utc),
                ),
                Message(
                    conversation_id=conv.id,
                    role="assistant",
                    content="Photosynthesis converts light into energy.",
                    created_at=datetime.now(timezone.utc),
                ),
            ]
        )
        await db_session.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/api/conversations/search?q=photosynthesis")
            assert resp.status_code == 200
            data = resp.json()
            mine = [r for r in data if r["conversation_id"] == str(conv.id)]
            assert len(mine) == 1
            assert mine[0]["match_count"] == 2
            assert "photosynthesis" in mine[0]["snippet"].lower()

            # Filter by a different persona -> no hits for our conversation
            other = await ac.get(
                f"/api/conversations/search?q=photosynthesis&persona_id={uuid.uuid4()}"
            )
            assert other.status_code == 200
            assert all(r["conversation_id"] != str(conv.id) for r in other.json())

            # Empty query -> 422 (validation)
            bad = await ac.get("/api/conversations/search?q=")
            assert bad.status_code == 422
    finally:
        await surgical_cleanup(db_session, conversation_id=conv.id, persona_id=persona.id)
