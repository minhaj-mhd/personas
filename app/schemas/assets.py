import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, computed_field


class AssetResponse(BaseModel):
    """Metadata for an uploaded asset. Excludes the raw bytes — clients fetch those
    from the `url` (GET /api/assets/{id})."""

    id: uuid.UUID
    persona_id: Optional[uuid.UUID] = None
    panel_id: Optional[uuid.UUID] = None
    kind: str
    filename: str
    mime_type: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @computed_field
    @property
    def url(self) -> str:
        return f"/api/assets/{self.id}"
