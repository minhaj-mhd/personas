import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict

class ConversationCreate(BaseModel):
    persona_id: uuid.UUID
    title: Optional[str] = None

class MessageResponse(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    role: str
    content: str
    audio_url: Optional[str] = None
    token_count: Optional[int] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class ConversationResponse(BaseModel):
    id: uuid.UUID
    persona_id: uuid.UUID
    title: Optional[str] = None
    last_summarized_message_id: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
