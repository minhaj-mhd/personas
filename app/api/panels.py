import uuid
from typing import List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import Persona, Panel, PanelMessage
from app.schemas.panels import PanelCreate, PanelResponse, PanelMessageResponse

router = APIRouter(prefix="/api/panels", tags=["Panels"])


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
