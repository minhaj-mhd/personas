from fastapi import APIRouter, Depends
from sqlalchemy import select, func, distinct
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.persona import Persona
from app.models.conversation import Conversation
from app.models.message import Message
from app.services.analytics import estimate_speaking_minutes

router = APIRouter(prefix="/api/analytics", tags=["Analytics"])


@router.get("")
async def get_analytics(db: AsyncSession = Depends(get_db)):
    """
    Usage analytics across personas: totals plus per-persona conversation/message counts,
    user-vs-assistant split, an estimated spoken-time figure, and last activity.
    """
    personas = (await db.execute(select(func.count(Persona.id)))).scalar_one()
    conversations = (await db.execute(select(func.count(Conversation.id)))).scalar_one()
    messages = (await db.execute(select(func.count(Message.id)))).scalar_one()

    stmt = (
        select(
            Persona.id,
            Persona.name,
            func.count(distinct(Conversation.id)).label("conversations"),
            func.count(Message.id).label("messages"),
            func.count(Message.id).filter(Message.role == "user").label("user_messages"),
            func.count(Message.id)
            .filter(Message.role == "assistant")
            .label("assistant_messages"),
            func.coalesce(func.sum(func.length(Message.content)), 0).label("chars"),
            func.max(Message.created_at).label("last_active"),
        )
        .select_from(Persona)
        .outerjoin(Conversation, Conversation.persona_id == Persona.id)
        .outerjoin(Message, Message.conversation_id == Conversation.id)
        .group_by(Persona.id, Persona.name)
        .order_by(func.count(Message.id).desc())
    )
    rows = (await db.execute(stmt)).all()

    per_persona = [
        {
            "persona_id": str(r.id),
            "name": r.name,
            "conversations": r.conversations or 0,
            "messages": r.messages or 0,
            "user_messages": r.user_messages or 0,
            "assistant_messages": r.assistant_messages or 0,
            "est_speaking_minutes": estimate_speaking_minutes(r.chars or 0),
            "last_active": r.last_active.isoformat() if r.last_active else None,
        }
        for r in rows
    ]

    return {
        "totals": {
            "personas": personas,
            "conversations": conversations,
            "messages": messages,
        },
        "per_persona": per_persona,
    }
