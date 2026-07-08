from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select, delete

from app.db import async_session_maker
from app.main import app
from app.models.persona import Persona
from app.schemas.personas import PersonaDraft


@pytest_asyncio.fixture
async def db_session():
    """
    Yields a clean database session and closes it at the end of the test.
    """
    async with async_session_maker() as session:
        yield session


async def clean_custom_personas(session):
    """
    Helper function to delete all custom (non-builtin) personas from the database.
    Runs inside the active test's event loop.
    """
    try:
        await session.execute(delete(Persona).where(Persona.is_builtin == False))
        await session.commit()
    except Exception:
        await session.rollback()


@pytest.mark.asyncio
async def test_create_persona(db_session):
    """
    Test creating a custom persona, validating system prompt assembly.
    """
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            payload = {
                "name": "Test Bot",
                "description": "A helper for testing",
                "personality_traits": ["helpful", "polite"],
                "speaking_style": "formal",
                "goals": "answer queries",
                "constraints": "none",
                "domain_expertise": "testing",
                "voice": "en-US-Neural2-F",
                "temperature": 0.5,
            }
            response = await ac.post("/api/personas", json=payload)

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test Bot"
        assert data["is_builtin"] is False
        assert "PERSONALITY: helpful, polite" in data["system_prompt"]

        # Verify it exists in database using a fresh query
        stmt = select(Persona).where(Persona.name == "Test Bot")
        result = await db_session.execute(stmt)
        persona = result.scalar_one_or_none()
        assert persona is not None
        assert persona.temperature == 0.5
    finally:
        await clean_custom_personas(db_session)


@pytest.mark.asyncio
async def test_list_personas(db_session):
    """
    Test listing personas, ensuring our custom ones are returned.
    """
    try:
        mock_persona = Persona(
            name="Mock Bot", system_prompt="You are a mock", is_builtin=False
        )
        db_session.add(mock_persona)
        await db_session.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/api/personas")

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        names = [p["name"] for p in data]
        assert "Mock Bot" in names
    finally:
        await clean_custom_personas(db_session)


@pytest.mark.asyncio
async def test_restrict_builtin_modification(db_session):
    """
    Verify updates or deletions to built-in personas are blocked.
    """
    try:
        builtin_persona = Persona(
            name="Seeded Bot", system_prompt="You are seeded", is_builtin=True
        )
        db_session.add(builtin_persona)
        await db_session.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            # Try updating
            update_resp = await ac.put(
                f"/api/personas/{builtin_persona.id}", json={"name": "New Name"}
            )
            assert update_resp.status_code == 400
            assert "Built-in" in update_resp.json()["detail"]

            # Try deleting
            delete_resp = await ac.delete(f"/api/personas/{builtin_persona.id}")
            assert delete_resp.status_code == 400
            assert "Built-in" in delete_resp.json()["detail"]

        # Remove the mock builtin manually since clean_custom_personas only targets non-builtins
        await db_session.delete(builtin_persona)
        await db_session.commit()
    finally:
        await clean_custom_personas(db_session)


@pytest.mark.asyncio
async def test_update_custom_persona(db_session):
    """
    Test updating an existing custom persona, verifying that fields change and the prompt rebuilds.
    """
    try:
        persona = Persona(
            name="Old Name",
            description="Old bio",
            system_prompt="You are Old",
            personality_traits=["sad"],
            is_builtin=False,
        )
        db_session.add(persona)
        await db_session.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.put(
                f"/api/personas/{persona.id}",
                json={"name": "New Name", "personality_traits": "happy, cheerful"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "New Name"
        assert "PERSONALITY: happy, cheerful" in data["system_prompt"]
    finally:
        await clean_custom_personas(db_session)


@pytest.mark.asyncio
async def test_draft_persona_returns_structured_fields():
    """
    The AI draft endpoint returns structured persona fields (Gemini is mocked so no
    real API call is made) and persists nothing.
    """
    fake_draft = PersonaDraft(
        name="Sage",
        description="a calm meditation guide for stressed beginners",
        personality_traits=["calm", "gentle", "grounding"],
        speaking_style="Slow, soft, with long pauses and short sentences.",
        goals="Lead short breathing exercises and help the user relax.",
        constraints="Not a medical professional; never diagnose or treat.",
        domain_expertise="Mindfulness, breathwork, guided meditation.",
        voice="Leda",
        temperature=0.85,
    )

    transport = ASGITransport(app=app)
    with patch(
        "app.api.personas.GeminiService.draft_persona",
        new=AsyncMock(return_value=fake_draft),
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                "/api/personas/draft",
                json={"brief": "A calm meditation guide for beginners"},
            )

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Sage"
    assert data["voice"] == "Leda"
    assert data["personality_traits"] == ["calm", "gentle", "grounding"]
    assert data["temperature"] == 0.85


@pytest.mark.asyncio
async def test_draft_persona_rejects_empty_brief():
    """A blank/too-short brief is rejected by validation before any Gemini call."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post("/api/personas/draft", json={"brief": ""})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_delete_custom_persona(db_session):
    """
    Test deleting a custom persona.
    """
    try:
        persona = Persona(
            name="To Delete", system_prompt="You will die", is_builtin=False
        )
        db_session.add(persona)
        await db_session.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.delete(f"/api/personas/{persona.id}")

        assert response.status_code == 204

        # Check that it's no longer present
        stmt = select(Persona).where(Persona.id == persona.id)
        result = await db_session.execute(stmt)
        assert result.scalar_one_or_none() is None
    finally:
        await clean_custom_personas(db_session)
