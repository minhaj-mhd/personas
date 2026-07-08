import uuid
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class PanelCreate(BaseModel):
    name: str = Field(
        ..., min_length=1, max_length=120, description="Panel display name"
    )
    persona_ids: List[uuid.UUID] = Field(
        ..., min_length=1, description="Ordered roster of persona UUIDs on this panel"
    )


class PanelMemberAdd(BaseModel):
    persona_id: uuid.UUID = Field(..., description="Persona to add to the panel roster")


class PanelResponse(BaseModel):
    id: uuid.UUID
    name: str
    persona_ids: List[uuid.UUID]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PanelMessageResponse(BaseModel):
    id: uuid.UUID
    panel_id: uuid.UUID
    speaker: str
    persona_id: Optional[uuid.UUID] = None
    content: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
