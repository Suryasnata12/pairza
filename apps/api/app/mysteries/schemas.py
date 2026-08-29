import uuid

from pydantic import BaseModel, Field


class MysteryTeaser(BaseModel):
    """What a player sees on the Home screen BEFORE entering — no clue, no answer, no spoilers."""

    id: uuid.UUID
    category: str
    difficulty: int
    summary: str

    model_config = {"from_attributes": True}


class ClueOut(BaseModel):
    id: uuid.UUID
    text: str
    media_url: str | None

    model_config = {"from_attributes": True}


class StageOut(BaseModel):
    """A stage as seen by one player — only THEIR clue is included, never the partner's."""

    id: uuid.UUID
    stage_number: int
    is_final: bool
    context: str | None
    unlocked: bool
    your_clue: ClueOut | None  # null until `unlocked` is true

    model_config = {"from_attributes": True}


class MysteryDetailForSession(BaseModel):
    id: uuid.UUID
    title: str
    category: str
    difficulty: int
    flavor_text: str | None
    stages: list[StageOut]


# --- Admin schemas ---

class ClueIn(BaseModel):
    role: str = Field(pattern="^(player_a|player_b)$")
    text: str
    media_url: str | None = None


class StageIn(BaseModel):
    stage_number: int
    is_final: bool = False
    context: str | None = None
    checkpoint_answer_patterns: list[str] | None = None
    clues: list[ClueIn]


class MysteryCreate(BaseModel):
    title: str
    category: str
    difficulty: int = Field(ge=1, le=5)
    summary: str
    flavor_text: str | None = None
    final_answer_patterns: list[str]
    stages: list[StageIn]


class MysteryUpdate(BaseModel):
    title: str | None = None
    difficulty: int | None = Field(default=None, ge=1, le=5)
    summary: str | None = None
    flavor_text: str | None = None
    final_answer_patterns: list[str] | None = None
    is_published: bool | None = None


class MysteryAdminOut(BaseModel):
    id: uuid.UUID
    title: str
    category: str
    difficulty: int
    summary: str
    is_published: bool
    stage_count: int = 0

    model_config = {"from_attributes": True}
