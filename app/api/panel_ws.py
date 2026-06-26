"""Voice-panel WebSocket — host-led, one Live session at a time (P-3).

Implements the host-led panel: the user picks a roster, a HOST session greets them, and when the
user names a specialist (detected by the floor router on the active session's input transcript),
the floor switches — the current session closes and the named agent's session opens, primed with
the shared panel transcript + that agent's long-term memory.

Design: **exactly one Gemini Live session is open at a time** (the 1:1 constraint). The host
"hears" the whole conversation via the in-memory `PanelState` transcript, not a parallel audio
session. See [[Master Plan — Voice Panel (Host-Led, Subagent-Ready)]].

⚠️ Integration code — verified to import + register; true end-to-end requires a mic test.
"""

import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from google.genai import types

from app.db import async_session_maker
from app.models.persona import Persona
from app.config import settings
from app.services.memory import MemoryService
from app.services.prompt_builder import format_retrieved_memories
from app.services.gemini_live import (
    GeminiLiveService,
    resolve_voice,
    build_live_config,
)
from app.services.panel.router import PanelParticipant
from app.services.panel.session import PanelState, build_agent_priming

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Panel WebSocket"])


def build_host_instruction(roster_names: list[str]) -> str:
    names = ", ".join(roster_names) if roster_names else "the panelists"
    return (
        "You are the HOST and moderator of a live voice panel. The panelists are: "
        f"{names}. Your ONLY two jobs are: (1) greet the user in ONE short sentence and ask who "
        "they would like to talk to; and (2) the instant the user asks for a panelist — even if "
        "they abbreviate or mispronounce the name (e.g. 'Ali sir' means Alistair) — call the "
        "route_to_agent tool with that panelist's correct name. NEVER answer the user's questions "
        "yourself and NEVER role-play, impersonate, or speak as any panelist. If the user asks a "
        "real question without naming anyone, briefly ask which panelist should take it. Keep "
        "every reply to one short sentence (this is audio)."
    )


def build_panel_agent_instruction(base_prompt: str, name: str, other_names: list[str], priming: str) -> str:
    others = ", ".join(other_names) if other_names else "the other panelists"
    directive = (
        f"You are {name}, a panelist on a live voice panel alongside: {others}. Stay in character "
        "and answer ONLY as yourself. ALWAYS follow what the user is saying RIGHT NOW — any past-session "
        "memory or panel history provided below is BACKGROUND ONLY; never force a previous topic onto "
        "the user. If they raise a new subject, go with it. If the user asks to speak with another "
        "panelist, or directs a question at them by name, call the route_to_agent tool with that "
        "panelist's name instead of answering for them. You also have a recall_memory tool for past "
        "context. Keep replies short and conversational, since this is audio."
    )
    parts = [base_prompt]
    if priming:
        parts.append(priming)
    parts.append(directive)
    return "\n\n".join(parts)


def resolve_agent_name(requested: str, roster: list[PanelParticipant]) -> PanelParticipant | None:
    """Tolerant match of a model-provided agent name against the roster."""
    if not requested:
        return None
    r = requested.strip().lower()
    for p in roster:  # exact full name
        if p.name.lower() == r:
            return p
    for p in roster:  # first name
        if p.name.split()[0].lower() == r:
            return p
    for p in roster:  # prefix / substring either direction
        first = p.name.split()[0].lower()
        if first.startswith(r) or r.startswith(first) or first in r or r in first:
            return p
    return None


async def _handle_recall_tool(session, function_calls, persona_id, conversation_id, memory_service):
    responses = []
    for fc in function_calls:
        if fc.name == "recall_memory":
            query = fc.args.get("query", "") if isinstance(fc.args, dict) else getattr(fc.args, "query", "")
            if query:
                try:
                    retrieved = await memory_service.retrieve_context(persona_id, conversation_id, query)
                    fmt = format_retrieved_memories(retrieved)
                    responses.append(
                        types.FunctionResponse(id=fc.id, name="recall_memory", response={"result": fmt})
                    )
                except Exception as e:
                    logger.error(f"Panel recall_memory failed: {e}")
    if responses:
        try:
            await session.send_tool_response(function_responses=responses)
        except Exception as e:
            logger.error(f"Panel send_tool_response failed: {e}")


@router.websocket("/ws/panel/{conversation_id}")
async def panel_websocket(websocket: WebSocket, conversation_id: uuid.UUID):
    await websocket.accept()
    gemini_live = GeminiLiveService()
    memory_service = MemoryService()

    # 1. First client message must select the roster.
    try:
        first = await websocket.receive_json()
    except Exception:
        await websocket.close()
        return

    if first.get("type") != "select_roster":
        await websocket.send_json({"type": "error", "detail": "Expected select_roster as first message"})
        await websocket.close()
        return

    # 2. Load the selected personas.
    roster: list[PanelParticipant] = []
    persona_map: dict[str, dict] = {}
    async with async_session_maker() as db:
        for raw in first.get("persona_ids", []):
            try:
                p = await db.get(Persona, uuid.UUID(str(raw)))
            except Exception:
                p = None
            if p:
                roster.append(PanelParticipant(str(p.id), p.name))
                persona_map[str(p.id)] = {
                    "name": p.name,
                    "system_prompt": p.system_prompt,
                    "voice": p.voice,
                    "temperature": p.temperature,
                }

    if not roster:
        await websocket.send_json({"type": "error", "detail": "No valid personas in roster"})
        await websocket.close()
        return

    state = PanelState(roster=roster, active_id=None)  # active_id None = HOST holds the floor
    roster_names = [r.name for r in roster]
    await websocket.send_json(
        {"type": "ready", "roster": [{"persona_id": r.persona_id, "name": r.name} for r in roster]}
    )

    stop = False

    # 3. Outer loop — one Live session at a time (host, then whichever agent is named).
    while not stop:
        target_id = state.active_id  # None => host
        if target_id is None:
            sys_instruct = build_host_instruction(roster_names)
            voice = resolve_voice(settings.LIVE_VOICE)
            temperature = 0.7
            speaker_name = state.host_name
        else:
            pdata = persona_map[target_id]
            priming = await build_agent_priming(uuid.UUID(target_id), conversation_id, state)
            other_names = [r.name for r in roster if r.persona_id != target_id]
            sys_instruct = build_panel_agent_instruction(
                pdata["system_prompt"], pdata["name"], other_names, priming
            )
            voice = resolve_voice(pdata["voice"])
            temperature = pdata["temperature"]
            speaker_name = pdata["name"]

        config = build_live_config(sys_instruct, voice, temperature, enable_search=False, routing=True)
        await websocket.send_json({"type": "active_speaker", "persona_id": target_id, "name": speaker_name})

        cur_input = ""
        cur_output = ""

        try:
            async with gemini_live.connect(config) as session:

                async def downlink():
                    nonlocal cur_input, cur_output, stop
                    while True:
                        async for resp in session.receive():
                            if getattr(resp, "data", None):
                                await websocket.send_bytes(resp.data)

                            sc = getattr(resp, "server_content", None)
                            if sc:
                                in_t = getattr(sc, "input_transcription", None)
                                if in_t and getattr(in_t, "text", ""):
                                    cur_input += in_t.text
                                    await websocket.send_json(
                                        {"type": "transcript", "speaker": "You", "text": cur_input, "final": False}
                                    )
                                    # Floor routing: detect if the user named another agent.
                                    decision = state.route(cur_input)
                                    if decision.action == "switch":
                                        state.record_user(cur_input)
                                        state.apply_route(decision)
                                        await websocket.send_json(
                                            {"type": "handoff", "to_name": decision.target_name, "to_id": decision.target_id}
                                        )
                                        return  # close this session; outer loop opens the new one

                                out_t = getattr(sc, "output_transcription", None)
                                if out_t and getattr(out_t, "text", ""):
                                    cur_output += out_t.text
                                    await websocket.send_json(
                                        {"type": "transcript", "speaker": speaker_name, "text": cur_output, "final": False}
                                    )

                                if getattr(sc, "interrupted", False):
                                    await websocket.send_json({"type": "interrupted"})

                                if getattr(sc, "turn_complete", False):
                                    if cur_input.strip():
                                        state.record_user(cur_input)
                                    if cur_output.strip():
                                        state.record_agent(target_id, cur_output)
                                    await websocket.send_json({"type": "turn_complete"})
                                    cur_input = ""
                                    cur_output = ""

                            tc = getattr(resp, "tool_call", None)
                            if tc and getattr(tc, "function_calls", None):
                                switch_to = None
                                recall_fcs = []
                                for fc in tc.function_calls:
                                    if fc.name == "route_to_agent":
                                        req = (
                                            fc.args.get("agent_name", "")
                                            if isinstance(fc.args, dict)
                                            else getattr(fc.args, "agent_name", "")
                                        )
                                        tgt = resolve_agent_name(req, state.roster)
                                        if tgt and tgt.persona_id != state.active_id:
                                            switch_to = tgt
                                    elif fc.name == "recall_memory" and target_id:
                                        recall_fcs.append(fc)
                                if recall_fcs:
                                    asyncio.create_task(
                                        _handle_recall_tool(
                                            session, recall_fcs, uuid.UUID(target_id),
                                            conversation_id, memory_service,
                                        )
                                    )
                                if switch_to:
                                    if cur_input.strip():
                                        state.record_user(cur_input)
                                    state.active_id = switch_to.persona_id
                                    await websocket.send_json(
                                        {"type": "handoff", "to_name": switch_to.name, "to_id": switch_to.persona_id}
                                    )
                                    return

                async def uplink():
                    nonlocal stop
                    while True:
                        message = await websocket.receive()
                        if message.get("type") == "websocket.disconnect":
                            stop = True
                            return
                        if message.get("bytes") is not None:
                            await session.send_realtime_input(
                                audio=types.Blob(data=message["bytes"], mime_type="audio/pcm;rate=16000")
                            )
                        elif message.get("text") is not None:
                            try:
                                data = json.loads(message["text"])
                                if data.get("type") in ("stop", "audio_end"):
                                    stop = True
                                    return
                            except json.JSONDecodeError:
                                pass

                down_task = asyncio.create_task(downlink())
                up_task = asyncio.create_task(uplink())
                done, pending = await asyncio.wait(
                    [down_task, up_task], return_when=asyncio.FIRST_COMPLETED
                )
                for p in pending:
                    p.cancel()
                for d in done:
                    exc = d.exception()
                    if exc and not isinstance(exc, asyncio.CancelledError):
                        raise exc

        except WebSocketDisconnect:
            stop = True
        except Exception as e:
            logger.error(f"Panel session error: {e}")
            try:
                await websocket.send_json({"type": "error", "detail": str(e)})
            except Exception:
                pass
            stop = True
