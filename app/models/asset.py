import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, LargeBinary
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class Asset(Base):
    """A binary upload (currently images) attached to either a single persona or a
    panel, for visual injection into a live session. Bytes live in Postgres (BYTEA)
    to keep the single-user app to one store — no filesystem to manage or gitignore.

    Documents are handled separately: their text is chunked + embedded into `memories`
    for RAG recall. Assets are the non-text uploads that a model *sees* rather than
    *recalls*. `kind` leaves room to store more upload types later."""

    __tablename__ = "assets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Exactly one of persona_id / panel_id is set (single-agent vs panel scope).
    persona_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("personas.id", ondelete="CASCADE"),
        nullable=True,
    )
    panel_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("panels.id", ondelete="CASCADE"),
        nullable=True,
    )
    kind: Mapped[str] = mapped_column(String, nullable=False, default="image")
    filename: Mapped[str] = mapped_column(String, nullable=False)
    mime_type: Mapped[str] = mapped_column(String, nullable=False)
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
