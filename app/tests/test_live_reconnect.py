"""End-to-end test for live session-resumption reconnect.

Drives the real `live_websocket` handler with a faked Gemini Live service that drops
the first connection with a 1006 abnormal-closure (the exact failure that used to crash
the session) and verifies the handler transparently RESUMES using the server-issued
resumption handle instead of surfacing an error.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import pytest_asyncio

from app.db import async_session_maker
from app.models import Persona, Conversation
from app.api.live_ws import live_websocket
from app.services.gemini_live import GeminiLiveService
from app.services.memory import MemoryService
from app.services.summarizer import SummarizerService


@pytest_asyncio.fixture
async def db_session():
    async with async_session_maker() as session:
        yield session


async def _clean(session):
    from sqlalchemy import delete

    try:
        await session.execute(delete(Conversation))
        await session.execute(delete(Persona).where(Persona.is_builtin == False))  # noqa: E712
        await session.commit()
    except Exception:
        await session.rollback()


class LiveMockWebSocket:
    """Minimal ASGI-ish WebSocket. Blocks the mic uplink until the server reports the
    session RESUMED, then reports the browser disconnecting so the handler ends cleanly."""

    def __init__(self):
        self.sent = []
        self.accepted = False
        self.closed = False
        self._release = asyncio.Event()

    async def accept(self):
        self.accepted = True

    async def send_json(self, data):
        self.sent.append(data)
        if data.get("type") == "resumed":
            self._release.set()

    async def send_bytes(self, b):
        self.sent.append({"type": "_bytes", "n": len(b)})

    async def receive(self):
        await self._release.wait()
        return {"type": "websocket.disconnect"}

    async def close(self):
        self.closed = True


class _FakeConnect:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *exc):
        return False


class _FakeSession:
    """`receive()` replays scripted per-turn generators; a scripted Exception is raised
    (modelling the upstream drop). An empty script parks forever (until cancelled)."""

    def __init__(self, turns):
        self._turns = list(turns)

    def receive(self):
        if not self._turns:
            return self._park()
        return self._turn(self._turns.pop(0))

    async def _turn(self, turn):
        if isinstance(turn, Exception):
            raise turn
        for msg in turn:
            yield msg

    async def _park(self):
        await asyncio.Event().wait()
        yield  # unreachable

    async def send_realtime_input(self, **kw):
        pass

    async def send_tool_response(self, **kw):
        pass

    async def send_client_content(self, **kw):
        pass


@pytest.mark.asyncio
async def test_live_resumes_after_1006(db_session):
    try:
        persona = Persona(
            name="Resume Bot", system_prompt="Be brief.", is_builtin=False
        )
        db_session.add(persona)
        await db_session.commit()
        conv = Conversation(persona_id=persona.id, title="Resume Session")
        db_session.add(conv)
        await db_session.commit()

        # First session issues a resumption handle, then drops with a 1006. Second
        # session (the resume) parks until the browser disconnects.
        handle_msg = SimpleNamespace(
            session_resumption_update=SimpleNamespace(new_handle="H-1")
        )
        drop = Exception("1006 None. abnormal closure [internal]")
        s1 = _FakeSession(turns=[[handle_msg], drop])
        s2 = _FakeSession(turns=[])
        sessions = [s1, s2]

        captured_handles = []

        def fake_connect(self, config):
            captured_handles.append(config.session_resumption.handle)
            idx = len(captured_handles) - 1
            return _FakeConnect(sessions[min(idx, len(sessions) - 1)])

        async def no_preamble(self, *a, **k):
            return []

        async def no_summarize(self, *a, **k):
            return None

        mock_ws = LiveMockWebSocket()

        with patch.object(GeminiLiveService, "connect", fake_connect), patch.object(
            MemoryService, "get_preamble_memories", no_preamble
        ), patch.object(
            SummarizerService, "maybe_summarize", no_summarize
        ), patch(
            "app.api.live_ws.get_scope_images", return_value=[]
        ):
            await asyncio.wait_for(live_websocket(mock_ws, conv.id), timeout=10)

        types_sent = [m["type"] for m in mock_ws.sent]

        # It connected twice: once fresh (no handle), once resuming with the handle.
        assert captured_handles == [None, "H-1"]
        # The client saw a clean lifecycle: ready -> reconnecting -> resumed, no error.
        assert "ready" in types_sent
        assert "reconnecting" in types_sent
        assert "resumed" in types_sent
        assert "error" not in types_sent
        # And in the right order.
        assert types_sent.index("ready") < types_sent.index("reconnecting")
        assert types_sent.index("reconnecting") < types_sent.index("resumed")
    finally:
        await _clean(db_session)


@pytest.mark.asyncio
async def test_live_gives_up_without_handle(db_session):
    """A drop before any resumption handle arrives can't be resumed — the handler must
    surface an error rather than loop forever."""
    try:
        persona = Persona(
            name="NoResume Bot", system_prompt="Be brief.", is_builtin=False
        )
        db_session.add(persona)
        await db_session.commit()
        conv = Conversation(persona_id=persona.id, title="NoResume Session")
        db_session.add(conv)
        await db_session.commit()

        drop = Exception("1006 None. abnormal closure [internal]")
        s1 = _FakeSession(turns=[drop])  # drops immediately, no handle ever issued

        connect_calls = []

        def fake_connect(self, config):
            connect_calls.append(config.session_resumption.handle)
            return _FakeConnect(s1)

        async def no_preamble(self, *a, **k):
            return []

        async def no_summarize(self, *a, **k):
            return None

        mock_ws = LiveMockWebSocket()

        with patch.object(GeminiLiveService, "connect", fake_connect), patch.object(
            MemoryService, "get_preamble_memories", no_preamble
        ), patch.object(
            SummarizerService, "maybe_summarize", no_summarize
        ), patch(
            "app.api.live_ws.get_scope_images", return_value=[]
        ):
            await asyncio.wait_for(live_websocket(mock_ws, conv.id), timeout=10)

        types_sent = [m["type"] for m in mock_ws.sent]
        # No handle was ever captured, so we must NOT have attempted a resume...
        assert connect_calls == [None]
        # ...and the client is told the session could not be resumed.
        assert "error" in types_sent
        assert "resumed" not in types_sent
    finally:
        await _clean(db_session)
