"""End-to-end test for panel session-resumption reconnect.

Drives the real `panel_websocket` handler through a 1006 abnormal-closure on the host
session and verifies it RESUMES the same speaker with the server-issued handle instead
of tearing the whole panel down. Uses an ephemeral (unsaved) panel so the flow stays on
the host and touches no memory/persistence.
"""

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import pytest_asyncio

from app.db import async_session_maker
from app.models import Persona
from app.api.panel_ws import panel_websocket
from app.services.gemini_live import GeminiLiveService


@pytest_asyncio.fixture
async def db_session():
    async with async_session_maker() as session:
        yield session


async def _clean(session):
    from sqlalchemy import delete

    try:
        await session.execute(delete(Persona).where(Persona.is_builtin == False))  # noqa: E712
        await session.commit()
    except Exception:
        await session.rollback()


class PanelMockWebSocket:
    def __init__(self, roster_ids):
        self.sent = []
        self.accepted = False
        self.closed = False
        self._first = {"type": "select_roster", "persona_ids": roster_ids}
        self._release = asyncio.Event()

    async def accept(self):
        self.accepted = True

    async def receive_json(self):
        return self._first

    async def send_json(self, data):
        self.sent.append(data)
        if data.get("type") == "resumed":
            self._release.set()

    async def send_bytes(self, b):
        self.sent.append({"type": "_bytes"})

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
async def test_panel_resumes_after_1006(db_session):
    try:
        persona = Persona(
            name="Panelist One", system_prompt="Be brief.", is_builtin=False
        )
        db_session.add(persona)
        await db_session.commit()

        handle_msg = SimpleNamespace(
            session_resumption_update=SimpleNamespace(new_handle="H-1")
        )
        # The exact failure reported in the field: the session-duration GoAway/1008.
        drop = Exception(
            "1008 None. Connection aborted because the client failed to close the "
            "connection after receiving a GoAway signal once the session duration "
            "limit was reached"
        )
        s1 = _FakeSession(turns=[[handle_msg], drop])
        s2 = _FakeSession(turns=[])
        sessions = [s1, s2]
        captured_handles = []

        def fake_connect(self, config):
            captured_handles.append(config.session_resumption.handle)
            idx = len(captured_handles) - 1
            return _FakeConnect(sessions[min(idx, len(sessions) - 1)])

        mock_ws = PanelMockWebSocket([str(persona.id)])

        # An ephemeral (unsaved) panel id -> persist=False, so no memory/persistence I/O.
        with patch.object(GeminiLiveService, "connect", fake_connect):
            await asyncio.wait_for(
                panel_websocket(mock_ws, uuid.uuid4()), timeout=10
            )

        types_sent = [m["type"] for m in mock_ws.sent]

        assert captured_handles == [None, "H-1"]
        assert "ready" in types_sent
        assert "active_speaker" in types_sent
        assert "reconnecting" in types_sent
        assert "resumed" in types_sent
        assert "error" not in types_sent
        # The speaker was announced before the drop, and NOT re-announced on resume
        # (exactly one active_speaker for the single host turn across both connections).
        assert types_sent.count("active_speaker") == 1
        assert types_sent.index("active_speaker") < types_sent.index("reconnecting")
        assert types_sent.index("reconnecting") < types_sent.index("resumed")
    finally:
        await _clean(db_session)
