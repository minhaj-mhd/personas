import uuid
from typing import List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import Persona, Panel, PanelMessage, Memory, Asset
from app.schemas.panels import PanelCreate, PanelResponse, PanelMessageResponse
from app.schemas.assets import AssetResponse
from app.services.assets import validate_image, ImageValidationError
from app.services.documents import DocumentExtractionError, extract_upload_text
from app.services.memory import MemoryService

router = APIRouter(prefix="/api/panels", tags=["Panels"])


async def _require_panel(id: uuid.UUID, db: AsyncSession) -> Panel:
    panel = await db.get(Panel, id)
    if not panel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Panel not found"
        )
    return panel


@router.post("", response_model=PanelResponse, status_code=status.HTTP_201_CREATED)
async def create_panel(payload: PanelCreate, db: AsyncSession = Depends(get_db)):
    """
    Create (persist) a new multi-agent voice panel from a name + roster. Verifies every
    persona in the roster exists so a panel can never reference a deleted persona.
    """
    # Validate the roster: every id must resolve to a real persona.
    ids = [str(pid) for pid in payload.persona_ids]
    found = (
        (
            await db.execute(
                select(Persona.id).where(Persona.id.in_(payload.persona_ids))
            )
        )
        .scalars()
        .all()
    )
    found_set = {str(f) for f in found}
    missing = [i for i in ids if i not in found_set]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Persona(s) not found: {', '.join(missing)}",
        )

    name = payload.name.strip()
    if not name:
        now = datetime.now()
        name = f"Panel — {now.strftime('%b %d, %Y, %I:%M %p')}"

    panel = Panel(name=name, persona_ids=ids)
    db.add(panel)
    await db.commit()
    await db.refresh(panel)
    return panel


@router.get("", response_model=List[PanelResponse])
async def list_panels(db: AsyncSession = Depends(get_db)):
    """List saved panels, most-recently-used first."""
    stmt = select(Panel).order_by(Panel.updated_at.desc())
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{id}", response_model=PanelResponse)
async def get_panel(id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Fetch a single saved panel by id."""
    panel = await db.get(Panel, id)
    if not panel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Panel not found"
        )
    return panel


@router.get("/{id}/messages", response_model=List[PanelMessageResponse])
async def get_panel_messages(id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Return the persisted transcript for a panel in chronological order."""
    panel = await db.get(Panel, id)
    if not panel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Panel not found"
        )
    stmt = (
        select(PanelMessage)
        .where(PanelMessage.panel_id == id)
        .order_by(PanelMessage.created_at.asc())
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_panel(id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Delete a panel and its persisted transcript (cascade)."""
    panel = await db.get(Panel, id)
    if not panel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Panel not found"
        )
    await db.delete(panel)
    await db.commit()
    return


# --- Panel images (visual context for the whole panel) ---


@router.post(
    "/{id}/images", response_model=AssetResponse, status_code=status.HTTP_201_CREATED
)
async def upload_panel_image(
    id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Upload an image for a panel; shown to whichever panelist holds the floor."""
    await _require_panel(id, db)
    data = await file.read()
    try:
        mime = validate_image(file.filename or "image", file.content_type, data)
    except ImageValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    asset = Asset(
        panel_id=id,
        kind="image",
        filename=file.filename or "image",
        mime_type=mime,
        data=data,
    )
    db.add(asset)
    await db.commit()
    await db.refresh(asset)
    return asset


@router.get("/{id}/images", response_model=List[AssetResponse])
async def list_panel_images(id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """List a panel's uploaded images (metadata only), newest first."""
    await _require_panel(id, db)
    stmt = (
        select(Asset)
        .where(Asset.panel_id == id)
        .where(Asset.kind == "image")
        .order_by(Asset.created_at.desc())
    )
    res = await db.execute(stmt)
    return res.scalars().all()


# --- Panel documents (RAG knowledge shared across the roster) ---


@router.post("/{id}/documents", status_code=status.HTTP_201_CREATED)
async def upload_panel_document(
    id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Ingest a text/markdown/PDF document into the RAG memory of EVERY persona on the
    panel, tagged with this panel_id, so any panelist can recall it. Chunks are stored
    once per roster persona (single-user app — duplicate embeddings are acceptable).
    """
    panel = await _require_panel(id, db)
    roster_ids = [uuid.UUID(str(pid)) for pid in (panel.persona_ids or [])]
    if not roster_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Panel has no personas to attach documents to.",
        )

    content_bytes = await file.read()
    filename = file.filename or "upload"
    try:
        content = extract_upload_text(filename, file.content_type, content_bytes)
    except DocumentExtractionError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    memory_service = MemoryService()
    try:
        for pid in roster_ids:
            await memory_service.ingest_document(
                persona_id=pid,
                filename=filename,
                text=content,
                extra_metadata={"panel_id": str(id)},
            )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to embed document (is Ollama running?): {e}",
        )

    return {"status": "success", "filename": filename}


@router.get("/{id}/documents", response_model=List[str])
async def list_panel_documents(id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """List unique filenames of documents ingested into this panel's knowledge base."""
    panel = await _require_panel(id, db)
    roster_ids = [uuid.UUID(str(pid)) for pid in (panel.persona_ids or [])]
    if not roster_ids:
        return []
    stmt = (
        select(Memory.metadata_)
        .where(Memory.persona_id.in_(roster_ids))
        .where(Memory.memory_type == "document")
    )
    rows = (await db.execute(stmt)).scalars().all()
    sources = {
        meta["source"]
        for meta in rows
        if meta and meta.get("panel_id") == str(id) and "source" in meta
    }
    return sorted(sources)


@router.delete("/{id}/documents", status_code=status.HTTP_204_NO_CONTENT)
async def delete_panel_documents(id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Remove all documents ingested for this panel from every roster persona's memory."""
    panel = await _require_panel(id, db)
    roster_ids = [uuid.UUID(str(pid)) for pid in (panel.persona_ids or [])]
    if not roster_ids:
        return
    # Fetch candidate doc rows, filter to this panel in Python (JSON column), delete by id.
    stmt = (
        select(Memory)
        .where(Memory.persona_id.in_(roster_ids))
        .where(Memory.memory_type == "document")
    )
    rows = (await db.execute(stmt)).scalars().all()
    to_delete = [
        m.id for m in rows if m.metadata_ and m.metadata_.get("panel_id") == str(id)
    ]
    if to_delete:
        await db.execute(delete(Memory).where(Memory.id.in_(to_delete)))
        await db.commit()
    return
