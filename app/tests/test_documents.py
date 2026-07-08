import pytest
from unittest.mock import patch
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.db import async_session_maker
from app.main import app
from app.models import Persona, Memory
from app.services.documents import (
    DocumentExtractionError,
    extract_pdf_text,
    extract_upload_text,
)
from app.tests.test_memory import mock_httpx_post


def build_pdf_bytes(text: str) -> bytes:
    """
    Builds a minimal single-page PDF containing `text`, computing xref offsets
    so pypdf can parse it without reconstruction.
    """
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"

    xref_pos = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_pos}\n%%EOF\n"
    ).encode()
    return bytes(out)


def test_extract_pdf_text():
    pdf = build_pdf_bytes("The launch code is BLUE-42.")
    assert extract_pdf_text(pdf).strip() == "The launch code is BLUE-42."


def test_extract_upload_text_routes_pdf_by_extension():
    pdf = build_pdf_bytes("Chunk me.")
    assert extract_upload_text("notes.PDF", None, pdf).strip() == "Chunk me."


def test_extract_upload_text_routes_pdf_by_content_type():
    pdf = build_pdf_bytes("Chunk me too.")
    text = extract_upload_text("upload", "application/pdf", pdf)
    assert text.strip() == "Chunk me too."


def test_extract_upload_text_plain_text_passthrough():
    assert extract_upload_text("notes.md", "text/markdown", "# Hello".encode()) == "# Hello"


def test_extract_upload_text_rejects_unknown_binary():
    with pytest.raises(DocumentExtractionError, match="Unsupported file type"):
        extract_upload_text("image.png", "image/png", b"\x89PNG\r\n\x1a\n\x00\x00")


def test_extract_pdf_text_rejects_corrupted_pdf():
    with pytest.raises(DocumentExtractionError, match="corrupted or password-protected"):
        extract_pdf_text(b"%PDF-1.4 garbage that is not a real pdf")


def test_extract_pdf_text_rejects_textless_pdf():
    pdf = build_pdf_bytes("")
    with pytest.raises(DocumentExtractionError, match="No extractable text"):
        extract_pdf_text(pdf)


@pytest.mark.asyncio
async def test_upload_pdf_document_endpoint():
    async with async_session_maker() as session:
        persona = Persona(
            name="PDF Reader", system_prompt="You read PDFs.", is_builtin=False
        )
        session.add(persona)
        await session.commit()
        persona_id = persona.id

    try:
        pdf = build_pdf_bytes("Gemini models were developed by Google DeepMind.")
        with patch("app.services.embeddings.httpx.AsyncClient.post", mock_httpx_post):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.post(
                    f"/api/personas/{persona_id}/documents",
                    files={"file": ("deepmind.pdf", pdf, "application/pdf")},
                )
        assert resp.status_code == 201
        assert resp.json()["filename"] == "deepmind.pdf"

        async with async_session_maker() as session:
            stmt = (
                select(Memory)
                .where(Memory.persona_id == persona_id)
                .where(Memory.memory_type == "document")
            )
            chunks = (await session.execute(stmt)).scalars().all()
            assert len(chunks) > 0
            assert "Google DeepMind" in chunks[0].content
            assert chunks[0].metadata_["source"] == "deepmind.pdf"
    finally:
        async with async_session_maker() as session:
            db_persona = await session.get(Persona, persona_id)
            if db_persona:
                await session.delete(db_persona)
                await session.commit()


@pytest.mark.asyncio
async def test_upload_scanned_pdf_returns_400():
    async with async_session_maker() as session:
        persona = Persona(
            name="PDF Rejecter", system_prompt="You reject scans.", is_builtin=False
        )
        session.add(persona)
        await session.commit()
        persona_id = persona.id

    try:
        textless_pdf = build_pdf_bytes("")
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                f"/api/personas/{persona_id}/documents",
                files={"file": ("scan.pdf", textless_pdf, "application/pdf")},
            )
        assert resp.status_code == 400
        assert "No extractable text" in resp.json()["detail"]
    finally:
        async with async_session_maker() as session:
            db_persona = await session.get(Persona, persona_id)
            if db_persona:
                await session.delete(db_persona)
                await session.commit()
