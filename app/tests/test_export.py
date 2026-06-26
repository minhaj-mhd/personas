import pytest
import pytest_asyncio
from datetime import datetime, timezone
from httpx import AsyncClient, ASGITransport

from app.db import async_session_maker
from app.main import app
from app.models import Persona, Conversation, Message
from app.services.export import render_conversation_markdown, safe_filename


@pytest_asyncio.fixture
async def db_session():
    async with async_session_maker() as session:
        yield session


async def surgical_cleanup(session, *, conversation_id=None, persona_id=None):
    """Delete ONLY the rows this test created (cascades messages/memories) — never a mass wipe.
    The dev DB holds real conversation history; tests must not touch it (see AGENTS.md)."""
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


def test_safe_filename():
    assert safe_filename("My Chat / Session!") == "My_Chat_Session"
    assert safe_filename(None) == "conversation"
    assert safe_filename("") == "conversation"
    assert len(safe_filename("x" * 200)) == 60


def test_render_conversation_markdown_pure():
    class Obj:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    conv = Obj(title="Trip Planning", created_at=datetime(2026, 6, 25, 14, 30))
    persona = Obj(name="Professor Clara", description="a friendly tutor")
    messages = [
        Obj(role="user", content="Hello there", created_at=datetime(2026, 6, 25, 14, 31)),
        Obj(role="assistant", content="Hi! How can I help?", created_at=datetime(2026, 6, 25, 14, 31)),
    ]

    md = render_conversation_markdown(conv, persona, messages)
    assert md.startswith("# Trip Planning")
    assert "**Persona:** Professor Clara" in md
    assert "**Messages:** 2" in md
    assert "### You" in md
    assert "### Professor Clara" in md
    assert "Hello there" in md
    assert "Hi! How can I help?" in md


@pytest.mark.asyncio
async def test_export_endpoint_markdown(db_session):
    try:
        persona = Persona(
            name="Export Bot",
            description="exports things",
            system_prompt="You export.",
            is_builtin=False,
        )
        db_session.add(persona)
        await db_session.commit()

        conv = Conversation(persona_id=persona.id, title="Export Session")
        db_session.add(conv)
        await db_session.commit()

        db_session.add_all(
            [
                Message(
                    conversation_id=conv.id,
                    role="user",
                    content="What is RAG?",
                    created_at=datetime.now(timezone.utc),
                ),
                Message(
                    conversation_id=conv.id,
                    role="assistant",
                    content="Retrieval-Augmented Generation.",
                    created_at=datetime.now(timezone.utc),
                ),
            ]
        )
        await db_session.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get(f"/api/conversations/{conv.id}/export?format=md")
            assert resp.status_code == 200
            assert "text/markdown" in resp.headers["content-type"]
            assert "attachment" in resp.headers["content-disposition"]
            assert ".md" in resp.headers["content-disposition"]
            body = resp.text
            assert "# Export Session" in body
            assert "Export Bot" in body
            assert "What is RAG?" in body
            assert "Retrieval-Augmented Generation." in body

            # Unsupported format -> 400
            bad = await ac.get(f"/api/conversations/{conv.id}/export?format=pdf")
            assert bad.status_code == 400

            # Missing conversation -> 404
            import uuid

            missing = await ac.get(f"/api/conversations/{uuid.uuid4()}/export?format=md")
            assert missing.status_code == 404
    finally:
        await surgical_cleanup(db_session, conversation_id=conv.id, persona_id=persona.id)
