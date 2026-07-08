import uuid
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.config import settings
from app.models import Persona, Memory, Asset
from app.schemas.personas import (
    PersonaCreate,
    PersonaUpdate,
    PersonaResponse,
    PersonaDraftRequest,
    PersonaDraft,
)
from app.schemas.assets import AssetResponse
from app.services.prompt_builder import assemble_system_prompt
from app.services.gemini import GeminiService
from app.services.memory import MemoryService
from app.services.documents import DocumentExtractionError, extract_upload_text
from app.services.assets import validate_image, ImageValidationError

router = APIRouter(prefix="/api/personas", tags=["Personas"])


@router.get("", response_model=List[PersonaResponse])
async def list_personas(db: AsyncSession = Depends(get_db)):
    """
    List all personas, built-in first, then ordered by creation date.
    """
    stmt = select(Persona).order_by(
        Persona.is_builtin.desc(), Persona.created_at.desc()
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=PersonaResponse, status_code=status.HTTP_201_CREATED)
async def create_persona(payload: PersonaCreate, db: AsyncSession = Depends(get_db)):
    """
    Create a new custom persona and automatically assemble its system prompt.
    """
    system_prompt = assemble_system_prompt(
        name=payload.name,
        description=payload.description or "",
        personality_traits=payload.personality_traits,
        speaking_style=payload.speaking_style,
        goals=payload.goals,
        constraints=payload.constraints,
        domain_expertise=payload.domain_expertise,
    )

    persona = Persona(
        name=payload.name,
        description=payload.description,
        system_prompt=system_prompt,
        personality_traits=payload.personality_traits,
        speaking_style=payload.speaking_style,
        goals=payload.goals,
        constraints=payload.constraints,
        domain_expertise=payload.domain_expertise,
        voice=payload.voice,
        temperature=payload.temperature,
        is_builtin=False,
    )

    db.add(persona)
    await db.commit()
    await db.refresh(persona)
    return persona


@router.post("/draft", response_model=PersonaDraft)
async def draft_persona(payload: PersonaDraftRequest):
    """
    Generate a structured persona draft from a natural-language brief using Gemini.
    Nothing is persisted: the caller reviews/edits the returned fields, then submits
    POST /api/personas to actually create the voice agent.
    """
    if not settings.GEMINI_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Gemini API key is not configured; cannot generate a draft.",
        )

    service = GeminiService()
    try:
        return await service.draft_persona(payload.brief)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to generate persona draft: {e}",
        )


@router.get("/{id}", response_model=PersonaResponse)
async def get_persona(id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """
    Get a single persona by UUID.
    """
    stmt = select(Persona).where(Persona.id == id)
    result = await db.execute(stmt)
    persona = result.scalar_one_or_none()
    if not persona:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Persona not found"
        )
    return persona


@router.put("/{id}", response_model=PersonaResponse)
async def update_persona(
    id: uuid.UUID, payload: PersonaUpdate, db: AsyncSession = Depends(get_db)
):
    """
    Update an existing custom persona and rebuild its system prompt.
    Built-in personas cannot be updated.
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
            detail="Built-in personas cannot be modified.",
        )

    # Apply updates
    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(persona, key, value)

    # Re-assemble system prompt
    persona.system_prompt = assemble_system_prompt(
        name=persona.name,
        description=persona.description or "",
        personality_traits=persona.personality_traits,
        speaking_style=persona.speaking_style,
        goals=persona.goals,
        constraints=persona.constraints,
        domain_expertise=persona.domain_expertise,
    )

    await db.commit()
    await db.refresh(persona)
    return persona


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_persona(id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """
    Delete a custom persona. Built-in personas cannot be deleted.
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
            detail="Built-in personas cannot be deleted.",
        )

    await db.delete(persona)
    await db.commit()
    return


@router.post("/{id}/documents", status_code=status.HTTP_201_CREATED)
async def upload_persona_document(
    id: uuid.UUID,
    file: Optional[UploadFile] = File(None),
    raw_text: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a text, markdown, or PDF file or paste raw text to ingest as RAG memory chunks for a persona.
    """
    # Verify persona exists
    persona_stmt = select(Persona).where(Persona.id == id)
    persona_res = await db.execute(persona_stmt)
    if not persona_res.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Persona not found"
        )

    content = ""
    filename = ""
    if file:
        content_bytes = await file.read()
        filename = file.filename or "upload"
        try:
            content = extract_upload_text(filename, file.content_type, content_bytes)
        except DocumentExtractionError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    elif raw_text:
        content = raw_text
        now = datetime.now()
        filename = f"Pasted Text — {now.strftime('%b %d, %Y, %I:%M %p')}"
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Must provide either a file upload or raw_text Form parameter.",
        )

    memory_service = MemoryService()
    try:
        await memory_service.ingest_document(
            persona_id=id, filename=filename, text=content
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to embed document (is Ollama running?): {e}",
        )

    return {"status": "success", "filename": filename}


@router.get("/{id}/documents", response_model=List[str])
async def list_persona_documents(id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """
    Lists unique filenames of uploaded documents in the knowledge base of a persona.
    """
    stmt = (
        select(Memory.metadata_)
        .where(Memory.persona_id == id)
        .where(Memory.memory_type == "document")
    )
    res = await db.execute(stmt)
    metadata_list = res.scalars().all()
    sources = set()
    for meta in metadata_list:
        if meta and "source" in meta:
            sources.add(meta["source"])
    return sorted(list(sources))


@router.delete("/{id}/documents", status_code=status.HTTP_204_NO_CONTENT)
async def delete_persona_documents(id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """
    Wipes all document chunks associated with a persona.
    """
    stmt = (
        delete(Memory)
        .where(Memory.persona_id == id)
        .where(Memory.memory_type == "document")
    )
    await db.execute(stmt)
    await db.commit()
    return


@router.post(
    "/{id}/images", response_model=AssetResponse, status_code=status.HTTP_201_CREATED
)
async def upload_persona_image(
    id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload an image (PNG/JPEG/WebP/GIF) for a persona. Stored as an Asset and shown
    to the persona as a visual frame at the start of a live session.
    """
    persona = await db.get(Persona, id)
    if not persona:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Persona not found"
        )

    data = await file.read()
    try:
        mime = validate_image(file.filename or "image", file.content_type, data)
    except ImageValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    asset = Asset(
        persona_id=id,
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
async def list_persona_images(id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """List a persona's uploaded images (metadata only), newest first."""
    stmt = (
        select(Asset)
        .where(Asset.persona_id == id)
        .where(Asset.kind == "image")
        .order_by(Asset.created_at.desc())
    )
    res = await db.execute(stmt)
    return res.scalars().all()
