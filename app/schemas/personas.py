import uuid
from datetime import datetime
from typing import List, Union, Optional, Literal
from pydantic import BaseModel, ConfigDict, Field

# Prebuilt Gemini Live voices offered on the persona form. Kept in sync with
# persona_form.html's <select> and gemini_live.VALID_VOICES.
VoiceName = Literal[
    "Puck", "Charon", "Fenrir", "Orus", "Aoede", "Kore", "Leda", "Zephyr"
]


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


class PersonaDraftRequest(BaseModel):
    """Free-text brief the user provides to have the AI design a persona."""

    brief: str = Field(
        ...,
        min_length=3,
        max_length=2000,
        description="Natural-language description of the voice agent to design",
    )


class PersonaDraft(BaseModel):
    """AI-generated draft of the persona form fields, for the user to review and edit
    before creating the persona. Doubles as the Gemini structured-output schema."""

    name: str = Field(..., description="A fitting name for the persona")
    description: str = Field(
        ...,
        description="One concise, lowercase sentence; rendered as 'You are {name}, {description}.'",
    )
    personality_traits: List[str] = Field(
        ..., description="3-5 lowercase adjective keywords"
    )
    speaking_style: str = Field(
        ..., description="How the persona sounds out loud: pace, tone, sentence length"
    )
    goals: str = Field(..., description="What the persona actively does for the user")
    constraints: str = Field(
        ..., description="What it must never do, plus any needed safety guardrails"
    )
    domain_expertise: str = Field(
        ..., description="Comma-separated fields of deep knowledge"
    )
    voice: VoiceName = Field(
        ..., description="The prebuilt Gemini Live voice that best fits the persona"
    )
    temperature: float = Field(
        0.8, description="Sampling temperature; 0.6-0.8 focused, 0.85-1.0 expressive"
    )
