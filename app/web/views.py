import os
import uuid
from fastapi import APIRouter, Depends, Request, HTTPException, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import (
    Persona,
    Conversation,
    Message,
    Memory,
    Panel,
    PanelMessage,
    Asset,
)

router = APIRouter(tags=["Web Views"])

# Setup Jinja2 templates directory
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


@router.get("/", response_class=HTMLResponse)
async def home(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Renders the main dashboard grid containing all personas.
    """
    stmt = select(Persona).order_by(
        Persona.is_builtin.desc(), Persona.created_at.desc()
    )
    result = await db.execute(stmt)
    personas = result.scalars().all()
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"title": "Dashboard — Aura", "personas": personas},
    )


@router.get("/panels", response_class=HTMLResponse)
async def panels_hub(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Panels hub: create a new saved panel from a roster, or resume an existing one. Saved
    panels persist their roster and full transcript, so a panel is a durable conversation.
    """
    personas = (
        (
            await db.execute(
                select(Persona).order_by(
                    Persona.is_builtin.desc(), Persona.created_at.desc()
                )
            )
        )
        .scalars()
        .all()
    )

    panels = (
        (await db.execute(select(Panel).order_by(Panel.updated_at.desc())))
        .scalars()
        .all()
    )

    # Resolve each panel's roster ids to display names for the hub cards.
    name_by_id = {str(p.id): p.name for p in personas}
    panel_rows = [
        {
            "id": panel.id,
            "name": panel.name,
            "updated_at": panel.updated_at,
            "roster_names": [
                name_by_id.get(str(pid), "Unknown") for pid in (panel.persona_ids or [])
            ],
        }
        for panel in panels
    ]

    return templates.TemplateResponse(
        request=request,
        name="panels_hub.html",
        context={
            "title": "Voice Panels — Aura",
            "personas": personas,
            "panels": panel_rows,
        },
    )


@router.get("/panel/{panel_id}", response_class=HTMLResponse)
async def panel_live_view(
    panel_id: uuid.UUID, request: Request, db: AsyncSession = Depends(get_db)
):
    """
    Live view for one saved panel: renders its persisted transcript, then connects to
    /ws/panel/{panel_id} with the panel's stored roster so the conversation resumes.
    """
    panel = await db.get(Panel, panel_id)
    if not panel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Panel not found"
        )

    # Load the roster personas, preserving the panel's stored order.
    persona_rows = (
        (
            await db.execute(
                select(Persona).where(Persona.id.in_(panel.persona_ids or []))
            )
        )
        .scalars()
        .all()
    )
    by_id = {str(p.id): p for p in persona_rows}
    roster = [by_id[str(pid)] for pid in (panel.persona_ids or []) if str(pid) in by_id]

    messages = (
        (
            await db.execute(
                select(PanelMessage)
                .where(PanelMessage.panel_id == panel_id)
                .order_by(PanelMessage.created_at.asc())
            )
        )
        .scalars()
        .all()
    )

    # Panel images (visual context) and panel-scoped documents (shared RAG).
    images = (
        (
            await db.execute(
                select(Asset)
                .where(Asset.panel_id == panel_id)
                .where(Asset.kind == "image")
                .order_by(Asset.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    doc_meta = (
        (
            await db.execute(
                select(Memory.metadata_)
                .where(Memory.persona_id.in_(panel.persona_ids or []))
                .where(Memory.memory_type == "document")
            )
        )
        .scalars()
        .all()
    )
    documents = sorted(
        {
            m["source"]
            for m in doc_meta
            if m and m.get("panel_id") == str(panel_id) and "source" in m
        }
    )

    return templates.TemplateResponse(
        request=request,
        name="panel.html",
        context={
            "title": f"{panel.name} — Voice Panel",
            "panel": panel,
            "roster": roster,
            "messages": messages,
            "images": images,
            "documents": documents,
        },
    )


@router.get("/personas/new", response_class=HTMLResponse)
async def new_persona_form(request: Request):
    """
    Renders the custom persona creation form.
    """
    return templates.TemplateResponse(
        request=request,
        name="persona_form.html",
        context={
            "title": "Create Custom Persona — Aura",
            "action": "create",
            "persona": None,
            "traits_str": "",
        },
    )


@router.get("/personas/{id}/edit", response_class=HTMLResponse)
async def edit_persona_form(
    id: uuid.UUID, request: Request, db: AsyncSession = Depends(get_db)
):
    """
    Renders the custom persona edit form. Built-in personas cannot be edited.
    """
    stmt = select(Persona).where(Persona.id == id)
    result = await db.execute(stmt)
    persona = result.scalar_one_or_none()

    if not persona:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Persona not found"
        )
    if persona.is_builtin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Built-in personas cannot be edited.",
        )

    # Convert traits list to comma-separated string for form input
    traits_str = ""
    if persona.personality_traits:
        if isinstance(persona.personality_traits, list):
            traits_str = ", ".join(persona.personality_traits)
        else:
            traits_str = str(persona.personality_traits)

    return templates.TemplateResponse(
        request=request,
        name="persona_form.html",
        context={
            "title": f"Edit {persona.name} — Aura",
            "action": "edit",
            "persona": persona,
            "traits_str": traits_str,
        },
    )


@router.get("/personas/{id}", response_class=HTMLResponse)
async def persona_detail(
    id: uuid.UUID, request: Request, db: AsyncSession = Depends(get_db)
):
    """
    Renders the conversation sessions history for a specific persona.
    """
    stmt = select(Persona).where(Persona.id == id)
    result = await db.execute(stmt)
    persona = result.scalar_one_or_none()
    if not persona:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Persona not found"
        )

    conv_stmt = (
        select(Conversation)
        .where(Conversation.persona_id == id)
        .order_by(Conversation.updated_at.desc())
    )
    conv_result = await db.execute(conv_stmt)
    conversations = conv_result.scalars().all()

    # Fetch unique uploaded RAG documents for this persona
    stmt_docs = (
        select(Memory.metadata_)
        .where(Memory.persona_id == id)
        .where(Memory.memory_type == "document")
    )
    res_docs = await db.execute(stmt_docs)
    metadata_list = res_docs.scalars().all()
    sources = set()
    for meta in metadata_list:
        # Persona-scoped docs only (panel docs carry a panel_id tag).
        if meta and "source" in meta and not meta.get("panel_id"):
            sources.add(meta["source"])
    documents = sorted(list(sources))

    # Uploaded images (visual context for the persona's live sessions).
    images = (
        (
            await db.execute(
                select(Asset)
                .where(Asset.persona_id == id)
                .where(Asset.kind == "image")
                .order_by(Asset.created_at.desc())
            )
        )
        .scalars()
        .all()
    )

    return templates.TemplateResponse(
        request=request,
        name="conversations.html",
        context={
            "title": f"{persona.name} Sessions — Aura",
            "persona": persona,
            "conversations": conversations,
            "documents": documents,
            "images": images,
        },
    )


@router.get("/chat/{conversation_id}", response_class=HTMLResponse)
async def chat_view(
    conversation_id: uuid.UUID, request: Request, db: AsyncSession = Depends(get_db)
):
    """
    Renders the active chat session page with history.
    """
    # Fetch conversation
    conv_stmt = select(Conversation).where(Conversation.id == conversation_id)
    conv_result = await db.execute(conv_stmt)
    conversation = conv_result.scalar_one_or_none()
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation session not found",
        )

    # Fetch associated persona
    persona_stmt = select(Persona).where(Persona.id == conversation.persona_id)
    persona_result = await db.execute(persona_stmt)
    persona = persona_result.scalar_one_or_none()
    if not persona:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Associated persona not found"
        )

    # Fetch messages
    msg_stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
    )
    msg_result = await db.execute(msg_stmt)
    messages = msg_result.scalars().all()

    return templates.TemplateResponse(
        request=request,
        name="chat.html",
        context={
            "title": f"Chat with {persona.name} — Aura",
            "conversation": conversation,
            "persona": persona,
            "messages": messages,
        },
    )
