import os
import uuid
from fastapi import APIRouter, Depends, Request, HTTPException, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.persona import Persona

router = APIRouter(tags=["Web Views"])

# Setup Jinja2 templates directory
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

@router.get("/", response_class=HTMLResponse)
async def home(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Renders the main dashboard grid containing all personas.
    """
    stmt = select(Persona).order_by(Persona.is_builtin.desc(), Persona.created_at.desc())
    result = await db.execute(stmt)
    personas = result.scalars().all()
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"title": "Dashboard — Aura", "personas": personas}
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
            "traits_str": ""
        }
    )

@router.get("/personas/{id}/edit", response_class=HTMLResponse)
async def edit_persona_form(id: uuid.UUID, request: Request, db: AsyncSession = Depends(get_db)):
    """
    Renders the custom persona edit form. Built-in personas cannot be edited.
    """
    stmt = select(Persona).where(Persona.id == id)
    result = await db.execute(stmt)
    persona = result.scalar_one_or_none()
    
    if not persona:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Persona not found"
        )
    if persona.is_builtin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Built-in personas cannot be edited."
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
            "traits_str": traits_str
        }
    )
