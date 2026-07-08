import array
import asyncio
import contextlib
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
    prime_session_with_images,
    send_image_frame,
    recoverable_disconnect,
)
from app.services.assets import get_scope_images
from app.services.mcp.client import build_sheets_provider
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

    gemini_live = GeminiLiveService()

    # MCP (e.g. Google Sheets) tool provider — opened below only if enabled in settings.
    mcp_provider = None
    mcp_stack = None

    # Shared state for transcripts
    current_input_text = ""
    current_output_text = ""
    was_interrupted = False

    # Session resumption: the latest server-issued handle plus a bounded reconnect budget.
    # When the upstream Live connection drops abnormally (e.g. a 1006 close with no
    # go_away), we reconnect with this handle to continue the SAME logical session rather
    # than surfacing a crash. The budget is reset every time a healthy session issues a
    # new handle, so it caps *consecutive* failures, not lifetime reconnects.
    resumption_handle: str | None = None
    reconnect_attempts = 0
    MAX_RECONNECTS = 5

    def make_config(handle: str | None) -> types.LiveConnectConfig:
        return build_live_config(
            system_instruction=sys_instruct,
            voice=voice,
            temperature=temperature,
            enable_search=enable_search,
            extra_function_declarations=(
                mcp_provider.declarations if mcp_provider is not None else None
            ),
            resumption_handle=handle,
        )

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

    async def handle_tool_call(session, function_calls):
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
                        sched = getattr(types, "FunctionResponseScheduling", None)
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

            elif mcp_provider is not None and mcp_provider.owns(fc.name):
                # A tool bridged from the MCP server (e.g. Google Sheets).
                args = fc.args if isinstance(fc.args, dict) else {}
                try:
                    result = await mcp_provider.dispatch(fc.name, args)
                    responses.append(
                        types.FunctionResponse(
                            id=fc.id,
                            name=fc.name,
                            response={"result": result or ""},
                        )
                    )
                except Exception as e:
                    logger.error(f"MCP tool '{fc.name}' failed: {e}")
                    responses.append(
                        types.FunctionResponse(
                            id=fc.id,
                            name=fc.name,
                            response={"error": str(e)},
                        )
                    )

        if responses:
            try:
                await session.send_tool_response(function_responses=responses)
            except Exception as e:
                logger.error(f"Error sending tool response: {e}")

    async def downlink(session):
        nonlocal current_input_text, current_output_text, was_interrupted
        nonlocal resumption_handle, reconnect_attempts
        frames_out = 0
        # session.receive() is a PER-TURN async generator: it yields the messages
        # for one model turn and then ends. To keep a continuous full-duplex
        # conversation we must re-enter it for every turn — hence the outer loop.
        # When the underlying connection closes, receive() raises, the exception
        # propagates out and the task ends; the reconnect loop decides what to do.
        while True:
            async for resp in session.receive():
                # Capture the session-resumption handle so we can resume after a drop.
                # A fresh handle also means the session is healthy and progressing, so
                # reset the consecutive-failure budget.
                sru = getattr(resp, "session_resumption_update", None)
                if sru is not None and getattr(sru, "new_handle", None):
                    resumption_handle = sru.new_handle
                    reconnect_attempts = 0

                if getattr(resp, "go_away", None):
                    print("[LIVE] downlink: go_away from server", flush=True)
                    await websocket.send_json({"type": "go_away"})

                # Handle raw audio bytes
                if getattr(resp, "data", None):
                    frames_out += 1
                    if frames_out == 1 or frames_out % 50 == 0:
                        print(
                            f"[LIVE] downlink: audio frame #{frames_out} ({len(resp.data)} bytes) -> browser",
                            flush=True,
                        )
                    await websocket.send_bytes(resp.data)

                sc = getattr(resp, "server_content", None)
                if sc:
                    if getattr(sc, "interrupted", False):
                        was_interrupted = True
                        print(
                            "[LIVE] downlink: INTERRUPTED (barge-in)",
                            flush=True,
                        )
                        await websocket.send_json({"type": "interrupted"})

                    # Transcripts arrive as incremental DELTAS (e.g. 'The', ' quick',
                    # ' brown') with NO per-chunk 'finished' flag. So we ACCUMULATE them
                    # and stream interim (non-final) updates for the live status chip; the
                    # FINAL transcript — which the client renders as a chat bubble — is
                    # emitted once at turn_complete from the accumulated text.
                    in_t = getattr(sc, "input_transcription", None)
                    if in_t and getattr(in_t, "text", ""):
                        current_input_text += in_t.text
                        await websocket.send_json(
                            {
                                "type": "input_transcript",
                                "text": current_input_text,
                                "final": False,
                            }
                        )

                    out_t = getattr(sc, "output_transcription", None)
                    if out_t and getattr(out_t, "text", ""):
                        current_output_text += out_t.text
                        await websocket.send_json(
                            {
                                "type": "output_transcript",
                                "text": current_output_text,
                                "final": False,
                            }
                        )

                    if getattr(sc, "turn_complete", False):
                        print(
                            f"[LIVE] downlink: TURN_COMPLETE | user='{current_input_text[:50]}' | model='{current_output_text[:50]}'",
                            flush=True,
                        )
                        # Emit FINAL transcripts so the client commits chat bubbles.
                        if current_input_text.strip():
                            await websocket.send_json(
                                {
                                    "type": "input_transcript",
                                    "text": current_input_text,
                                    "final": True,
                                }
                            )
                        if current_output_text.strip():
                            await websocket.send_json(
                                {
                                    "type": "output_transcript",
                                    "text": current_output_text,
                                    "final": True,
                                }
                            )
                        await websocket.send_json({"type": "turn_complete"})
                        # Persist and reset turn state
                        await persist_turn(
                            current_input_text,
                            current_output_text,
                            was_interrupted,
                        )
                        current_input_text = ""
                        current_output_text = ""
                        was_interrupted = False

                # Handle Tools
                tc = getattr(resp, "tool_call", None)
                if tc and getattr(tc, "function_calls", None):
                    print(
                        f"[LIVE] downlink: tool_call {[fc.name for fc in tc.function_calls]}",
                        flush=True,
                    )
                    asyncio.create_task(handle_tool_call(session, tc.function_calls))

    async def uplink(session):
        """Pump browser mic/image frames up to `session`. Returns "client_closed" when
        the browser ends the session; raises (for the reconnect loop to catch) if the
        upstream send fails because the Live connection dropped."""
        frames_in = 0
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                print("[LIVE] uplink: browser disconnected", flush=True)
                return "client_closed"
            # Client sends binary mic frames
            if message.get("bytes") is not None:
                frames_in += 1
                if frames_in == 1 or frames_in % 50 == 0:
                    buf = array.array("h")
                    buf.frombytes(message["bytes"])
                    rms = int((sum(s * s for s in buf) / max(len(buf), 1)) ** 0.5)
                    print(
                        f"[LIVE] uplink: mic frame #{frames_in} ({len(message['bytes'])} bytes, rms={rms}, samples={len(buf)}) -> gemini",
                        flush=True,
                    )
                await session.send_realtime_input(
                    audio=types.Blob(
                        data=message["bytes"], mime_type="audio/pcm;rate=16000"
                    )
                )
            elif message.get("text") is not None:
                try:
                    data = json.loads(message["text"])
                    if data.get("type") == "client_info":
                        print(f"[LIVE] client_info: {data}", flush=True)
                    elif data.get("type") == "image_frame":
                        # Screen-share / captured frame -> visual input to Gemini.
                        await send_image_frame(
                            session, data.get("mime"), data.get("data", "")
                        )
                    elif data.get("type") in ["stop", "audio_end"]:
                        print(
                            "[LIVE] uplink: stop/audio_end from browser",
                            flush=True,
                        )
                        return "client_closed"
                except json.JSONDecodeError:
                    pass

    async def run_duplex(session) -> str:
        """Run the mic-up / audio-down loops against one connected session until one
        side finishes. Returns "client" if the browser ended the session, or "server"
        if the upstream connection dropped in a way we can resume from. Re-raises any
        non-recoverable task error so the outer handler can surface it."""
        down_task = asyncio.create_task(downlink(session))
        up_task = asyncio.create_task(uplink(session))
        done, pending = await asyncio.wait(
            [down_task, up_task], return_when=asyncio.FIRST_COMPLETED
        )
        for p in pending:
            p.cancel()
            with contextlib.suppress(BaseException):
                await p

        client_closed = False
        server_drop = False
        fatal: BaseException | None = None
        for d in done:
            exc = d.exception()
            if exc is None:
                if d is up_task and d.result() == "client_closed":
                    client_closed = True
                else:
                    # downlink only returns via exception; a clean return is unexpected
                    # — treat it as an upstream drop and try to resume.
                    server_drop = True
            elif recoverable_disconnect(exc):
                server_drop = True
            else:
                fatal = exc

        if fatal is not None:
            raise fatal
        # A browser close wins over a simultaneous upstream drop.
        if client_closed:
            return "client"
        return "server" if server_drop else "client"

    try:
        # Bring up the MCP (Google Sheets) tool provider and expose its tools to the
        # model, if enabled. A failure here is non-fatal — the session runs without it.
        if settings.MCP_SHEETS_ENABLED:
            from contextlib import AsyncExitStack

            try:
                mcp_stack = AsyncExitStack()
                mcp_provider = await mcp_stack.enter_async_context(
                    build_sheets_provider()
                )
                print(
                    f"[LIVE] MCP tools: {[d.name for d in mcp_provider.declarations]}",
                    flush=True,
                )
            except Exception as e:
                logger.error(f"MCP init failed; continuing without it: {e}")
                mcp_provider = None

        first_connect = True
        while True:
            print(
                f"[LIVE] connecting | model={settings.LIVE_MODEL} | voice={voice} "
                f"| search={enable_search} | resume={'yes' if resumption_handle else 'no'}",
                flush=True,
            )
            try:
                async with gemini_live.connect(make_config(resumption_handle)) as session:
                    if first_connect:
                        await websocket.send_json(
                            {"type": "ready", "voice": voice, "model": settings.LIVE_MODEL}
                        )
                        print(
                            f"[LIVE] session READY | model={settings.LIVE_MODEL} | voice={voice}",
                            flush=True,
                        )
                        # Prime the session with the persona's uploaded reference images.
                        try:
                            imgs = await get_scope_images(persona_id=persona_id)
                            n = await prime_session_with_images(session, imgs)
                            if n:
                                print(
                                    f"[LIVE] primed session with {n} reference image(s)",
                                    flush=True,
                                )
                        except Exception as e:
                            logger.error(f"Failed to prime live session with images: {e}")
                        first_connect = False
                    else:
                        # Resumed session: the audio pipeline in the browser is still
                        # running, so DON'T re-send "ready" (it would re-init audio).
                        await websocket.send_json({"type": "resumed", "voice": voice})
                        print("[LIVE] session RESUMED", flush=True)

                    outcome = await run_duplex(session)
            except WebSocketDisconnect:
                raise
            except Exception as e:
                # connect() itself failed, or a fatal task error propagated. Only a
                # recoverable upstream drop is retried; anything else is fatal.
                if recoverable_disconnect(e):
                    print(f"[LIVE] connection dropped (recoverable): {e!r}", flush=True)
                    outcome = "server"
                else:
                    raise

            if outcome == "client":
                break

            # Upstream dropped. Resume if we have a handle and budget left.
            if resumption_handle is None or reconnect_attempts >= MAX_RECONNECTS:
                print(
                    f"[LIVE] giving up after {reconnect_attempts} reconnect(s) "
                    f"(handle={'yes' if resumption_handle else 'no'})",
                    flush=True,
                )
                with contextlib.suppress(Exception):
                    await websocket.send_json(
                        {
                            "type": "error",
                            "detail": "Live connection was lost and could not be resumed.",
                        }
                    )
                break

            reconnect_attempts += 1
            delay = min(0.5 * (2 ** (reconnect_attempts - 1)), 5.0)
            print(
                f"[LIVE] reconnecting (attempt {reconnect_attempts}/{MAX_RECONNECTS}) in {delay:.1f}s",
                flush=True,
            )
            try:
                await websocket.send_json(
                    {"type": "reconnecting", "attempt": reconnect_attempts}
                )
            except Exception:
                # Browser is gone — nothing to resume for.
                break
            await asyncio.sleep(delay)

        # If any turn was left un-persisted (e.g. disconnected mid-turn), persist it.
        if current_input_text or current_output_text:
            await persist_turn(current_input_text, current_output_text, was_interrupted)

    except WebSocketDisconnect:
        logger.info(f"Live WS disconnected for {conversation_id}")
    except Exception as e:
        logger.error(f"Live WS Error: {e}")
        print(f"[LIVE] ERROR: {e!r}", flush=True)
        try:
            await websocket.send_json({"type": "error", "detail": str(e)})
        except Exception:
            pass
    finally:
        # Tear down the MCP server process (if we started one).
        if mcp_stack is not None:
            try:
                await mcp_stack.aclose()
            except Exception as e:
                logger.error(f"Error closing MCP provider: {e}")
        # Trigger summarizer explicitly on disconnect per §2.2
        try:
            asyncio.create_task(
                SummarizerService().maybe_summarize(conversation_id, force=True)
            )
        except Exception as e:
            logger.error(f"Error triggering summarizer on disconnect: {e}")
