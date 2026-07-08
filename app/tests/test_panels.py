import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.db import async_session_maker
from app.main import app
from app.models import Persona, Panel, PanelMessage
from app.services.panel.persistence import load_panel, append_panel_message


async def _make_persona(name: str) -> uuid.UUID:
    async with async_session_maker() as session:
        p = Persona(name=name, system_prompt=f"You are {name}.", is_builtin=False)
        session.add(p)
        await session.commit()
        return p.id


async def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_create_panel_persists_roster():
    a = await _make_persona("Alistair-Panel")
    b = await _make_persona("Elena-Panel")
    async with await _client() as ac:
        resp = await ac.post(
            "/api/panels",
            json={"name": "Strategy Room", "persona_ids": [str(a), str(b)]},
        )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Strategy Room"
    assert body["persona_ids"] == [str(a), str(b)]  # order preserved

    async with async_session_maker() as session:
        panel = await session.get(Panel, uuid.UUID(body["id"]))
        assert panel is not None
        assert panel.persona_ids == [str(a), str(b)]


@pytest.mark.asyncio
async def test_create_panel_rejects_unknown_persona():
    a = await _make_persona("RealOne")
    ghost = uuid.uuid4()
    async with await _client() as ac:
        resp = await ac.post(
            "/api/panels",
            json={"name": "Bad Roster", "persona_ids": [str(a), str(ghost)]},
        )
    assert resp.status_code == 404
    assert str(ghost) in resp.json()["detail"]


@pytest.mark.asyncio
async def test_list_and_get_panel():
    a = await _make_persona("Solo-Panelist")
    async with await _client() as ac:
        created = (
            await ac.post(
                "/api/panels", json={"name": "Listed", "persona_ids": [str(a)]}
            )
        ).json()
        listing = await ac.get("/api/panels")
        assert listing.status_code == 200
        assert any(p["id"] == created["id"] for p in listing.json())

        got = await ac.get(f"/api/panels/{created['id']}")
        assert got.status_code == 200
        assert got.json()["name"] == "Listed"

        missing = await ac.get(f"/api/panels/{uuid.uuid4()}")
        assert missing.status_code == 404


@pytest.mark.asyncio
async def test_append_and_read_panel_transcript():
    a = await _make_persona("Transcriber")
    async with await _client() as ac:
        panel = (
            await ac.post(
                "/api/panels", json={"name": "Chatty", "persona_ids": [str(a)]}
            )
        ).json()
        panel_id = uuid.UUID(panel["id"])

        # Persist a short transcript via the same helper the WS uses.
        await append_panel_message(panel_id, "You", "Hello panel")
        await append_panel_message(panel_id, "Transcriber", "Hi there", persona_id=a)
        # Blank content is ignored.
        await append_panel_message(panel_id, "You", "   ")

        resp = await ac.get(f"/api/panels/{panel['id']}/messages")
    assert resp.status_code == 200
    msgs = resp.json()
    assert [m["content"] for m in msgs] == ["Hello panel", "Hi there"]
    assert msgs[0]["persona_id"] is None
    assert msgs[1]["persona_id"] == str(a)


@pytest.mark.asyncio
async def test_append_to_missing_panel_is_noop():
    # No panel row => load_panel returns None and append silently no-ops.
    ghost = uuid.uuid4()
    assert await load_panel(ghost) is None
    await append_panel_message(ghost, "You", "into the void")  # must not raise
    async with async_session_maker() as session:
        rows = (
            (
                await session.execute(
                    select(PanelMessage).where(PanelMessage.panel_id == ghost)
                )
            )
            .scalars()
            .all()
        )
    assert rows == []


@pytest.mark.asyncio
async def test_delete_panel_cascades_messages():
    a = await _make_persona("Deletable")
    async with await _client() as ac:
        panel = (
            await ac.post("/api/panels", json={"name": "Temp", "persona_ids": [str(a)]})
        ).json()
        panel_id = uuid.UUID(panel["id"])
        await append_panel_message(panel_id, "You", "will be gone")

        deleted = await ac.delete(f"/api/panels/{panel['id']}")
        assert deleted.status_code == 204

    async with async_session_maker() as session:
        assert await session.get(Panel, panel_id) is None
        rows = (
            (
                await session.execute(
                    select(PanelMessage).where(PanelMessage.panel_id == panel_id)
                )
            )
            .scalars()
            .all()
        )
        assert rows == []


# --- Web views (server-rendered hub + resume page) ---


@pytest.mark.asyncio
async def test_panels_hub_renders():
    await _make_persona("HubVisiblePersona")
    async with await _client() as ac:
        resp = await ac.get("/panels")
    assert resp.status_code == 200
    assert "Voice Panels" in resp.text
    assert "Create a Panel" in resp.text
    assert "HubVisiblePersona" in resp.text  # persona offered in the roster picker


@pytest.mark.asyncio
async def test_panel_live_view_renders_roster_and_history():
    a = await _make_persona("ResumePanelist")
    async with await _client() as ac:
        panel = (
            await ac.post(
                "/api/panels", json={"name": "Resume Me", "persona_ids": [str(a)]}
            )
        ).json()
        await append_panel_message(uuid.UUID(panel["id"]), "You", "remembered line")

        resp = await ac.get(f"/panel/{panel['id']}")
    assert resp.status_code == 200
    assert "Resume Me" in resp.text  # panel name
    assert "ResumePanelist" in resp.text  # roster chip
    assert "remembered line" in resp.text  # persisted transcript pre-rendered


@pytest.mark.asyncio
async def test_panel_live_view_404_for_unknown():
    async with await _client() as ac:
        resp = await ac.get(f"/panel/{uuid.uuid4()}")
    assert resp.status_code == 404


# --- Roster management: add / remove agents ---


@pytest.mark.asyncio
async def test_add_panel_member_appends_and_rejects_duplicate():
    a = await _make_persona("Founder-A")
    b = await _make_persona("Founder-B")
    async with await _client() as ac:
        panel = (
            await ac.post(
                "/api/panels", json={"name": "Growing", "persona_ids": [str(a)]}
            )
        ).json()

        added = await ac.post(
            f"/api/panels/{panel['id']}/members", json={"persona_id": str(b)}
        )
        assert added.status_code == 201
        assert added.json()["persona_ids"] == [str(a), str(b)]  # appended, order kept

        # Adding the same persona again is a conflict.
        dup = await ac.post(
            f"/api/panels/{panel['id']}/members", json={"persona_id": str(b)}
        )
        assert dup.status_code == 409


@pytest.mark.asyncio
async def test_add_unknown_persona_and_unknown_panel_404():
    a = await _make_persona("Solo-Add")
    async with await _client() as ac:
        panel = (
            await ac.post("/api/panels", json={"name": "P", "persona_ids": [str(a)]})
        ).json()
        ghost = await ac.post(
            f"/api/panels/{panel['id']}/members", json={"persona_id": str(uuid.uuid4())}
        )
        assert ghost.status_code == 404

        no_panel = await ac.post(
            f"/api/panels/{uuid.uuid4()}/members", json={"persona_id": str(a)}
        )
        assert no_panel.status_code == 404


@pytest.mark.asyncio
async def test_remove_panel_member_and_guards():
    a = await _make_persona("Stay-A")
    b = await _make_persona("Leave-B")
    async with await _client() as ac:
        panel = (
            await ac.post(
                "/api/panels",
                json={"name": "Shrinking", "persona_ids": [str(a), str(b)]},
            )
        ).json()

        removed = await ac.delete(f"/api/panels/{panel['id']}/members/{b}")
        assert removed.status_code == 200
        assert removed.json()["persona_ids"] == [str(a)]

        # Removing someone not on the roster -> 404.
        gone = await ac.delete(f"/api/panels/{panel['id']}/members/{b}")
        assert gone.status_code == 404

        # Cannot remove the last agent.
        last = await ac.delete(f"/api/panels/{panel['id']}/members/{a}")
        assert last.status_code == 400


@pytest.mark.asyncio
async def test_panel_page_shows_roster_management():
    a = await _make_persona("OnPanel")
    await _make_persona("OffPanel")  # available to add
    async with await _client() as ac:
        panel = (
            await ac.post(
                "/api/panels", json={"name": "Manageable", "persona_ids": [str(a)]}
            )
        ).json()
        resp = await ac.get(f"/panel/{panel['id']}")
    assert resp.status_code == 200
    assert "remove-agent" in resp.text  # remove button on the roster chip
    assert "add-agent-select" in resp.text  # add-agent control
    assert "OffPanel" in resp.text  # a non-roster persona offered to add
