import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, Float, DateTime, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import Base


class Persona(Base):
    __tablename__ = "personas"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    system_prompt: Mapped[str] = mapped_column(String, nullable=False)

    # Structured prompt building fields
    personality_traits: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    speaking_style: Mapped[str | None] = mapped_column(String, nullable=True)
    goals: Mapped[str | None] = mapped_column(String, nullable=True)
    constraints: Mapped[str | None] = mapped_column(String, nullable=True)
    domain_expertise: Mapped[str | None] = mapped_column(String, nullable=True)

    # Settings and Metadata
    voice: Mapped[str | None] = mapped_column(String, nullable=True)
    temperature: Mapped[float] = mapped_column(Float, default=0.8)
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    conversations = relationship(
        "Conversation", back_populates="persona", cascade="all, delete-orphan"
    )
