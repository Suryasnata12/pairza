"""
scripts/validate_mystery.py

Three independent validation stages, run in order, cheapest first:
  1. validate_structure()  — deterministic, free, instant
  2. check_duplicates()    — deterministic, one DB round-trip
  3. validate_semantics()  — costs a real AI API call, only reached if 1+2 pass

Used by scripts/generate_mysteries.py as a library, and directly runnable
against a single JSON candidate for manual testing/debugging:

    python -m scripts.validate_mystery path/to/candidate.json
    python -m scripts.validate_mystery path/to/candidate.json --skip-semantic

A candidate JSON file should match the MysteryCandidate shape in
app/mysteries/schemas.py — see scripts/generate_mysteries.py's own output,
or apps/api/tests/fixtures/ for examples, for the exact shape expected.
"""
import asyncio
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.mysteries.difficulty import get_difficulty_tier
from app.mysteries.models import MYSTERY_CATEGORIES, Mystery
from app.mysteries.schemas import MysteryCandidate
from app.mysteries.service import normalize_answer

settings = get_settings()

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
SEMANTIC_CONFIDENCE_THRESHOLD = 70  # 0-100; below this, reject the stage


@dataclass
class ValidationResult:
    is_valid: bool
    stage: str  # "structure" | "duplicate" | "semantic"
    reason: str | None = None
    warnings: list[str] = field(default_factory=list)

    @staticmethod
    def ok(stage: str, warnings: list[str] | None = None) -> "ValidationResult":
        return ValidationResult(is_valid=True, stage=stage, warnings=warnings or [])

    @staticmethod
    def fail(stage: str, reason: str) -> "ValidationResult":
        return ValidationResult(is_valid=False, stage=stage, reason=reason)


# --- Stage 1: structural validation (deterministic, free, instant) ---

def validate_structure(raw: dict) -> tuple[MysteryCandidate | None, ValidationResult]:
    """Parses and checks the raw dict against the full structural checklist.
    Returns (candidate_or_None, result) — candidate is None only if the
    shape is too broken to even parse."""
    try:
        candidate = MysteryCandidate.model_validate(raw)
    except ValidationError as exc:
        return None, ValidationResult.fail("structure", f"Schema validation failed: {exc.errors()[0]['msg']}")

    warnings: list[str] = []

    if candidate.category not in MYSTERY_CATEGORIES:
        return None, ValidationResult.fail(
            "structure", f"Unknown category '{candidate.category}'. Must be one of {MYSTERY_CATEGORIES}."
        )

    stage_numbers = [s.stage_number for s in candidate.stages]
    if stage_numbers != list(range(1, len(candidate.stages) + 1)):
        return None, ValidationResult.fail(
            "structure", f"Stage numbers must be sequential starting at 1, got {stage_numbers}."
        )

    final_stages = [s for s in candidate.stages if s.is_final]
    if len(final_stages) != 1:
        return None, ValidationResult.fail(
            "structure", f"Exactly one stage must be marked is_final, found {len(final_stages)}."
        )
    if final_stages[0].stage_number != candidate.stages[-1].stage_number:
        return None, ValidationResult.fail("structure", "The final stage must be the LAST stage, not an earlier one.")

    for stage in candidate.stages:
        roles = sorted(c.role for c in stage.clues)
        if roles != ["player_a", "player_b"]:
            return None, ValidationResult.fail(
                "structure", f"Stage {stage.stage_number} must have exactly one player_a and one player_b clue, got {roles}."
            )

        clue_a = next(c.text for c in stage.clues if c.role == "player_a")
        clue_b = next(c.text for c in stage.clues if c.role == "player_b")
        if normalize_answer(clue_a) == normalize_answer(clue_b):
            return None, ValidationResult.fail(
                "structure",
                f"Stage {stage.stage_number}'s two clues are identical (or identical after normalization) — "
                "the entire mechanic requires them to be genuinely different.",
            )

        if not stage.is_final and not stage.checkpoint_answer_patterns:
            return None, ValidationResult.fail(
                "structure", f"Stage {stage.stage_number} is not final but has no checkpoint_answer_patterns — players could never advance past it."
            )
        if stage.is_final and stage.checkpoint_answer_patterns:
            warnings.append(
                f"Stage {stage.stage_number} is final but also has checkpoint_answer_patterns set — "
                "these are ignored (only final_answer_patterns is ever checked on the final stage)."
            )

    # A clue that already contains the literal answer trivializes the whole puzzle.
    normalized_answers = {normalize_answer(a) for a in candidate.final_answer_patterns if normalize_answer(a)}
    for stage in candidate.stages:
        for clue in stage.clues:
            normalized_clue = normalize_answer(clue.text)
            for answer in normalized_answers:
                if answer in normalized_clue:
                    return None, ValidationResult.fail(
                        "structure",
                        f"Stage {stage.stage_number}'s {clue.role} clue appears to contain the literal answer "
                        f"('{answer}') — this gives it away outright.",
                    )

    if len({normalize_answer(a) for a in candidate.final_answer_patterns}) != len(candidate.final_answer_patterns):
        warnings.append("final_answer_patterns has duplicate entries after normalization.")

    return candidate, ValidationResult.ok("structure", warnings)


# --- Stage 2: duplicate detection (deterministic, one DB query) ---

async def check_duplicates(db: AsyncSession, candidate: MysteryCandidate) -> ValidationResult:
    """At minimum: reject an exact-normalized-title match, and reject sharing
    an accepted answer with an existing mystery in the SAME category (two
    different puzzles with the same solution in one category would be easy
    to guess from a player's own history, and confusing besides)."""
    normalized_title = normalize_answer(candidate.title)
    normalized_answers = {normalize_answer(a) for a in candidate.final_answer_patterns}

    existing_rows = (await db.execute(select(Mystery.title, Mystery.category, Mystery.final_answer_patterns))).all()

    for existing_title, existing_category, existing_answers in existing_rows:
        if normalize_answer(existing_title) == normalized_title:
            return ValidationResult.fail("duplicate", f"Title duplicates an existing mystery: '{existing_title}'.")

        if existing_category == candidate.category:
            existing_normalized_answers = {normalize_answer(a) for a in existing_answers}
            overlap = normalized_answers & existing_normalized_answers
            if overlap:
                return ValidationResult.fail(
                    "duplicate",
                    f"Shares accepted answer {sorted(overlap)!r} with an existing {existing_category} "
                    f"mystery ('{existing_title}').",
                )

    return ValidationResult.ok("duplicate")


# --- Stage 3: semantic validation (costs a real AI API call per stage) ---

SEMANTIC_VALIDATION_PROMPT = """You are a strict quality reviewer for a two-player puzzle game called Pairza. Two \
strangers are matched together and each gets ONE of the two clues below for this stage. Neither can see the \
other's clue. They must combine what they each see, by describing it to each other in chat, to arrive at the answer.

Category: {category}
Difficulty (1=gentle, 5=brutal): {difficulty} — {difficulty_style}
Time limit for the WHOLE mystery (all stages together): {time_limit_minutes} minutes
Stage context: {context}
Clue A (shown only to player A): {clue_a}
Clue B (shown only to player B): {clue_b}
Expected answer(s): {answers}

Judge this stage against ALL of these criteria:
1. SOLVABLE: a reasonable person combining both clues could actually arrive at the answer.
2. GENUINELY COMPLEMENTARY: clue A alone is not enough to guess the answer, and neither is clue B alone.
3. NOT MISLEADING: nothing in either clue points to a different, equally plausible wrong answer once both clues are combined. (A hard mystery may use deliberate red herrings or indirect wording, but the combined clues must still single out exactly ONE answer.)
4. APPROPRIATE: nothing sexual, hateful, violent, or otherwise inappropriate for a general audience.
5. DIFFICULTY & TIME MATCH: roughly matches the stated difficulty level, and two strangers chatting could realistically solve the whole mystery within the time limit.

Respond with ONLY a JSON object, no other text, in exactly this shape:
{{"confidence": <integer 0-100, how confident you are this stage is high quality and meets all 5 criteria>, \
"reason": "<one or two sentences explaining your confidence score, especially if below 100>"}}
"""


async def _call_anthropic(prompt: str, api_key: str, model: str) -> str:
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            ANTHROPIC_API_URL,
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": model, "max_tokens": 500, "messages": [{"role": "user", "content": prompt}]},
        )
        resp.raise_for_status()
        data = resp.json()
        return "".join(block.get("text", "") for block in data.get("content", []) if block.get("type") == "text")


def _extract_json(text: str) -> dict:
    """Models occasionally wrap JSON in prose or code fences despite instructions — this recovers it."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object found in model response: {text[:200]!r}")
    return json.loads(match.group(0))


async def validate_semantics(candidate: MysteryCandidate, api_key: str, model: str) -> ValidationResult:
    if not api_key:
        return ValidationResult.fail("semantic", "No ANTHROPIC_API_KEY configured — cannot run semantic validation.")

    warnings: list[str] = []
    for stage in candidate.stages:
        clue_a = next(c.text for c in stage.clues if c.role == "player_a")
        clue_b = next(c.text for c in stage.clues if c.role == "player_b")
        answers = candidate.final_answer_patterns if stage.is_final else (stage.checkpoint_answer_patterns or [])
        tier = get_difficulty_tier(candidate.difficulty)
        prompt = SEMANTIC_VALIDATION_PROMPT.format(
            category=candidate.category, difficulty=candidate.difficulty,
            difficulty_style=tier.style, time_limit_minutes=tier.time_limit_minutes,
            context=stage.context or "(none given)", clue_a=clue_a, clue_b=clue_b, answers=", ".join(answers),
        )
        try:
            raw_response = await _call_anthropic(prompt, api_key, model)
            judgment = _extract_json(raw_response)
            confidence = int(judgment.get("confidence", 0))
            reason = str(judgment.get("reason", ""))
        except Exception as exc:  # noqa: BLE001 — a flaky API call must not crash a whole generation batch
            return ValidationResult.fail("semantic", f"Stage {stage.stage_number}: semantic validation call failed ({exc}).")

        if confidence < SEMANTIC_CONFIDENCE_THRESHOLD:
            return ValidationResult.fail("semantic", f"Stage {stage.stage_number} scored {confidence}/100: {reason}")
        if confidence < 90:
            warnings.append(f"Stage {stage.stage_number} scored {confidence}/100: {reason}")

    return ValidationResult.ok("semantic", warnings)


# --- Orchestration ---

async def validate_mystery(
    db: AsyncSession, raw: dict, api_key: str, model: str, skip_semantic: bool = False
) -> tuple[MysteryCandidate | None, ValidationResult]:
    """Runs all three stages in order, cheapest first, stopping at the first failure."""
    candidate, result = validate_structure(raw)
    if not result.is_valid or candidate is None:
        return None, result

    dup_result = await check_duplicates(db, candidate)
    if not dup_result.is_valid:
        return candidate, dup_result

    if skip_semantic:
        return candidate, ValidationResult.ok("semantic", result.warnings + dup_result.warnings + ["Semantic validation skipped."])

    semantic_result = await validate_semantics(candidate, api_key, model)
    if not semantic_result.is_valid:
        return candidate, semantic_result

    return candidate, ValidationResult.ok("semantic", result.warnings + dup_result.warnings + semantic_result.warnings)


async def _main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m scripts.validate_mystery <path_to_candidate.json> [--skip-semantic]")
        sys.exit(1)

    path = Path(sys.argv[1])
    skip_semantic = "--skip-semantic" in sys.argv
    raw = json.loads(path.read_text())

    from app.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        candidate, result = await validate_mystery(
            db, raw, settings.ANTHROPIC_API_KEY, settings.MYSTERY_GENERATOR_MODEL, skip_semantic
        )

    print(f"Valid: {result.is_valid}")
    print(f"Stage reached: {result.stage}")
    if result.reason:
        print(f"Reason: {result.reason}")
    for w in result.warnings:
        print(f"Warning: {w}")
    sys.exit(0 if result.is_valid else 1)


if __name__ == "__main__":
    asyncio.run(_main())
