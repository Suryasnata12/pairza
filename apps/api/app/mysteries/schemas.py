import uuid

from pydantic import BaseModel, Field

from app.mysteries.difficulty import MAX_DIFFICULTY, MIN_DIFFICULTY


class MysteryTeaser(BaseModel):
    """What a player sees on the Home screen BEFORE entering — no clue, no answer, no spoilers."""

    id: uuid.UUID
    category: str
    difficulty: int
    summary: str
    time_limit_seconds: int | None = None  # derived from difficulty — see mysteries/difficulty.py

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
    time_limit_seconds: int | None = None  # derived from difficulty — see mysteries/difficulty.py
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
    difficulty: int = Field(ge=MIN_DIFFICULTY, le=MAX_DIFFICULTY)
    summary: str
    flavor_text: str | None = None
    final_answer_patterns: list[str]
    stages: list[StageIn]


class MysteryUpdate(BaseModel):
    title: str | None = None
    difficulty: int | None = Field(default=None, ge=MIN_DIFFICULTY, le=MAX_DIFFICULTY)
    summary: str | None = None
    flavor_text: str | None = None
    final_answer_patterns: list[str] | None = None
    is_published: bool | None = None


class MysteryAdminOut(BaseModel):
    id: uuid.UUID
    title: str
    category: str
    difficulty: int
    time_limit_seconds: int | None = None  # derived from difficulty — see mysteries/difficulty.py
    summary: str
    is_published: bool
    stage_count: int = 0

    model_config = {"from_attributes": True}


class DifficultyLevelOut(BaseModel):
    """One row of the difficulty -> time-limit table, so no client ever has to hard-code it."""

    difficulty: int
    time_limit_minutes: int
    time_limit_seconds: int
    style: str


# --- AI generation pipeline (scripts/generate_mysteries.py, scripts/validate_mystery.py) ---
# This is the exact JSON shape the generator prompts the model to return,
# and the shape validate_mystery.py's structural checks are written against.
# Kept separate from MysteryCreate above because this one has stricter,
# generation-specific validation (min/max lengths, required stage shape)
# baked into the field constraints themselves, catching malformed model
# output before it ever reaches the deterministic checklist.

class ClueCandidate(BaseModel):
    role: str = Field(pattern="^(player_a|player_b)$")
    text: str = Field(min_length=10, max_length=600)


class StageCandidate(BaseModel):
    stage_number: int = Field(ge=1)
    is_final: bool
    context: str | None = Field(default=None, max_length=400)
    checkpoint_answer_patterns: list[str] | None = None
    clues: list[ClueCandidate] = Field(min_length=2, max_length=2)


class MysteryCandidate(BaseModel):
    """The generator's raw output for one mystery, before any validation."""

    title: str = Field(min_length=3, max_length=200)
    category: str
    difficulty: int = Field(ge=MIN_DIFFICULTY, le=MAX_DIFFICULTY)
    summary: str = Field(min_length=10, max_length=400)
    flavor_text: str | None = Field(default=None, max_length=400)
    final_answer_patterns: list[str] = Field(min_length=1, max_length=8)
    stages: list[StageCandidate] = Field(min_length=1, max_length=5)
