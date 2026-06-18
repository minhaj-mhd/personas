import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from google.genai import types

from app.db import async_session_maker
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.persona import Persona
from app.config import settings
from app.services.memory import MemoryService
from app.services.prompt_builder import format_retrieved_memories
from app.services.gemini_live import (
    GeminiLiveService,
    resolve_voice,
    build_system_instruction,
    build_live_config,
)
from app.services.summarizer import SummarizerService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Live WebSocket Chat"])


@router.websocket("/ws/live/{conversation_id}")
async def live_websocket(websocket: WebSocket, conversation_id: uuid.UUID):
    await websocket.accept()

    # 1. Load conversation & persona
    async with async_session_maker() as db:
        conv = await db.get(Conversation, conversation_id)
        if not conv:
            await websocket.send_json(
                {"type": "error", "detail": "Conversation not found"}
            )
            await websocket.close()
            return

        persona = await db.get(Persona, conv.persona_id)
        if not persona:
            await websocket.send_json({"type": "error", "detail": "Persona not found"})
            await websocket.close()
            return

        system_prompt = persona.system_prompt
        temperature = persona.temperature
        persona_voice = persona.voice
        persona_id = persona.id

    # 2. Get preamble memories
    memory_service = MemoryService()
    preamble_mems = await memory_service.get_preamble_memories(
        persona_id, conversation_id
    )
    memory_block = format_retrieved_memories(preamble_mems)

    # 3. Build config
    voice = resolve_voice(persona_voice)
    sys_instruct = build_system_instruction(system_prompt, memory_block)
    enable_search = getattr(settings, "LIVE_ENABLE_SEARCH", False)

    config = build_live_config(
        system_instruction=sys_instruct,
        voice=voice,
        temperature=temperature,
        enable_search=enable_search,
    )

    gemini_live = GeminiLiveService()

    # Shared state for transcripts
    current_input_text = ""
    current_output_text = ""
    was_interrupted = False

    async def persist_turn(input_text: str, output_text: str, interrupted: bool):
        if not input_text and not output_text:
            return

        async with async_session_maker() as session:
            conv_obj = await session.get(Conversation, conversation_id)
            if input_text:
                session.add(
                    Message(
                        conversation_id=conversation_id, role="user", content=input_text
                    )
                )

            if output_text:
                final_out = (
                    output_text + " [interrupted]" if interrupted else output_text
                )
                session.add(
                    Message(
                        conversation_id=conversation_id,
                        role="assistant",
                        content=final_out,
                    )
                )

            if conv_obj and (input_text or output_text):
                conv_obj.updated_at = datetime.now(timezone.utc)
            await session.commit()

    try:
        async with gemini_live.connect(config) as session:
            # Send ready event
            await websocket.send_json(
                {"type": "ready", "voice": voice, "model": settings.LIVE_MODEL}
            )

            async def handle_tool_call(function_calls):
                responses = []
                for fc in function_calls:
                    if fc.name == "recall_memory":
                        query = ""
                        if isinstance(fc.args, dict):
                            query = fc.args.get("query", "")
                        else:
                            query = getattr(fc.args, "query", "")

                        if query:
                            try:
                                retrieved = await memory_service.retrieve_context(
                                    persona_id, conversation_id, query
                                )
                                fmt_result = format_retrieved_memories(retrieved)

                                # Compatibility check for FunctionResponseScheduling
                                sched = getattr(
                                    types, "FunctionResponseScheduling", None
                                )
                                kwargs = {
                                    "id": fc.id,
                                    "name": "recall_memory",
                                    "response": {"result": fmt_result},
                                }
                                if sched and hasattr(sched, "WHEN_IDLE"):
                                    kwargs["scheduling"] = sched.WHEN_IDLE

                                responses.append(types.FunctionResponse(**kwargs))
                            except Exception as e:
                                logger.error(f"Error in tool call: {e}")

                if responses:
                    try:
                        await session.send_tool_response(function_responses=responses)
                    except Exception as e:
                        logger.error(f"Error sending tool response: {e}")

            async def downlink():
                nonlocal current_input_text, current_output_text, was_interrupted
                async for resp in session.receive():
                    if getattr(resp, "go_away", None):
                        await websocket.send_json({"type": "go_away"})

                    # Handle raw audio bytes
                    if getattr(resp, "data", None):
                        await websocket.send_bytes(resp.data)

                    # Accumulate chunked output text
                    if getattr(resp, "text", None):
                        current_output_text += resp.text

                    sc = getattr(resp, "server_content", None)
                    if sc:
                        if getattr(sc, "interrupted", False):
                            was_interrupted = True
                            await websocket.send_json({"type": "interrupted"})

                        in_t = getattr(sc, "input_transcription", None)
                        if in_t:
                            text_val = getattr(in_t, "text", "")
                            if text_val:
                                current_input_text = text_val
                            await websocket.send_json(
                                {
                                    "type": "input_transcript",
                                    "text": text_val,
                                    "final": bool(getattr(in_t, "finished", False)),
                                }
                            )

                        out_t = getattr(sc, "output_transcription", None)
                        if out_t:
                            out_val = getattr(out_t, "text", "")
                            # Some SDK variants give the full text in output_transcription,
                            # we update current_output_text if provided, otherwise trust resp.text.
                            if out_val:
                                current_output_text = out_val
                            await websocket.send_json(
                                {
                                    "type": "output_transcript",
                                    "text": getattr(out_t, "text", current_output_text),
                                    "final": bool(getattr(out_t, "finished", False)),
                                }
                            )
                        elif getattr(resp, "text", None):
                            # fallback: emit partial output_transcript if no out_t block exists
                            await websocket.send_json(
                                {
                                    "type": "output_transcript",
                                    "text": current_output_text,
                                    "final": False,
                                }
                            )

                        if getattr(sc, "turn_complete", False):
                            await websocket.send_json({"type": "turn_complete"})
                            # Persist and reset turn state
                            await persist_turn(
                                current_input_text, current_output_text, was_interrupted
                            )
                            current_input_text = ""
                            current_output_text = ""
                            was_interrupted = False

                    # Handle Tools
                    tc = getattr(resp, "tool_call", None)
                    if tc and getattr(tc, "function_calls", None):
                        asyncio.create_task(handle_tool_call(tc.function_calls))

            async def uplink():
                while True:
                    message = await websocket.receive()
                    # Client sends binary mic frames
                    if "bytes" in message:
                        await session.send_realtime_input(
                            audio=types.Blob(
                                data=message["bytes"], mime_type="audio/pcm;rate=16000"
                            )
                        )
                    elif "text" in message:
                        try:
                            data = json.loads(message["text"])
                            if data.get("type") in ["stop", "audio_end"]:
                                # Close the session
                                break
                        except json.JSONDecodeError:
                            pass

            # Run tasks concurrently
            down_task = asyncio.create_task(downlink())
            up_task = asyncio.create_task(uplink())

            done, pending = await asyncio.wait(
                [down_task, up_task], return_when=asyncio.FIRST_COMPLETED
            )
            for p in pending:
                p.cancel()

            # If any turn left un-persisted, persist it (e.g., disconnected mid-turn)
            if current_input_text or current_output_text:
                await persist_turn(
                    current_input_text, current_output_text, was_interrupted
                )

    except WebSocketDisconnect:
        logger.info(f"Live WS disconnected for {conversation_id}")
    except Exception as e:
        logger.error(f"Live WS Error: {e}")
        try:
            await websocket.send_json({"type": "error", "detail": str(e)})
        except Exception:
            pass
    finally:
        # Trigger summarizer explicitly on disconnect per §2.2
        try:
            asyncio.create_task(
                SummarizerService().maybe_summarize(conversation_id, force=True)
            )
        except Exception as e:
            logger.error(f"Error triggering summarizer on disconnect: {e}")
