import uuid
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.persona import Persona
from app.schemas.conversations import ConversationCreate, ConversationResponse, MessageResponse

router = APIRouter(prefix="/api/conversations", tags=["Conversations"])

@router.post("", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_conversation(payload: ConversationCreate, db: AsyncSession = Depends(get_db)):
    """
    Create a new conversation session for a persona.
    """
    # Verify persona exists
    persona_stmt = select(Persona).where(Persona.id == payload.persona_id)
    persona_result = await db.execute(persona_stmt)
    persona = persona_result.scalar_one_or_none()
    if not persona:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Persona not found"
        )
    
    # Generate default title if not provided
    title = payload.title
    if not title:
        now = datetime.now()
        title = f"Session — {now.strftime('%B %d, %Y, %I:%M %p')}"

    conversation = Conversation(
        persona_id=payload.persona_id,
        title=title
    )
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    return conversation

@router.get("", response_model=List[ConversationResponse])
async def list_conversations(
    persona_id: Optional[uuid.UUID] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """
    List conversations, optionally filtered by persona_id, ordered by last update.
    """
    stmt = select(Conversation)
    if persona_id:
        stmt = stmt.where(Conversation.persona_id == persona_id)
    stmt = stmt.order_by(Conversation.updated_at.desc())
    result = await db.execute(stmt)
    return result.scalars().all()

@router.get("/{id}", response_model=ConversationResponse)
async def get_conversation(id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """
    Get conversation metadata by ID.
    """
    stmt = select(Conversation).where(Conversation.id == id)
    result = await db.execute(stmt)
    conversation = result.scalar_one_or_none()
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )
    return conversation

@router.get("/{id}/messages", response_model=List[MessageResponse])
async def get_conversation_messages(id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """
    Get all messages for a specific conversation in chronological order.
    """
    # Check if conversation exists
    conv_stmt = select(Conversation).where(Conversation.id == id)
    conv_result = await db.execute(conv_stmt)
    if not conv_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )
        
    stmt = select(Message).where(Message.conversation_id == id).order_by(Message.created_at.asc())
    result = await db.execute(stmt)
    return result.scalars().all()

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """
    Delete a conversation session and all its messages.
    """
    stmt = select(Conversation).where(Conversation.id == id)
    result = await db.execute(stmt)
    conversation = result.scalar_one_or_none()
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )
    await db.delete(conversation)
    await db.commit()
    return
