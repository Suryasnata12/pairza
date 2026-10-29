"""Plan-first asynchronous Pairza mystery generator.

Run from apps/api:
    python -m scripts.generate_mysteries --category geo --quantity 10
    python -m scripts.generate_mysteries --all-categories --quantity 5
    python -m scripts.generate_mysteries --category cipher --quantity 3 --difficulty 4 --dry-run

The selected difficulty is enforced by Python before the complete mystery is
requested from Gemini. Candidates must pass deterministic plan validation,
deterministic generated-structure checks, Pairza's existing validation
pipeline, and a final cross-stage dependency review before they can be saved.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import random
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.ai.gemini import call_gemini
from app.common.database import AsyncSessionLocal
from app.config.settings import get_settings
from app.mysteries.difficulty import (
    DIFFICULTY_TIERS,
    MAX_DIFFICULTY,
    MIN_DIFFICULTY,
    get_difficulty_tier,
)
from app.mysteries.models import MYSTERY_CATEGORIES, Mystery, MysteryClue, MysteryStage
from app.mysteries.schemas import MysteryCandidate
from app.mysteries.service import normalize_answer
from scripts.validate_mystery import _extract_json, validate_mystery

settings = get_settings()
logger = logging.getLogger("pairza.generate_mysteries")

MAX_ATTEMPTS_PER_MYSTERY = 3
MAX_PLAN_ATTEMPTS = 3
GENERATOR_VERSION_PREFIX = "v2-plan-first"

CATEGORY_GUIDANCE = {
    "internet_hunt": "archived pages, forum fragments, filenames, metadata, link trails, or old-internet evidence",
    "visual": "text-described visual scenes, spatial layouts, colors, shapes, symbols, or image details; do not assume an actual image is attached",
    "geo": "real-world geography, spatial relationships, map descriptions, coordinates, landmarks, and geographic evidence",
    "audio": "text-described sound patterns, rhythms, sequences, transcriptions, or acoustic clues; do not assume actual audio is attached",
    "logic": "deduction, constraints, elimination, contradictions, and consistent logical inference",
    "cipher": "a genuine code or cipher where the key or transformation is discoverable from the clues",
    "investigation": "case files, witness statements, timelines, physical evidence, contradictions, and cross-referenced testimony",
    "pattern": "sequences, repeated structures, symbol systems, numeric relationships, or transformations",
    "arg": "an original alternate-reality-game-style narrative using connected evidence across multiple artifacts",
}

# Mechanics are canonical labels, not arbitrary free text. This prevents the
# planner from claiming diversity through near-synonyms such as "pattern
# finding" and "pattern recognition".
MECHANICS_BY_CATEGORY: dict[str, set[str]] = {
    "internet_hunt": {
        "deduction", "elimination", "pattern recognition", "sequence reconstruction",
        "evidence correlation", "timeline reconstruction", "contradiction analysis",
        "key extraction", "cross-reference", "classification", "logical constraints",
    },
    "visual": {
        "deduction", "elimination", "pattern recognition", "spatial reasoning",
        "transformation", "sequence reconstruction", "symbol mapping", "key extraction",
        "cross-reference", "classification", "logical constraints",
    },
    "geo": {
        "deduction", "elimination", "spatial reasoning", "coordinate interpretation",
        "evidence correlation", "cross-reference", "classification", "logical constraints",
        "sequence reconstruction", "timeline reconstruction",
    },
    "audio": {
        "deduction", "pattern recognition", "sequence reconstruction", "symbol mapping",
        "transformation", "key extraction", "evidence correlation", "cross-reference",
        "classification", "elimination",
    },
    "logic": {
        "deduction", "elimination", "logical constraints", "contradiction analysis",
        "classification", "sequence reconstruction", "cross-reference", "evidence correlation",
    },
    "cipher": {
        "deduction", "elimination", "cipher decoding", "key extraction", "symbol mapping",
        "transformation", "pattern recognition", "sequence reconstruction", "cross-reference",
    },
    "investigation": {
        "deduction", "elimination", "evidence correlation", "timeline reconstruction",
        "contradiction analysis", "cross-reference", "classification", "logical constraints",
        "sequence reconstruction",
    },
    "pattern": {
        "deduction", "elimination", "pattern recognition", "sequence reconstruction",
        "transformation", "symbol mapping", "key extraction", "cross-reference", "classification",
    },
    "arg": {
        "deduction", "elimination", "evidence correlation", "cross-reference",
        "timeline reconstruction", "pattern recognition", "key extraction", "symbol mapping",
        "transformation", "contradiction analysis", "sequence reconstruction",
    },
}

# All structural choices live in Python. Gemini may choose within these bounds,
# but cannot redefine a level's required architecture.
DIFFICULTY_RULES: dict[int, dict[str, Any]] = {
    1: {
        "min_stages": 1, "max_stages": 1, "exact_stages": 1,
        "minimum_distinct_mechanics": 1, "minimum_operations": 1,
        "architecture": "One stage and one reasoning operation. Direct complementary clues. No checkpoint dependency.",
    },
    2: {
        "min_stages": 1, "max_stages": 2, "exact_stages": None,
        "minimum_distinct_mechanics": 1, "minimum_operations": 2,
        "architecture": "More reasoning than Level 1. One stage must spell out at least two linked reasoning operations; alternatively use two connected stages where Stage 1 yields a checkpoint required by Stage 2. Do not merely make the clue text longer.",
    },
    3: {
        "min_stages": 2, "max_stages": 2, "exact_stages": 2,
        "minimum_distinct_mechanics": 1, "minimum_operations": 2,
        "architecture": "Exactly two connected stages. Stage 1 produces a checkpoint; Stage 2 requires it and produces the final answer. At least two meaningful reasoning operations overall.",
    },
    4: {
        "min_stages": 2, "max_stages": 3, "exact_stages": None,
        "minimum_distinct_mechanics": 2, "minimum_operations": 2,
        "architecture": "Two or three meaningfully connected stages. Every later stage requires the immediately preceding checkpoint. Use at least two different, category-appropriate reasoning mechanics. Never a single-step riddle.",
    },
    5: {
        "min_stages": 3, "max_stages": 3, "exact_stages": 3,
        "minimum_distinct_mechanics": 3, "minimum_operations": 3,
        "architecture": "Exactly three stages in one reasoning chain: Stage 1 produces checkpoint A; Stage 2 requires A and produces checkpoint B; Stage 3 requires B and produces the final answer. Use at least three distinct mechanics. The final answer must not be inferable from the initial clues alone. Never three independent mini-puzzles.",
    },
}


class CandidateGenerationError(RuntimeError):
    """A candidate could not be planned or generated correctly."""


def _normalise_label(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().casefold().replace("_", " "))


def _operation_segments(value: str) -> list[str]:
    """Conservatively count explicit linked operations in planner prose."""
    return [
        part.strip(" .:-\t\n")
        for part in re.split(r";|\n|\bthen\b|\bafter that\b|\bnext\b", value, flags=re.IGNORECASE)
        if part.strip(" .:-\t\n")
    ]


def _expected_plan_outputs(stage_count: int) -> list[tuple[list[str], str]]:
    if stage_count == 1:
        return [([], "final answer")]
    if stage_count == 2:
        return [([], "checkpoint A"), (["checkpoint A"], "final answer")]
    return [
        ([], "checkpoint A"),
        (["checkpoint A"], "checkpoint B"),
        (["checkpoint B"], "final answer"),
    ]


def validate_challenge_plan(plan: Any, category: str, difficulty: int) -> str | None:
    """Return a rejection reason, or None if the plan satisfies Python rules."""
    if not isinstance(plan, dict):
        return "planner output must be a JSON object"
    if type(plan.get("difficulty")) is not int or plan["difficulty"] != difficulty:
        return f"plan difficulty must equal requested difficulty {difficulty}"

    stages = plan.get("stages")
    if not isinstance(stages, list):
        return "plan.stages must be a JSON array"
    if type(plan.get("stage_count")) is not int or plan["stage_count"] != len(stages):
        return "stage_count must equal the number of stages in the plan"

    rules = DIFFICULTY_RULES[difficulty]
    count = len(stages)
    if not rules["min_stages"] <= count <= rules["max_stages"]:
        return (
            f"difficulty {difficulty} requires {rules['min_stages']}–{rules['max_stages']} stages; got {count}"
        )
    if rules["exact_stages"] is not None and count != rules["exact_stages"]:
        return f"difficulty {difficulty} requires exactly {rules['exact_stages']} stages; got {count}"

    expected_links = _expected_plan_outputs(count)
    canonical_mechanics: list[str] = []
    allowed_mechanics = MECHANICS_BY_CATEGORY.get(category)
    if not allowed_mechanics:
        return f"no reasoning mechanics are configured for category {category!r}"

    for index, stage in enumerate(stages, start=1):
        if not isinstance(stage, dict):
            return f"stage {index} must be a JSON object"
        if type(stage.get("stage_number")) is not int or stage["stage_number"] != index:
            return f"stage numbers must be sequential starting at 1; expected {index}"
        for field in ("mechanic", "reasoning_operation", "purpose", "produces"):
            value = stage.get(field)
            if not isinstance(value, str) or not value.strip():
                return f"stage {index} must have a non-empty {field}"
            if len(value) > (350 if field == "reasoning_operation" else 400):
                return f"stage {index} {field} is too long"

        mechanic = _normalise_label(stage["mechanic"])
        if mechanic not in allowed_mechanics:
            return (
                f"stage {index} mechanic {stage['mechanic']!r} is not an approved, category-appropriate mechanic "
                f"for {category}; choose from {sorted(allowed_mechanics)}"
            )
        canonical_mechanics.append(mechanic)

        requires = stage.get("requires")
        if not isinstance(requires, list) or any(not isinstance(item, str) for item in requires):
            return f"stage {index} requires must be an array of strings"
        normalized_requires = [_normalise_label(item) for item in requires]
        expected_requires, expected_produces = expected_links[index - 1]
        if normalized_requires != [_normalise_label(item) for item in expected_requires]:
            if index == 1:
                return "Stage 1 must not require a prior checkpoint"
            return (
                f"stage {index} must directly depend on {expected_requires[0]!r}; "
                "independent or out-of-order stages are not allowed"
            )
        if _normalise_label(stage["produces"]) != _normalise_label(expected_produces):
            return f"stage {index} must produce {expected_produces!r}"

        if difficulty == 1 and len(_operation_segments(stage["reasoning_operation"])) != 1:
            return "Level 1 must describe exactly one reasoning operation"

    operation_labels = [_normalise_label(stage["reasoning_operation"]) for stage in stages]
    if count > 1 and len(set(operation_labels)) != len(operation_labels):
        return "connected stages must use distinct reasoning operations, not repeat the same operation verbatim"

    if len(set(canonical_mechanics)) < rules["minimum_distinct_mechanics"]:
        return (
            f"difficulty {difficulty} requires at least {rules['minimum_distinct_mechanics']} distinct mechanics; "
            f"plan uses {len(set(canonical_mechanics))}"
        )

    if difficulty == 2 and count == 1:
        operation_text = stages[0]["reasoning_operation"]
        if len(_operation_segments(operation_text)) < 2:
            return "a one-stage Level 2 plan must explicitly describe at least two linked reasoning operations"

    if difficulty == 5:
        if count != 3:
            return "Level 5 must have exactly three stages"
        if _normalise_label(stages[0]["produces"]) != "checkpoint a":
            return "Level 5 Stage 1 must produce checkpoint A"
        if _normalise_label(stages[1]["produces"]) != "checkpoint b":
            return "Level 5 Stage 2 must produce checkpoint B"
        if _normalise_label(stages[2]["produces"]) != "final answer":
            return "Level 5 Stage 3 must produce the final answer"

    return None


def _build_plan_prompt(category: str, difficulty: int) -> str:
    tier = get_difficulty_tier(difficulty)
    rules = DIFFICULTY_RULES[difficulty]
    allowed = sorted(MECHANICS_BY_CATEGORY[category])
    # The illustrated JSON shape follows the requested level instead of always
    # showing a single-stage example that could bias a Level 4/5 plan downward.
    sample_count = {1: 1, 2: 2, 3: 2, 4: 3, 5: 3}[difficulty]
    sample_stages = []
    for index, (requires, produces) in enumerate(_expected_plan_outputs(sample_count), start=1):
        sample_stages.append({
            "stage_number": index,
            "mechanic": allowed[(index - 1) % len(allowed)],
            "reasoning_operation": (
                "Operation 1: combine complementary information; Operation 2: infer the unique result"
                if difficulty == 2 and sample_count == 1
                else f"perform the concrete reasoning operation for stage {index}"
            ),
            "purpose": f"establish the information needed by stage {index + 1}" if index < sample_count else "derive the final answer",
            "requires": requires,
            "produces": produces,
        })
    plan_shape = {"difficulty": difficulty, "stage_count": sample_count, "stages": sample_stages}

    return f"""You are the architecture planner for Pairza, a cooperative mystery game. Do NOT write the mystery or clues yet. Design only a compact, connected challenge plan.

REQUEST
- Category: {category}
- Difficulty selected by the admin: {difficulty}
- Gameplay time limit for the complete mystery: {tier.time_limit_minutes} minutes
- Category guidance: {CATEGORY_GUIDANCE[category]}

PYTHON-DEFINED DIFFICULTY CONTRACT (authoritative; do not reinterpret it):
{json.dumps(rules, indent=2)}

APPROVED MECHANICS FOR THIS CATEGORY:
{json.dumps(allowed, indent=2)}
Choose only exact labels from this list. Different wording for the same mechanic does not count as diversity.

STRUCTURAL DEPENDENCY CONTRACT:
- stage 1 requires []
- For a 1-stage plan, stage 1 produces "final answer".
- For a 2-stage plan, stage 1 produces "checkpoint A"; stage 2 requires ["checkpoint A"] and produces "final answer".
- For a 3-stage plan, stage 1 produces "checkpoint A"; stage 2 requires ["checkpoint A"] and produces "checkpoint B"; stage 3 requires ["checkpoint B"] and produces "final answer".
- Every later stage must genuinely use its required previous checkpoint; it cannot be an unrelated puzzle.
- A checkpoint is an intermediate result the players derive jointly from that stage's two complementary clues.
- The stage count must obey the Python-defined contract exactly. Never choose the stage count freely outside the allowed range.
- Prefer coherent cause-and-effect information flow, not three independent mini-puzzles.
- Difficulty must come from dependencies and reasoning, not long wording, obscure vocabulary, or vagueness.

Return JSON only, no markdown or commentary, using exactly this structure and the correct stage count for the selected difficulty:
{json.dumps(plan_shape, indent=2, ensure_ascii=False)}
The JSON above is a shape example. Mechanics and operations must actually fit category {category}, and the final plan must obey every dependency rule. For multi-stage plans use the required checkpoint labels and dependency arrays exactly as specified. For Level 4/5, use genuinely different mechanics wherever required. Do not include clue text, final answer, narrative, or full puzzle content.
"""


def _plan_summary(plan: dict) -> str:
    return "\n".join(
        f"  Stage {stage['stage_number']}: {stage['mechanic']} — {stage['reasoning_operation']} "
        f"[requires={stage['requires']!r}, produces={stage['produces']!r}]"
        for stage in plan["stages"]
    )


async def _generate_valid_plan(category: str, difficulty: int) -> dict:
    """Ask Gemini for a plan, validating and regenerating bad plans locally."""
    prompt = _build_plan_prompt(category, difficulty)
    last_reason = "no planning attempt completed"

    for plan_attempt in range(1, MAX_PLAN_ATTEMPTS + 1):
        try:
            response = await call_gemini(
                prompt, settings.GEMINI_API_KEY, settings.MYSTERY_GENERATOR_MODEL
            )
            plan = _extract_json(response)
        except Exception as exc:  # API/parser failure is one rejected plan attempt.
            last_reason = f"planning call or JSON parsing failed: {exc}"
            logger.warning(
                "Plan rejection (%d/%d): %s",
                plan_attempt, MAX_PLAN_ATTEMPTS, last_reason,
            )
            continue

        reason = validate_challenge_plan(plan, category, difficulty)
        if reason is None:
            logger.info("Plan valid. Stage count: %d", plan["stage_count"])
            logger.info("Selected plan mechanics:\n%s", _plan_summary(plan))
            return plan

        last_reason = reason
        logger.warning(
            "Plan rejection (%d/%d): %s",
            plan_attempt, MAX_PLAN_ATTEMPTS, reason,
        )

    raise CandidateGenerationError(
        f"plan rejected after {MAX_PLAN_ATTEMPTS} attempts: {last_reason}"
    )


def _example_to_dict(example: Mystery) -> dict[str, Any]:
    return {
        "title": example.title,
        "category": example.category,
        "difficulty": example.difficulty,
        "summary": example.summary,
        "flavor_text": example.flavor_text,
        "final_answer_patterns": example.final_answer_patterns,
        "stages": [
            {
                "stage_number": stage.stage_number,
                "is_final": stage.is_final,
                "context": stage.context,
                "checkpoint_answer_patterns": stage.checkpoint_answer_patterns,
                "clues": [
                    {"role": clue.role, "text": clue.text}
                    for clue in sorted(stage.clues, key=lambda item: item.role)
                ],
            }
            for stage in example.stages
        ],
    }


def _example_is_structurally_relevant(example: Mystery, difficulty: int) -> bool:
    """An example must have a stage architecture useful for the requested level.

    This intentionally evaluates architecture separately from the stored difficulty:
    a well-formed three-stage Level 4 example can still teach useful structure to a
    Level 5 generation, while a one-stage Level 2 example cannot.
    """
    rules = DIFFICULTY_RULES[difficulty]
    stages = list(example.stages)
    count = len(stages)

    if not rules["min_stages"] <= count <= rules["max_stages"]:
        return False
    if rules["exact_stages"] is not None and count != rules["exact_stages"]:
        return False
    if not stages or not stages[-1].is_final:
        return False
    if any(stage.is_final for stage in stages[:-1]):
        return False

    for index, stage in enumerate(stages):
        roles = {clue.role for clue in stage.clues}
        if not {"player_a", "player_b"}.issubset(roles):
            return False
        if index < count - 1 and not stage.checkpoint_answer_patterns:
            return False

    return True


def _example_structure_score(example: Mystery, difficulty: int) -> int:
    """Lower is better. Structural relevance is filtered before this score is used."""
    preferred_count = {1: 1, 2: 2, 3: 2, 4: 3, 5: 3}[difficulty]
    stage_count = len(example.stages)
    # Stage architecture is the primary consideration; once an example is
    # structurally relevant, prefer difficulty proximity and then exact shape.
    score = abs(stage_count - preferred_count) * 100
    score += abs(int(example.difficulty) - difficulty) * 12
    return score


async def _fetch_example(db: AsyncSession, category: str, difficulty: int) -> str:
    """Choose an example with useful structure; never teach Level 4/5 from a single-stage puzzle."""
    query = (
        select(Mystery)
        .options(selectinload(Mystery.stages).selectinload(MysteryStage.clues))
        .where(Mystery.is_published.is_(True), Mystery.status == "PUBLISHED")
    )
    published = list((await db.execute(query)).scalars().unique().all())
    if not published:
        logger.info("No published few-shot example available; using the plan/schema only.")
        return "(no structurally relevant published example; follow the validated plan and schema exactly)"

    category_candidates = [item for item in published if item.category == category]
    category_relevant = [
        item for item in category_candidates
        if _example_is_structurally_relevant(item, difficulty)
    ]
    all_relevant = [
        item for item in published
        if _example_is_structurally_relevant(item, difficulty)
    ]

    # Preference order: same category + exact difficulty; same category + useful
    # architecture; any category with exact difficulty + useful architecture; then
    # the structurally closest relevant example. Never fall back to an unrelated
    # one-stage example for a level that requires two or three connected stages.
    exact_category_and_difficulty = [
        item for item in category_relevant if item.difficulty == difficulty
    ]
    exact_difficulty_any_category = [
        item for item in all_relevant if item.difficulty == difficulty
    ]

    if exact_category_and_difficulty:
        pool = exact_category_and_difficulty
    elif category_relevant:
        pool = category_relevant
    elif exact_difficulty_any_category:
        pool = exact_difficulty_any_category
    elif all_relevant:
        pool = all_relevant
    else:
        logger.warning(
            "No published mystery has a structurally relevant stage chain for difficulty %d; "
            "omitting the few-shot example instead of teaching an incompatible structure.",
            difficulty,
        )
        return "(no structurally relevant published example; follow the validated plan and schema exactly)"

    best_score = min(_example_structure_score(item, difficulty) for item in pool)
    best_matches = [
        item for item in pool
        if _example_structure_score(item, difficulty) == best_score
    ]
    example = random.choice(best_matches)
    logger.info(
        "Few-shot example selected: %r (category=%s, difficulty=%s, stages=%s)%s",
        example.title,
        example.category,
        example.difficulty,
        len(example.stages),
        " [cross-category structural fallback]" if example.category != category else "",
    )
    return json.dumps(_example_to_dict(example), indent=2, ensure_ascii=False)


def _build_generation_prompt(category: str, difficulty: int, plan: dict, example: str) -> str:
    tier = get_difficulty_tier(difficulty)
    rules = DIFFICULTY_RULES[difficulty]
    # Render the correct number of stage examples from the validated plan so
    # the schema example itself never biases Level 4/5 toward one stage.
    candidate_stages = []
    for planned_stage in plan["stages"]:
        stage_number = planned_stage["stage_number"]
        is_final = stage_number == plan["stage_count"]
        candidate_stages.append({
            "stage_number": stage_number,
            "is_final": is_final,
            "context": f"Framing for stage {stage_number}; explain how the chain advances without revealing the answer.",
            "checkpoint_answer_patterns": None if is_final else [f"example checkpoint {stage_number}"],
            "mechanic": planned_stage["mechanic"],
            "reasoning_operation": planned_stage["reasoning_operation"],
            "requires_checkpoints": planned_stage["requires"],
            "clues": [
                {"role": "player_a", "text": f"Example complementary clue for player A at stage {stage_number}."},
                {"role": "player_b", "text": f"A different complementary clue for player B at stage {stage_number}."},
            ],
        })
    candidate_shape = {
        "title": "...",
        "category": category,
        "difficulty": difficulty,
        "summary": "one spoiler-free sentence",
        "flavor_text": "one atmospheric sentence",
        "final_answer_patterns": ["normalized primary answer", "optional genuine accepted variant"],
        "stages": candidate_stages,
    }
    return f"""You write original, high-quality mysteries for Pairza, a cooperative game. Two strangers each see only their own clue for a stage and must communicate to combine genuinely different information.

ADMIN REQUEST — these values are authoritative:
- Category: {category}
- Difficulty: {difficulty}
- Time limit for the WHOLE mystery: {tier.time_limit_minutes} minutes
- Category guidance: {CATEGORY_GUIDANCE[category]}
- Python-defined difficulty contract: {json.dumps(rules)}

VALIDATED CHALLENGE PLAN — implement this plan exactly; do not redesign the architecture:
{json.dumps(plan, indent=2, ensure_ascii=False)}

EXISTING PAIRZA EXAMPLE (for format and tone only; do not copy its title, answers, clues, scenario, or distinctive wording):
{example}

CONTENT AND STRUCTURE REQUIREMENTS:
- Use exactly {plan['stage_count']} stages as specified by the validated plan; stage numbers must be sequential from 1.
- Return exactly one player_a clue and one player_b clue per stage. They must provide genuinely different, complementary information; neither clue alone should solve that stage.
- Implement each planned mechanic and reasoning operation. Do not replace a planned operation with a simpler riddle.
- Every non-final stage must have non-empty checkpoint_answer_patterns that contains the jointly derived checkpoint accepted for that stage. The following stage must actually need that checkpoint to proceed.
- Every stage must include validation metadata copied exactly from the matching plan stage: "mechanic" must copy the plan mechanic label, "reasoning_operation" must copy the plan reasoning_operation text exactly, and "requires_checkpoints" must copy the plan's "requires" array exactly.
- These metadata fields are validated before save and are not stored as database columns; do not omit them.
- Stage 1 must have requires_checkpoints=[]. Stage 2 in a multi-stage challenge requires ["checkpoint A"]. Stage 3 requires ["checkpoint B"].
- The final stage is the last stage, has is_final=true, and checkpoint_answer_patterns=null. Every earlier stage has is_final=false.
- A one-stage Level 1 must require one reasoning operation and no checkpoint. Level 2 must require more reasoning than Level 1. Levels 3–5 must follow the dependencies in the supplied plan.
- For Level 5, Stage 1 yields checkpoint A, Stage 2 transforms/uses A to produce checkpoint B, and Stage 3 requires B to derive the final answer. The final answer must not be inferable from the initial clues alone. These must be one chain, not three unrelated puzzles.
- Keep checkpoint and final answers normalized, concise, and unambiguous. Include only genuine accepted variants in answer-pattern arrays.
- CRITICAL ANSWER-LEAK AUDIT: after drafting the mystery, compare every checkpoint_answer_patterns value with both clues of its own non-final stage, and compare every final_answer_patterns value with every clue in every stage. If any normalized answer phrase appears verbatim or as a contiguous phrase in a clue, rewrite that clue before returning JSON. Do not change the answer merely to evade the check.
- Choose checkpoint/final answers that can be derived from evidence without being printed verbatim in that evidence. Avoid using a named person, object, or phrase as a checkpoint if the clue text needs to state that exact answer. Prefer a derived relationship, ordered pair, code, extracted sequence, or other concise result that can be implied without being copied into a clue.
- Never quote, repeat, spell out, or include the full accepted answer inside a clue, even as part of an illustrative sentence, witness statement, option list, or narrative context. This applies to all accepted variants, not only the primary answer.
- Before returning, run a final self-check over all answer-pattern arrays and all clue texts. A candidate that leaks an answer is invalid; rewrite the clue and recheck rather than returning an invalid candidate.
- Avoid ambiguity, accidental alternate solutions, factual claims that are not necessary, hidden assumptions, obscure wording, and difficulty created solely by lengthy text.
- Keep clues concise and atmospheric. The entire mystery must be realistically solvable by two strangers within the time limit.
- Return the established MysteryCandidate content fields plus the optional validation metadata fields shown below: mechanic, reasoning_operation, and requires_checkpoints. These metadata fields are not stored in PostgreSQL, but are required by the validator.

Return ONLY one JSON object (no markdown or extra text), matching this complete shape for the requested number of stages:
{json.dumps(candidate_shape, indent=2, ensure_ascii=False)}
For each stage, copy mechanic, reasoning_operation, and requires_checkpoints from the same numbered plan stage. For a final-only Level 1 stage, set is_final=true, checkpoint_answer_patterns=null, and requires_checkpoints=[]. For every other final stage set is_final=true and checkpoint_answer_patterns=null. Make the response conform to the supplied plan and candidate schema.
"""


async def _generate_candidate_with_plan(
    db: AsyncSession, category: str, difficulty: int
) -> tuple[dict, dict]:
    logger.info("Generating %r difficulty %d...", category, difficulty)
    plan = await _generate_valid_plan(category, difficulty)
    example = await _fetch_example(db, category, difficulty)
    prompt = _build_generation_prompt(category, difficulty, plan, example)
    raw_response = await call_gemini(
        prompt, settings.GEMINI_API_KEY, settings.MYSTERY_GENERATOR_MODEL
    )
    raw = _extract_json(raw_response)
    if not isinstance(raw, dict):
        raise CandidateGenerationError("generation returned JSON that is not an object")
    # Make the plan visible to the validator instead of keeping it as hidden
    # generator state. Pydantic ignores this top-level validation metadata, and
    # it is not persisted; validate_mystery.py checks consistency when present.
    raw["_challenge_plan"] = plan
    return raw, plan


async def generate_one_candidate(db: AsyncSession, category: str, difficulty: int) -> dict:
    """Backward-compatible entry point: generate and return one candidate JSON dict."""
    raw, _plan = await _generate_candidate_with_plan(db, category, difficulty)
    return raw


def validate_generated_structure(
    raw: Any, category: str, difficulty: int, plan: dict
) -> tuple[MysteryCandidate | None, str | None]:
    """Deterministically ensure the generated JSON implements the requested plan."""
    if not isinstance(raw, dict):
        return None, "generated output must be a JSON object"
    try:
        candidate = MysteryCandidate.model_validate(raw)
    except ValidationError as exc:
        first_error = exc.errors()[0]
        return None, f"MysteryCandidate schema validation failed: {first_error.get('msg', 'invalid shape')}"

    if candidate.category != category:
        return None, f"generated category {candidate.category!r} differs from requested {category!r}"
    if candidate.difficulty != difficulty:
        return None, f"generated difficulty {candidate.difficulty} differs from requested {difficulty}"
    if len(candidate.stages) != plan["stage_count"]:
        return None, (
            f"generated stage count {len(candidate.stages)} does not match validated plan "
            f"({plan['stage_count']})"
        )

    rules = DIFFICULTY_RULES[difficulty]
    count = len(candidate.stages)
    if not rules["min_stages"] <= count <= rules["max_stages"]:
        return None, f"difficulty {difficulty} does not permit {count} stages"
    if rules["exact_stages"] is not None and count != rules["exact_stages"]:
        return None, f"difficulty {difficulty} requires exactly {rules['exact_stages']} stages"

    stage_numbers = [stage.stage_number for stage in candidate.stages]
    if stage_numbers != list(range(1, count + 1)):
        return None, f"stage numbers are not sequential: {stage_numbers}"
    final_stages = [stage.stage_number for stage in candidate.stages if stage.is_final]
    if final_stages != [count]:
        return None, f"only the final stage (stage {count}) may be marked is_final; got {final_stages}"

    final_answers = {
        normalize_answer(value) for value in candidate.final_answer_patterns if normalize_answer(value)
    }
    if not final_answers:
        return None, "final_answer_patterns must contain at least one non-empty answer"

    for index, stage in enumerate(candidate.stages):
        plan_stage = plan["stages"][index]
        expected_final = index == count - 1
        if not stage.mechanic or stage.mechanic.strip().casefold().replace("_", " ").replace("-", " ") != plan_stage["mechanic"].strip().casefold().replace("_", " ").replace("-", " "):
            return None, f"stage {index + 1} mechanic does not match the validated challenge plan"
        if not stage.reasoning_operation or stage.reasoning_operation.strip() != plan_stage["reasoning_operation"].strip():
            return None, f"stage {index + 1} reasoning_operation does not match the validated challenge plan"
        if [item.strip().casefold() for item in stage.requires_checkpoints] != [item.strip().casefold() for item in plan_stage["requires"]]:
            return None, f"stage {index + 1} requires_checkpoints does not match the validated challenge plan"
        if stage.is_final != expected_final:
            return None, f"stage {stage.stage_number} has incorrect is_final value"
        if expected_final:
            if stage.checkpoint_answer_patterns is not None:
                return None, f"final stage {stage.stage_number} must have checkpoint_answer_patterns=null"
        else:
            if not stage.checkpoint_answer_patterns or not any(
                normalize_answer(value) for value in stage.checkpoint_answer_patterns
            ):
                return None, f"non-final stage {stage.stage_number} must provide checkpoint_answer_patterns"
            checkpoint_answers = {
                normalize_answer(value) for value in stage.checkpoint_answer_patterns if normalize_answer(value)
            }
            if checkpoint_answers & final_answers:
                return None, f"stage {stage.stage_number} checkpoint answer duplicates a final answer"

        roles = [clue.role for clue in stage.clues]
        if sorted(roles) != ["player_a", "player_b"]:
            return None, f"stage {stage.stage_number} must have exactly one clue for each player role"
        clue_texts = {clue.role: normalize_answer(clue.text) for clue in stage.clues}
        if clue_texts["player_a"] == clue_texts["player_b"]:
            return None, f"stage {stage.stage_number} has identical player clues"

        # Reject literal checkpoint leaks in the stage that is supposed to
        # generate that checkpoint. Whole-answer leakage is also checked by
        # the existing validate_mystery() pipeline.
        if not expected_final:
            for answer in stage.checkpoint_answer_patterns or []:
                normalized_answer = normalize_answer(answer)
                if normalized_answer and any(normalized_answer in text for text in clue_texts.values()):
                    return None, f"stage {stage.stage_number} clue contains its literal checkpoint answer {normalized_answer!r}"

    return candidate, None



async def save_mystery(db: AsyncSession, candidate: MysteryCandidate, auto_publish: bool) -> None:
    """Persist a fully validated candidate using the existing Pairza schema."""
    status = "PUBLISHED" if auto_publish else "VALIDATED"
    mystery = Mystery(
        title=candidate.title,
        category=candidate.category,
        difficulty=candidate.difficulty,
        summary=candidate.summary,
        flavor_text=candidate.flavor_text,
        final_answer_patterns=candidate.final_answer_patterns,
        is_published=auto_publish,
        status=status,
        generator_version=f"{settings.MYSTERY_GENERATOR_MODEL}:{GENERATOR_VERSION_PREFIX}",
    )
    db.add(mystery)
    await db.flush()
    for stage_candidate in candidate.stages:
        stage = MysteryStage(
            mystery_id=mystery.id,
            stage_number=stage_candidate.stage_number,
            is_final=stage_candidate.is_final,
            context=stage_candidate.context,
            checkpoint_answer_patterns=stage_candidate.checkpoint_answer_patterns,
        )
        db.add(stage)
        await db.flush()
        for clue_candidate in stage_candidate.clues:
            db.add(
                MysteryClue(
                    stage_id=stage.id,
                    role=clue_candidate.role,
                    text=clue_candidate.text,
                )
            )
    await db.commit()


async def generate_for_category(
    db: AsyncSession,
    category: str,
    quantity: int,
    difficulty: int | None,
    dry_run: bool,
) -> dict:
    stats: dict[str, Any] = {
        "category": category,
        "requested": quantity,
        "attempts": 0,
        "rejected": 0,
        "valid": 0,
        "saved": 0,
        "rejections": [],
    }

    if not settings.GEMINI_API_KEY:
        stats["rejections"].append("GEMINI_API_KEY is not configured — see .env.example.")
        return stats
    if quantity <= 0:
        stats["rejections"].append("Quantity must be greater than zero.")
        return stats

    accepted = 0
    max_total_attempts = quantity * MAX_ATTEMPTS_PER_MYSTERY
    while accepted < quantity and stats["attempts"] < max_total_attempts:
        stats["attempts"] += 1
        this_difficulty = difficulty if difficulty is not None else random.randint(MIN_DIFFICULTY, MAX_DIFFICULTY)
        logger.info(
            "Attempt %d/%d — requested category=%s difficulty=%d",
            stats["attempts"], max_total_attempts, category, this_difficulty,
        )
        try:
            raw, plan = await _generate_candidate_with_plan(db, category, this_difficulty)
        except Exception as exc:  # noqa: BLE001 — a rejected candidate must not abort the batch
            await db.rollback()
            stats["rejected"] += 1
            reason = f"Attempt {stats['attempts']} (planning/generation): {exc}"
            stats["rejections"].append(reason)
            logger.warning("Candidate rejected: %s", reason)
            continue

        candidate, structural_reason = validate_generated_structure(
            raw, category, this_difficulty, plan
        )
        if structural_reason or candidate is None:
            await db.rollback()
            stats["rejected"] += 1
            reason = f"Attempt {stats['attempts']} (generated structure): {structural_reason or 'invalid candidate'}"
            stats["rejections"].append(reason)
            logger.warning("Candidate rejected: %s", reason)
            continue

        try:
            validated_candidate, result = await validate_mystery(
                db, raw, settings.GEMINI_API_KEY, settings.MYSTERY_GENERATOR_MODEL
            )
        except Exception as exc:  # noqa: BLE001
            await db.rollback()
            stats["rejected"] += 1
            reason = f"Attempt {stats['attempts']} (existing validation pipeline): {exc}"
            stats["rejections"].append(reason)
            logger.warning("Candidate rejected: %s", reason)
            continue

        if not result.is_valid or validated_candidate is None:
            await db.rollback()
            stats["rejected"] += 1
            reason = f"Attempt {stats['attempts']} ({result.stage}): {result.reason or 'validation failed'}"
            stats["rejections"].append(reason)
            logger.warning("Candidate rejected: %s", reason)
            continue

        stats["valid"] += 1
        if dry_run:
            logger.info("Candidate accepted by all validators (dry run; not saved).")
        else:
            try:
                await save_mystery(db, validated_candidate, settings.MYSTERY_AUTO_PUBLISH)
            except Exception as exc:  # noqa: BLE001 — rollback before retrying on DB issues
                await db.rollback()
                stats["rejected"] += 1
                reason = f"Attempt {stats['attempts']} (database save): {exc}"
                stats["rejections"].append(reason)
                logger.exception("Candidate save failed; rolled back candidate transaction.")
                continue
            stats["saved"] += 1
            logger.info("Candidate accepted and saved: %r", validated_candidate.title)
        accepted += 1

    if accepted < quantity:
        logger.warning(
            "Could generate only %d/%d valid candidate(s) for category=%s within %d attempts.",
            accepted, quantity, category, max_total_attempts,
        )
    return stats


def _print_report(all_stats: list[dict]) -> None:
    print()
    print(f"{'Category':<16} {'Requested':>10} {'Attempts':>10} {'Rejected':>10} {'Valid':>8} {'Saved':>8}")
    print("-" * 66)
    for stats in all_stats:
        print(
            f"{stats['category']:<16} {stats['requested']:>10} {stats['attempts']:>10} "
            f"{stats['rejected']:>10} {stats['valid']:>8} {stats['saved']:>8}"
        )
    print()
    for stats in all_stats:
        if stats["rejections"]:
            print(f"--- {stats['category']} rejections ---")
            for rejection in stats["rejections"]:
                print(f"  {rejection}")
    print()


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate Pairza mysteries with plan-first AI generation and full validation."
    )
    parser.add_argument("--category", choices=MYSTERY_CATEGORIES, help="Generate for one specific category.")
    parser.add_argument(
        "--all-categories", action="store_true",
        help="Generate for every category in MYSTERY_CATEGORIES.",
    )
    parser.add_argument(
        "--quantity", type=int, default=5,
        help="How many VALID mysteries to save per category (default 5).",
    )
    parser.add_argument(
        "--difficulty", type=int, choices=sorted(DIFFICULTY_TIERS),
        help="Fix difficulty instead of randomizing per mystery.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Generate and validate but save nothing.")
    args = parser.parse_args()

    if not args.category and not args.all_categories:
        parser.error("Specify either --category <name> or --all-categories.")
    if args.quantity < 1:
        parser.error("--quantity must be at least 1.")

    categories = MYSTERY_CATEGORIES if args.all_categories else [args.category]
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    all_stats = []
    async with AsyncSessionLocal() as db:
        for category in categories:
            print(f"Generating for '{category}'...")
            stats = await generate_for_category(db, category, args.quantity, args.difficulty, args.dry_run)
            all_stats.append(stats)

    _print_report(all_stats)


if __name__ == "__main__":
    asyncio.run(main())
