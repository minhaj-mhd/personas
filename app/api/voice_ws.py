import uuid
import asyncio
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.db import async_session_maker
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.persona import Persona
from app.services.gemini import GeminiService
from google.genai import types
from app.config import settings
from app.services.memory import MemoryService
from app.services.prompt_builder import inject_memories_into_prompt
from app.services.summarizer import SummarizerService

logger = logging.getLogger(__name__)
router = APIRouter(tags=["WebSocket Chat"])


@router.websocket("/ws/chat/{conversation_id}")
async def chat_websocket(websocket: WebSocket, conversation_id: uuid.UUID):
    await websocket.accept()

    # We will hold the active generation task so we can cancel it on interrupt
    active_generation_task = None

    # Load conversation and persona details to check if they exist
    async with async_session_maker() as db:
        stmt = select(Conversation).where(Conversation.id == conversation_id)
        res = await db.execute(stmt)
        conversation = res.scalar_one_or_none()
        if not conversation:
            await websocket.send_json(
                {"type": "error", "detail": "Conversation not found"}
            )
            await websocket.close()
            return

        persona_stmt = select(Persona).where(Persona.id == conversation.persona_id)
        persona_res = await db.execute(persona_stmt)
        persona = persona_res.scalar_one_or_none()
        if not persona:
            await websocket.send_json({"type": "error", "detail": "Persona not found"})
            await websocket.close()
            return

        system_prompt = persona.system_prompt
        temperature = persona.temperature

    gemini_service = GeminiService()

    async def stream_response(user_text: str):
        nonlocal active_generation_task
        full_reply = ""
        try:
            # 1. Save user message to database
            async with async_session_maker() as session:
                conv = await session.get(Conversation, conversation_id)
                user_msg = Message(
                    conversation_id=conversation_id, role="user", content=user_text
                )
                session.add(user_msg)
                if conv:
                    conv.updated_at = datetime.now(timezone.utc)
                await session.commit()
                user_msg_id = user_msg.id

            # 2. Fetch recent conversation history
            async with async_session_maker() as session:
                history_stmt = (
                    select(Message)
                    .where(Message.conversation_id == conversation_id)
                    .where(Message.id != user_msg_id)
                    .order_by(Message.created_at.desc())
                    .limit(settings.SHORT_TERM_MESSAGES - 1)
                )
                history_res = await session.execute(history_stmt)
                history_msgs = list(reversed(history_res.scalars().all()))

            # Retrieve RAG context (narrative summaries and semantic document chunks)
            memory_service = MemoryService()
            retrieved_memories = await memory_service.retrieve_context(
                persona_id=persona.id,
                conversation_id=conversation_id,
                user_text=user_text,
            )
            injected_prompt = inject_memories_into_prompt(
                system_prompt, retrieved_memories
            )

            # Map messages to google-genai Content format
            gemini_history = []
            for msg in history_msgs:
                role = "model" if msg.role == "assistant" else "user"
                gemini_history.append(
                    types.Content(
                        role=role, parts=[types.Part.from_text(text=msg.content)]
                    )
                )

            # 3. Request and stream response from Gemini service
            generator = gemini_service.generate_chat_stream(
                system_instruction=injected_prompt,
                chat_history=gemini_history,
                user_message=user_text,
                temperature=temperature,
            )

            async for token in generator:
                full_reply += token
                await websocket.send_json({"type": "token", "delta": token})

            # 4. Save the completed assistant response to database
            async with async_session_maker() as session:
                conv = await session.get(Conversation, conversation_id)
                assistant_msg = Message(
                    conversation_id=conversation_id,
                    role="assistant",
                    content=full_reply,
                )
                session.add(assistant_msg)
                if conv:
                    conv.updated_at = datetime.now(timezone.utc)
                await session.commit()
                assistant_msg_id = assistant_msg.id

            # 5. Broadcast message complete event
            await websocket.send_json(
                {
                    "type": "message_complete",
                    "message_id": str(assistant_msg_id),
                    "text": full_reply,
                }
            )

            # 6. Trigger rolling summarization asynchronously
            summarizer_service = SummarizerService()
            asyncio.create_task(summarizer_service.maybe_summarize(conversation_id))

        except asyncio.CancelledError:
            logger.info("Generation task was cancelled.")
            # Persist whatever was generated before the interruption
            if full_reply:
                async with async_session_maker() as session:
                    conv = await session.get(Conversation, conversation_id)
                    assistant_msg = Message(
                        conversation_id=conversation_id,
                        role="assistant",
                        content=full_reply + " [interrupted]",
                    )
                    session.add(assistant_msg)
                    if conv:
                        conv.updated_at = datetime.now(timezone.utc)
                    await session.commit()
            await websocket.send_json({"type": "interrupted", "text": full_reply})
        except Exception as e:
            logger.error(f"Error in streaming generation: {e}")
            await websocket.send_json({"type": "error", "detail": str(e)})
        finally:
            active_generation_task = None

    try:
        while True:
            # Main WebSocket receive loop
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "user_message":
                # Cancel any existing active task if running
                if active_generation_task and not active_generation_task.done():
                    active_generation_task.cancel()

                user_text = data.get("text", "")
                active_generation_task = asyncio.create_task(stream_response(user_text))

            elif msg_type == "interrupt":
                if active_generation_task and not active_generation_task.done():
                    active_generation_task.cancel()
                    await websocket.send_json(
                        {"type": "info", "detail": "Generation interrupted by user."}
                    )

    except WebSocketDisconnect:
        logger.info(
            f"WebSocket client disconnected from conversation: {conversation_id}"
        )
        if active_generation_task and not active_generation_task.done():
            active_generation_task.cancel()
            try:
                await active_generation_task
            except asyncio.CancelledError:
                pass
    except Exception as e:
        logger.error(f"WebSocket exception: {e}")
        if active_generation_task and not active_generation_task.done():
            active_generation_task.cancel()
            try:
                await active_generation_task
            except asyncio.CancelledError:
                pass
