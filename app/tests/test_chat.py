import uuid
import asyncio
import pytest
import pytest_asyncio
from unittest.mock import patch
from httpx import AsyncClient, ASGITransport
from fastapi import WebSocketDisconnect

from app.db import async_session_maker
from app.main import app
from app.models import Persona, Conversation, Message
from app.api.voice_ws import chat_websocket
from app.services.gemini import GeminiService

@pytest_asyncio.fixture
async def db_session():
    async with async_session_maker() as session:
        yield session

async def clean_database(session):
    from sqlalchemy import delete
    try:
        await session.execute(delete(Message))
        await session.execute(delete(Conversation))
        await session.execute(delete(Persona).where(Persona.is_builtin == False))
        await session.commit()
    except Exception:
        await session.rollback()

class MockWebSocket:
    def __init__(self):
        self.sent_messages = []
        self.accepted = False
        self.closed = False
        self.receive_queue = asyncio.Queue()

    async def accept(self):
        self.accepted = True

    async def send_json(self, data):
        self.sent_messages.append(data)

    async def receive_json(self):
        if self.receive_queue.empty():
            await asyncio.sleep(0.5)
            raise WebSocketDisconnect()
        return await self.receive_queue.get()

    async def close(self):
        self.closed = True

@pytest.mark.asyncio
async def test_create_and_delete_conversation(db_session):
    try:
        # 1. Create a persona
        persona = Persona(
            name="Test Chat Bot",
            system_prompt="You are a helper bot.",
            is_builtin=False
        )
        db_session.add(persona)
        await db_session.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            # 2. Create conversation via API
            payload = {"persona_id": str(persona.id), "title": "My Test Session"}
            response = await ac.post("/api/conversations", json=payload)
            assert response.status_code == 201
            data = response.json()
            conv_id = data["id"]
            assert data["title"] == "My Test Session"
            assert data["persona_id"] == str(persona.id)

            # 3. List conversations
            list_resp = await ac.get(f"/api/conversations?persona_id={persona.id}")
            assert list_resp.status_code == 200
            list_data = list_resp.json()
            assert len(list_data) == 1
            assert list_data[0]["id"] == conv_id

            # 4. Get conversation messages (should be empty initially)
            msg_resp = await ac.get(f"/api/conversations/{conv_id}/messages")
            assert msg_resp.status_code == 200
            assert len(msg_resp.json()) == 0

            # 5. Delete conversation
            del_resp = await ac.delete(f"/api/conversations/{conv_id}")
            assert del_resp.status_code == 204

            # 6. Verify deleted
            get_resp = await ac.get(f"/api/conversations/{conv_id}")
            assert get_resp.status_code == 404
    finally:
        await clean_database(db_session)

@pytest.mark.asyncio
async def test_websocket_chat_streaming(db_session):
    try:
        # 1. Create persona and conversation
        persona = Persona(
            name="Debater Bot",
            system_prompt="You love arguments.",
            temperature=0.9,
            is_builtin=False
        )
        db_session.add(persona)
        await db_session.commit()

        conv = Conversation(
            persona_id=persona.id,
            title="Debate Session"
        )
        db_session.add(conv)
        await db_session.commit()

        # Mock GeminiService
        captured_calls = []

        async def mock_generate_chat_stream(self, system_instruction, chat_history, user_message, temperature=0.8):
            captured_calls.append({
                "system_instruction": system_instruction,
                "chat_history": chat_history,
                "user_message": user_message,
                "temperature": temperature
            })
            yield "Argue"
            yield " "
            yield "more"

        # Use patch to mock GeminiService.generate_chat_stream
        with patch.object(GeminiService, "generate_chat_stream", mock_generate_chat_stream):
            # Setup WebSocket
            mock_ws = MockWebSocket()
            
            # Push a user message to receive queue
            await mock_ws.receive_queue.put({
                "type": "user_message",
                "text": "Why is sky blue?"
            })

            # Call the websocket handler
            await chat_websocket(mock_ws, conv.id)

            # Assertions on connection and messages sent to client
            assert mock_ws.accepted is True
            
            tokens = [msg["delta"] for msg in mock_ws.sent_messages if msg.get("type") == "token"]
            assert tokens == ["Argue", " ", "more"]

            completes = [msg for msg in mock_ws.sent_messages if msg.get("type") == "message_complete"]
            assert len(completes) == 1
            assert completes[0]["text"] == "Argue more"

            # Check database records
            from sqlalchemy import select
            stmt = select(Message).where(Message.conversation_id == conv.id).order_by(Message.created_at.asc())
            res = await db_session.execute(stmt)
            messages = res.scalars().all()
            assert len(messages) == 2
            assert messages[0].role == "user"
            assert messages[0].content == "Why is sky blue?"
            assert messages[1].role == "assistant"
            assert messages[1].content == "Argue more"

            # Verify Gemini was invoked with correct parameters
            assert len(captured_calls) == 1
            assert captured_calls[0]["system_instruction"] == "You love arguments."
            assert captured_calls[0]["user_message"] == "Why is sky blue?"
            assert captured_calls[0]["temperature"] == 0.9

    finally:
        await clean_database(db_session)
