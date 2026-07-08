import base64
import uuid
import pytest
from unittest.mock import patch
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.db import async_session_maker
from app.main import app
from app.models import Persona, Memory
from app.services.assets import validate_image, ImageValidationError
from app.tests.test_memory import mock_httpx_post

# A real 1x1 transparent PNG.
PNG_1x1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


async def _make_persona(name: str) -> uuid.UUID:
    async with async_session_maker() as session:
        p = Persona(name=name, system_prompt=f"You are {name}.", is_builtin=False)
        session.add(p)
        await session.commit()
        return p.id


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# --- validate_image unit tests ---


def test_validate_image_by_content_type():
    assert validate_image("x", "image/png", b"\x89PNG") == "image/png"


def test_validate_image_by_extension_when_type_blank():
    assert validate_image("photo.JPG", None, b"\xff\xd8\xff") == "image/jpeg"


def test_validate_image_rejects_non_image():
    with pytest.raises(ImageValidationError, match="Unsupported image type"):
        validate_image("notes.txt", "text/plain", b"hello")


def test_validate_image_rejects_empty():
    with pytest.raises(ImageValidationError, match="Empty"):
        validate_image("x.png", "image/png", b"")


# --- persona image endpoints ---


@pytest.mark.asyncio
async def test_upload_persona_image_serve_list_delete():
    pid = await _make_persona("ImageOwner")
    async with _client() as ac:
        up = await ac.post(
            f"/api/personas/{pid}/images",
            files={"file": ("shot.png", PNG_1x1, "image/png")},
        )
        assert up.status_code == 201
        body = up.json()
        assert body["filename"] == "shot.png"
        assert body["mime_type"] == "image/png"
        asset_url = body["url"]
        assert asset_url == f"/api/assets/{body['id']}"

        # Raw bytes served back with the stored mime.
        served = await ac.get(asset_url)
        assert served.status_code == 200
        assert served.headers["content-type"].startswith("image/png")
        assert served.content == PNG_1x1

        listing = await ac.get(f"/api/personas/{pid}/images")
        assert [a["id"] for a in listing.json()] == [body["id"]]

        gone = await ac.delete(asset_url)
        assert gone.status_code == 204
        assert (await ac.get(f"/api/personas/{pid}/images")).json() == []


@pytest.mark.asyncio
async def test_upload_persona_image_rejects_text():
    pid = await _make_persona("PickyOwner")
    async with _client() as ac:
        resp = await ac.post(
            f"/api/personas/{pid}/images",
            files={"file": ("notes.txt", b"not an image", "text/plain")},
        )
    assert resp.status_code == 400
    assert "Unsupported image type" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_upload_image_to_missing_persona_404():
    async with _client() as ac:
        resp = await ac.post(
            f"/api/personas/{uuid.uuid4()}/images",
            files={"file": ("x.png", PNG_1x1, "image/png")},
        )
    assert resp.status_code == 404


# --- panel image + document endpoints ---


@pytest.mark.asyncio
async def test_panel_image_upload_and_list():
    a = await _make_persona("PanelImgPersona")
    async with _client() as ac:
        panel = (
            await ac.post(
                "/api/panels", json={"name": "Img Panel", "persona_ids": [str(a)]}
            )
        ).json()
        up = await ac.post(
            f"/api/panels/{panel['id']}/images",
            files={"file": ("board.png", PNG_1x1, "image/png")},
        )
        assert up.status_code == 201
        assert up.json()["panel_id"] == panel["id"]

        listing = await ac.get(f"/api/panels/{panel['id']}/images")
        assert len(listing.json()) == 1


# --- Tabbed uploads UI renders on both single-agent and panel pages ---


@pytest.mark.asyncio
async def test_persona_page_renders_uploads_tabs():
    pid = await _make_persona("TabbedOwner")
    async with _client() as ac:
        # Attach an image so it renders inside the Images tab too.
        await ac.post(
            f"/api/personas/{pid}/images",
            files={"file": ("a.png", PNG_1x1, "image/png")},
        )
        resp = await ac.get(f"/personas/{pid}")
    assert resp.status_code == 200
    assert "data-uploads-manager" in resp.text
    assert 'data-tab-btn="documents"' in resp.text
    assert 'data-tab-btn="images"' in resp.text
    assert f"/api/personas/{pid}/documents" in resp.text
    assert f"/api/personas/{pid}/images" in resp.text


@pytest.mark.asyncio
async def test_panel_page_renders_uploads_tabs():
    a = await _make_persona("TabbedPanelPersona")
    async with _client() as ac:
        panel = (
            await ac.post(
                "/api/panels", json={"name": "Tabbed Panel", "persona_ids": [str(a)]}
            )
        ).json()
        resp = await ac.get(f"/panel/{panel['id']}")
    assert resp.status_code == 200
    assert "data-uploads-manager" in resp.text
    assert f"/api/panels/{panel['id']}/documents" in resp.text
    assert f"/api/panels/{panel['id']}/images" in resp.text


@pytest.mark.asyncio
async def test_panel_document_ingest_list_delete():
    a = await _make_persona("PanelDocPersona")
    async with _client() as ac:
        panel = (
            await ac.post(
                "/api/panels", json={"name": "Doc Panel", "persona_ids": [str(a)]}
            )
        ).json()
        panel_id = panel["id"]

        with patch("app.services.embeddings.httpx.AsyncClient.post", mock_httpx_post):
            up = await ac.post(
                f"/api/panels/{panel_id}/documents",
                files={
                    "file": ("brief.txt", b"Panel shared knowledge base.", "text/plain")
                },
            )
        assert up.status_code == 201
        assert up.json()["filename"] == "brief.txt"

        # Ingested into the roster persona's RAG, tagged with this panel_id.
        async with async_session_maker() as session:
            docs = (
                (
                    await session.execute(
                        select(Memory)
                        .where(Memory.persona_id == a)
                        .where(Memory.memory_type == "document")
                    )
                )
                .scalars()
                .all()
            )
        assert docs and docs[0].metadata_["panel_id"] == panel_id

        listed = await ac.get(f"/api/panels/{panel_id}/documents")
        assert listed.json() == ["brief.txt"]

        cleared = await ac.delete(f"/api/panels/{panel_id}/documents")
        assert cleared.status_code == 204
        assert (await ac.get(f"/api/panels/{panel_id}/documents")).json() == []
