import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import Base


class Panel(Base):
    """A saved multi-agent voice panel: a named roster of personas the user can
    resume. The roster is stored as an ordered JSON list of persona UUIDs (single-
    user app — a join table would be overkill). Its transcript persists as
    PanelMessage rows so the conversation survives across sessions."""

    __tablename__ = "panels"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    # Ordered list of persona UUIDs (as strings) making up the roster.
    persona_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    messages = relationship(
        "PanelMessage",
        back_populates="panel",
        cascade="all, delete-orphan",
        order_by="PanelMessage.created_at",
    )


class PanelMessage(Base):
    """One line of a persisted panel transcript. `speaker` is the display label
    ("You", "Host", or a panelist's name); `persona_id` records which persona
    spoke (NULL for the user or the host). Kept FK-free on persona so deleting a
    persona never erases panel history."""

    __tablename__ = "panel_messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    panel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("panels.id", ondelete="CASCADE"),
        nullable=False,
    )
    speaker: Mapped[str] = mapped_column(String, nullable=False)
    persona_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    content: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    panel = relationship("Panel", back_populates="messages")
