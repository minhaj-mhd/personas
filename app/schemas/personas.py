import uuid
from datetime import datetime
from typing import List, Union, Optional
from pydantic import BaseModel, ConfigDict, Field


class PersonaBase(BaseModel):
    name: str = Field(
        ..., min_length=1, max_length=100, description="The name of the persona"
    )
    description: Optional[str] = Field(
        None, description="Short bio/role of the persona"
    )
    speaking_style: Optional[str] = Field(
        None, description="E.g., warm, concise, Socratic"
    )
    goals: Optional[str] = Field(
        None, description="What the persona is trying to achieve"
    )
    constraints: Optional[str] = Field(
        None, description="Things the persona should never do"
    )
    domain_expertise: Optional[str] = Field(
        None, description="Topics of deep knowledge"
    )
    voice: Optional[str] = Field(None, description="Synthesized voice name/ID")
    temperature: float = Field(0.8, ge=0.0, le=2.0, description="Sampling temperature")


class PersonaCreate(PersonaBase):
    personality_traits: Optional[Union[List[str], str]] = Field(
        None, description="Personality keywords/traits"
    )


class PersonaUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    personality_traits: Optional[Union[List[str], str]] = None
    speaking_style: Optional[str] = None
    goals: Optional[str] = None
    constraints: Optional[str] = None
    domain_expertise: Optional[str] = None
    voice: Optional[str] = None
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)


class PersonaResponse(PersonaBase):
    id: uuid.UUID
    system_prompt: str
    personality_traits: Optional[Union[List[str], str]] = None
    is_builtin: bool
    created_at: datetime

    # Enable SQLAlchemy model compatibility
    model_config = ConfigDict(from_attributes=True)
