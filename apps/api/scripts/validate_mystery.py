"""Validate Pairza mystery candidates before they can be saved.

Pipeline (cheapest first):
  1. Pydantic schema parsing
  2. deterministic difficulty/stage/dependency/mechanic checks
  3. validate an embedded challenge plan when supplied
  4. duplicate detection (one database query)
  5. per-stage semantic Gemini validation
  6. whole-mystery semantic Gemini validation

Validation-only metadata (mechanic, reasoning_operation, requires_checkpoints) is
part of MysteryCandidate.StageCandidate but is intentionally not persisted to the
production database. It gives the generator and standalone validator enough
explicit evidence to enforce architecture without adding database columns.

CLI remains compatible:
    python -m scripts.validate_mystery path/to/candidate.json
    python -m scripts.validate_mystery path/to/candidate.json --skip-semantic
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.gemini import call_gemini
from app.config.settings import get_settings
from app.mysteries.difficulty import get_difficulty_tier
from app.mysteries.models import MYSTERY_CATEGORIES, Mystery
from app.mysteries.schemas import MysteryCandidate
from app.mysteries.service import normalize_answer

settings = get_settings()

# Existing per-stage threshold intentionally remains unchanged. Difficulty is
# enforced by independent deterministic rules and a separate whole-mystery review.
SEMANTIC_CONFIDENCE_THRESHOLD = 70
WHOLE_MYSTERY_THRESHOLD = 80
DIFFICULTY_MATCH_THRESHOLD = 80
DEPENDENCY_THRESHOLD = 80
REASONING_DEPTH_THRESHOLD = 80
MECHANIC_DIVERSITY_THRESHOLD = 80
NON_SKIPPABLE_THRESHOLD = 80

DIFFICULTY_RULES: dict[int, dict[str, Any]] = {
    1: {
        "min_stages": 1, "max_stages": 1, "exact_stages": 1,
        "min_distinct_mechanics": 1, "min_operations": 1,
        "requires_dependency": False,
    },
    2: {
        "min_stages": 1, "max_stages": 2, "exact_stages": None,
        "min_distinct_mechanics": 1, "min_operations": 2,
        "requires_dependency": False,
    },
    3: {
        "min_stages": 2, "max_stages": 2, "exact_stages": 2,
        "min_distinct_mechanics": 1, "min_operations": 2,
        "requires_dependency": True,
    },
    4: {
        "min_stages": 2, "max_stages": 3, "exact_stages": None,
        "min_distinct_mechanics": 2, "min_operations": 2,
        "requires_dependency": True,
    },
    5: {
        "min_stages": 3, "max_stages": 3, "exact_stages": 3,
        "min_distinct_mechanics": 3, "min_operations": 3,
        "requires_dependency": True,
    },
}

# Keep these labels aligned with the plan-first generator's approved labels.
# Values are normalized at comparison time so underscores/hyphens are harmless.
CATEGORY_MECHANICS: dict[str, set[str]] = {
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

# Superficial names collapse to one canonical mechanic. In particular,
# adjectives such as "advanced" or "complex" do not create new mechanics.
MECHANIC_ALIASES = {
    "logical deduction": "deduction",
    "advanced deduction": "deduction",
    "complex deduction": "deduction",
    "harder deduction": "deduction",
    "pattern extraction": "pattern recognition",
    "pattern finding": "pattern recognition",
    "pattern detection": "pattern recognition",
    "cross reference": "cross reference",
    "cross referencing": "cross reference",
    "sequence analysis": "sequence reconstruction",
    "cipher decoding": "cipher decoding",
    "decoding cipher": "cipher decoding",
    "evidence correlation": "evidence correlation",
}

BANNED_GENERIC_OPERATIONS = {
    "deduction", "harder deduction", "advanced deduction", "complex deduction",
    "think carefully", "use logic", "solve the puzzle", "reason about the clues",
}


@dataclass
class ValidationResult:
    is_valid: bool
    stage: str  # structure/difficulty/dependency/mechanic/duplicate/semantic/whole_mystery
    reason: str | None = None
    warnings: list[str] = field(default_factory=list)

    @staticmethod
    def ok(stage: str, warnings: list[str] | None = None) -> "ValidationResult":
        return ValidationResult(is_valid=True, stage=stage, warnings=warnings or [])

    @staticmethod
    def fail(stage: str, reason: str) -> "ValidationResult":
        return ValidationResult(is_valid=False, stage=stage, reason=reason)


def _extract_json(text: str) -> dict:
    """Recover a JSON object from a response, tolerating accidental code fences."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object found in model response: {text[:200]!r}")
    parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise ValueError("Gemini response JSON must be an object")
    return parsed


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().casefold())


def _norm_label(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().casefold().replace("_", " ").replace("-", " "))


def _canonical_mechanic(value: Any) -> str:
    normalized = _norm_label(value)
    return MECHANIC_ALIASES.get(normalized, normalized)


def _operation_segments(value: str) -> list[str]:
    """Split explicitly chained operations; avoid treating a single operation's
    ordinary conjunction (e.g. 'cross-reference A and B') as two operations."""
    pieces = re.split(
        r";|\n|\s*(?:→|->)\s*|\bthen\b|\bafter that\b|\bfollowed by\b|\bnext,?\b",
        value,
        flags=re.IGNORECASE,
    )
    return [part.strip(" .:-\t\n") for part in pieces if part.strip(" .:-\t\n")]


def _contains_phrase(text: str, phrase: str) -> bool:
    """Phrase check on token boundaries, avoiding false leaks such as 'at' in 'late'."""
    normalized_text = f" {normalize_answer(text)} "
    normalized_phrase = f" {normalize_answer(phrase)} "
    return bool(normalize_answer(phrase)) and normalized_phrase in normalized_text


def _expected_checkpoint_requirements(stage_count: int) -> list[list[str]]:
    """Expected validation metadata for a single connected chain."""
    if stage_count == 1:
        return [[]]
    if stage_count == 2:
        return [[], ["checkpoint A"]]
    if stage_count == 3:
        return [[], ["checkpoint A"], ["checkpoint B"]]
    return []


def _expected_plan_links(stage_count: int) -> list[tuple[list[str], str]]:
    if stage_count == 1:
        return [([], "final answer")]
    if stage_count == 2:
        return [([], "checkpoint A"), (["checkpoint A"], "final answer")]
    if stage_count == 3:
        return [
            ([], "checkpoint A"),
            (["checkpoint A"], "checkpoint B"),
            (["checkpoint B"], "final answer"),
        ]
    return []


def validate_difficulty_structure(candidate: MysteryCandidate) -> ValidationResult:
    difficulty = candidate.difficulty
    rules = DIFFICULTY_RULES.get(difficulty)
    if rules is None:
        return ValidationResult.fail("difficulty", f"Unsupported difficulty {difficulty!r}; expected 1–5.")

    count = len(candidate.stages)
    if rules["exact_stages"] is not None and count != rules["exact_stages"]:
        return ValidationResult.fail(
            "difficulty", f"Difficulty {difficulty} requires exactly {rules['exact_stages']} stages, got {count}."
        )
    if not rules["min_stages"] <= count <= rules["max_stages"]:
        return ValidationResult.fail(
            "difficulty",
            f"Difficulty {difficulty} requires {rules['min_stages']}–{rules['max_stages']} stages, got {count}.",
        )
    if difficulty == 5 and count != 3:
        return ValidationResult.fail("difficulty", f"Difficulty 5 requires exactly 3 stages, got {count}.")
    if difficulty == 4 and count < 2:
        return ValidationResult.fail("difficulty", "Difficulty 4 requires at least 2 stages.")
    return ValidationResult.ok("difficulty")


def validate_stage_structure(candidate: MysteryCandidate) -> ValidationResult:
    stages = candidate.stages
    stage_numbers = [stage.stage_number for stage in stages]
    if stage_numbers != list(range(1, len(stages) + 1)):
        return ValidationResult.fail(
            "stage_structure", f"Stage numbers must be sequential starting at 1, got {stage_numbers}."
        )

    final_stages = [stage.stage_number for stage in stages if stage.is_final]
    if final_stages != [len(stages)]:
        return ValidationResult.fail(
            "stage_structure",
            f"Exactly the last stage must be final; expected [{len(stages)}], got {final_stages}.",
        )

    normalized_final_answers = {
        normalize_answer(answer) for answer in candidate.final_answer_patterns if normalize_answer(answer)
    }
    if not normalized_final_answers:
        return ValidationResult.fail("stage_structure", "final_answer_patterns must contain a non-empty answer.")

    if any(not isinstance(answer, str) or not normalize_answer(answer) for answer in candidate.final_answer_patterns):
        return ValidationResult.fail("stage_structure", "final_answer_patterns contains an empty or invalid value.")

    warnings: list[str] = []
    if len(normalized_final_answers) != len(candidate.final_answer_patterns):
        warnings.append("final_answer_patterns has duplicate entries after normalization.")

    checkpoint_sets: list[set[str]] = []
    for stage in stages:
        roles = sorted(clue.role for clue in stage.clues)
        if roles != ["player_a", "player_b"]:
            return ValidationResult.fail(
                "stage_structure",
                f"Stage {stage.stage_number} must have exactly one player_a and one player_b clue, got {roles}.",
            )

        clue_by_role = {clue.role: clue.text for clue in stage.clues}
        if normalize_answer(clue_by_role["player_a"]) == normalize_answer(clue_by_role["player_b"]):
            return ValidationResult.fail(
                "stage_structure",
                f"Stage {stage.stage_number}'s two clues are identical after normalization.",
            )

        if stage.is_final:
            if stage.checkpoint_answer_patterns is not None:
                return ValidationResult.fail(
                    "stage_structure",
                    f"Final stage {stage.stage_number} must have checkpoint_answer_patterns=null.",
                )
        else:
            answers = stage.checkpoint_answer_patterns
            if not answers or any(not isinstance(answer, str) or not normalize_answer(answer) for answer in answers):
                return ValidationResult.fail(
                    "stage_structure",
                    f"Stage {stage.stage_number} is non-final and must have non-empty checkpoint_answer_patterns.",
                )
            normalized_checkpoints = {normalize_answer(answer) for answer in answers}
            if normalized_checkpoints & normalized_final_answers:
                return ValidationResult.fail(
                    "stage_structure",
                    f"Stage {stage.stage_number} checkpoint answer duplicates a final answer.",
                )
            checkpoint_sets.append(normalized_checkpoints)

        # Final-answer leaks are checked on every clue using whole-phrase boundaries.
        for role, clue_text in clue_by_role.items():
            for answer in normalized_final_answers:
                if _contains_phrase(clue_text, answer):
                    return ValidationResult.fail(
                        "stage_structure",
                        f"Stage {stage.stage_number} {role} clue exposes the literal final answer {answer!r}.",
                    )

        # A checkpoint must not be printed verbatim in the clues of the stage
        # whose job is to derive it.
        if not stage.is_final:
            for answer in stage.checkpoint_answer_patterns or []:
                if any(_contains_phrase(clue_text, answer) for clue_text in clue_by_role.values()):
                    return ValidationResult.fail(
                        "stage_structure",
                        f"Stage {stage.stage_number} clue exposes its literal checkpoint answer {normalize_answer(answer)!r}.",
                    )

    # Checkpoints must represent different intermediate results, not aliases.
    for left_index, left in enumerate(checkpoint_sets):
        for right_index in range(left_index + 1, len(checkpoint_sets)):
            if left & checkpoint_sets[right_index]:
                return ValidationResult.fail(
                    "stage_structure",
                    "Two non-final stages reuse the same checkpoint answer; the chain does not progress.",
                )

    return ValidationResult.ok("stage_structure", warnings)


def validate_stage_dependencies(candidate: MysteryCandidate) -> ValidationResult:
    stages = candidate.stages
    expected_by_stage = _expected_checkpoint_requirements(len(stages))
    if not expected_by_stage:
        return ValidationResult.fail("dependency", f"Unsupported stage count {len(stages)} for a connected challenge.")

    for index, stage in enumerate(stages):
        actual = [_norm_label(item) for item in (stage.requires_checkpoints or [])]
        expected = [_norm_label(item) for item in expected_by_stage[index]]
        if actual != expected:
            if index == 0:
                return ValidationResult.fail(
                    "dependency", "Stage 1 must not require a checkpoint from a previous stage."
                )
            prior_stage = index
            prior_checkpoint = "checkpoint A" if prior_stage == 1 else "checkpoint B"
            return ValidationResult.fail(
                "dependency",
                f"Stage {index + 1} must require {prior_checkpoint} from Stage {index}; "
                f"expected requires_checkpoints={expected_by_stage[index]!r}, got {stage.requires_checkpoints!r}.",
            )

    # The StageCandidate model defaults absent metadata to [], so the expected
    # non-empty dependency above also catches legacy candidates that omit it.
    return ValidationResult.ok("dependency")


def validate_mechanics_and_reasoning(candidate: MysteryCandidate) -> ValidationResult:
    difficulty = candidate.difficulty
    rules = DIFFICULTY_RULES[difficulty]
    allowed_raw = CATEGORY_MECHANICS.get(candidate.category)
    if not allowed_raw:
        return ValidationResult.fail("mechanic", f"No approved mechanics configured for category {candidate.category!r}.")
    allowed = {_canonical_mechanic(item) for item in allowed_raw}

    canonical_mechanics: list[str] = []
    operations: list[str] = []
    operation_segment_count = 0

    for stage in candidate.stages:
        if not stage.mechanic or not str(stage.mechanic).strip():
            return ValidationResult.fail(
                "mechanic",
                f"Stage {stage.stage_number} is missing mechanic metadata; deterministic difficulty validation requires it.",
            )
        mechanic = _canonical_mechanic(stage.mechanic)
        if mechanic not in allowed:
            return ValidationResult.fail(
                "mechanic",
                f"Stage {stage.stage_number} mechanic {stage.mechanic!r} is not an approved, category-appropriate mechanic for {candidate.category}.",
            )
        canonical_mechanics.append(mechanic)

        if not stage.reasoning_operation or not str(stage.reasoning_operation).strip():
            return ValidationResult.fail(
                "mechanic",
                f"Stage {stage.stage_number} is missing reasoning_operation metadata.",
            )
        segments = _operation_segments(stage.reasoning_operation)
        if not segments:
            return ValidationResult.fail(
                "mechanic", f"Stage {stage.stage_number} must describe at least one concrete reasoning operation."
            )
        for operation in segments:
            normalized_operation = _norm_label(operation)
            if normalized_operation in BANNED_GENERIC_OPERATIONS or len(normalized_operation.split()) < 3:
                return ValidationResult.fail(
                    "mechanic",
                    f"Stage {stage.stage_number} reasoning operation {operation!r} is too generic to establish difficulty.",
                )
            operations.append(normalized_operation)
        operation_segment_count += len(segments)

        if difficulty == 1 and len(segments) != 1:
            return ValidationResult.fail(
                "mechanic", "Difficulty 1 must use exactly one core reasoning operation in its single stage."
            )

    distinct_mechanics = set(canonical_mechanics)
    if len(distinct_mechanics) < rules["min_distinct_mechanics"]:
        return ValidationResult.fail(
            "mechanic",
            f"Difficulty {difficulty} requires at least {rules['min_distinct_mechanics']} meaningfully different mechanics; "
            f"got {len(distinct_mechanics)}.",
        )

    distinct_operations = set(operations)
    if operation_segment_count < rules["min_operations"] or len(distinct_operations) < rules["min_operations"]:
        return ValidationResult.fail(
            "mechanic",
            f"Difficulty {difficulty} requires at least {rules['min_operations']} meaningful reasoning operations; "
            f"found {operation_segment_count} operation segment(s) and {len(distinct_operations)} distinct operation(s).",
        )

    if difficulty == 2 and len(candidate.stages) == 1 and operation_segment_count < 2:
        return ValidationResult.fail(
            "mechanic", "A one-stage Difficulty 2 mystery must explicitly chain at least two reasoning operations."
        )

    # Reusing the identical operation description is a strong structural signal
    # that later stages may merely repeat earlier work. Semantic review still
    # judges whether differently described operations are genuinely different.
    if difficulty >= 3 and len(distinct_operations) < min(rules["min_operations"], len(candidate.stages)):
        return ValidationResult.fail(
            "mechanic", f"Difficulty {difficulty} does not demonstrate sufficient reasoning-operation progression."
        )
    return ValidationResult.ok("mechanic")


def validate_embedded_plan(raw: Any, candidate: MysteryCandidate) -> ValidationResult:
    """Validate optional planner metadata when present, without requiring it.

    Standalone candidates remain independently validated from their own stage
    metadata. When a generator supplies `_challenge_plan`, verify it agrees with
    the candidate instead of trusting hidden, out-of-band generator state.
    """
    if not isinstance(raw, dict):
        return ValidationResult.ok("plan")
    plan = raw.get("_challenge_plan") or raw.get("challenge_plan") or raw.get("plan")
    if plan is None:
        return ValidationResult.ok("plan")
    if not isinstance(plan, dict):
        return ValidationResult.fail("plan", "Embedded challenge plan must be a JSON object.")
    if plan.get("difficulty") != candidate.difficulty:
        return ValidationResult.fail("plan", "Embedded challenge-plan difficulty differs from the candidate difficulty.")
    stages = plan.get("stages")
    if not isinstance(stages, list) or len(stages) != len(candidate.stages):
        return ValidationResult.fail("plan", "Embedded challenge-plan stage count differs from the candidate.")
    if plan.get("stage_count") != len(stages):
        return ValidationResult.fail("plan", "Embedded challenge-plan stage_count is inconsistent.")

    expected_links = _expected_plan_links(len(stages))
    for index, (plan_stage, candidate_stage) in enumerate(zip(stages, candidate.stages), start=1):
        if not isinstance(plan_stage, dict) or plan_stage.get("stage_number") != index:
            return ValidationResult.fail("plan", f"Embedded plan stage numbers are not sequential at stage {index}.")
        expected_requires, expected_produces = expected_links[index - 1]
        actual_requires = plan_stage.get("requires")
        if not isinstance(actual_requires, list) or [_norm_label(x) for x in actual_requires] != [_norm_label(x) for x in expected_requires]:
            return ValidationResult.fail(
                "plan", f"Embedded plan Stage {index} violates the required checkpoint dependency chain."
            )
        if _norm_label(plan_stage.get("produces")) != _norm_label(expected_produces):
            return ValidationResult.fail(
                "plan", f"Embedded plan Stage {index} must produce {expected_produces!r}."
            )
        planned_mechanic = _canonical_mechanic(plan_stage.get("mechanic"))
        if planned_mechanic != _canonical_mechanic(candidate_stage.mechanic):
            return ValidationResult.fail(
                "plan", f"Stage {index} mechanic does not match the validated challenge plan."
            )
        planned_operation = _norm_label(plan_stage.get("reasoning_operation"))
        candidate_operation = _norm_label(candidate_stage.reasoning_operation)
        if not planned_operation or planned_operation != candidate_operation:
            return ValidationResult.fail(
                "plan", f"Stage {index} reasoning_operation does not match the validated challenge plan."
            )
        candidate_requires = [_norm_label(x) for x in (candidate_stage.requires_checkpoints or [])]
        if candidate_requires != [_norm_label(x) for x in expected_requires]:
            return ValidationResult.fail(
                "plan", f"Stage {index} requires_checkpoints does not match the validated challenge plan."
            )
    return ValidationResult.ok("plan")


def validate_structure(raw: Any) -> tuple[MysteryCandidate | None, ValidationResult]:
    """Pydantic validation followed by all cheap deterministic architecture checks."""
    try:
        candidate = MysteryCandidate.model_validate(raw)
    except ValidationError as exc:
        errors = exc.errors()
        first = errors[0] if errors else {"msg": "invalid candidate"}
        return None, ValidationResult.fail("structure", f"Schema validation failed: {first.get('msg', 'invalid shape')}.")
    except (TypeError, ValueError) as exc:
        return None, ValidationResult.fail("structure", f"Schema validation failed: {exc}")

    checks = (
        validate_difficulty_structure(candidate),
        validate_stage_structure(candidate),
        validate_stage_dependencies(candidate),
        validate_mechanics_and_reasoning(candidate),
        validate_embedded_plan(raw, candidate),
    )
    warnings: list[str] = []
    for result in checks:
        if not result.is_valid:
            return candidate, result
        warnings.extend(result.warnings)
    return candidate, ValidationResult.ok("structure", warnings)


# --- Duplicate detection: deterministic, one DB query ---

async def check_duplicates(db: AsyncSession, candidate: MysteryCandidate) -> ValidationResult:
    """Reject duplicate normalized titles or same-category accepted answers."""
    normalized_title = normalize_answer(candidate.title)
    normalized_answers = {normalize_answer(a) for a in candidate.final_answer_patterns}
    existing_rows = (
        await db.execute(select(Mystery.title, Mystery.category, Mystery.final_answer_patterns))
    ).all()

    for existing_title, existing_category, existing_answers in existing_rows:
        if normalize_answer(existing_title) == normalized_title:
            return ValidationResult.fail("duplicate", f"Title duplicates an existing mystery: '{existing_title}'.")
        if existing_category == candidate.category:
            existing_normalized_answers = {normalize_answer(a) for a in existing_answers}
            overlap = normalized_answers & existing_normalized_answers
            if overlap:
                return ValidationResult.fail(
                    "duplicate",
                    f"Shares accepted answer {sorted(overlap)!r} with an existing {existing_category} mystery ('{existing_title}').",
                )
    return ValidationResult.ok("duplicate")


# --- Per-stage semantic validation: preserve existing review behavior ---

SEMANTIC_VALIDATION_PROMPT = """You are a strict quality reviewer for a two-player puzzle game called Pairza. Two strangers each see only one complementary clue and must combine their information.

Category: {category}
Difficulty (1=gentle, 5=expert): {difficulty} — {difficulty_style}
Time limit for the WHOLE mystery: {time_limit_minutes} minutes
Stage number: {stage_number}
Stage context: {context}
Declared mechanic: {mechanic}
Declared reasoning operation: {reasoning_operation}
Clue A (shown only to player A): {clue_a}
Clue B (shown only to player B): {clue_b}
Expected stage answer(s): {answers}

Judge this stage for solvability, complementary clues, uniqueness of the answer, appropriateness, realism within the time limit, and whether the clues actually require the declared operation. Do not award difficulty merely for long, vague, or obscure text.

Return ONLY JSON:
{{"confidence": 0-100, "reason": "one or two sentences"}}
"""


async def validate_semantics(candidate: MysteryCandidate, api_key: str, model: str) -> ValidationResult:
    if not api_key:
        return ValidationResult.fail("semantic", "No GEMINI_API_KEY configured — cannot run semantic validation.")

    warnings: list[str] = []
    tier = get_difficulty_tier(candidate.difficulty)
    for stage in candidate.stages:
        clue_a = next(clue.text for clue in stage.clues if clue.role == "player_a")
        clue_b = next(clue.text for clue in stage.clues if clue.role == "player_b")
        answers = candidate.final_answer_patterns if stage.is_final else (stage.checkpoint_answer_patterns or [])
        prompt = SEMANTIC_VALIDATION_PROMPT.format(
            category=candidate.category,
            difficulty=candidate.difficulty,
            difficulty_style=tier.style,
            time_limit_minutes=tier.time_limit_minutes,
            stage_number=stage.stage_number,
            context=stage.context or "(none given)",
            mechanic=stage.mechanic or "(missing)",
            reasoning_operation=stage.reasoning_operation or "(missing)",
            clue_a=clue_a,
            clue_b=clue_b,
            answers=", ".join(answers),
        )
        try:
            judgment = _extract_json(await call_gemini(prompt, api_key, model))
            confidence_value = judgment.get("confidence")
            if type(confidence_value) is not int or not 0 <= confidence_value <= 100:
                return ValidationResult.fail(
                    "semantic", f"Stage {stage.stage_number}: semantic reviewer returned an invalid confidence score."
                )
            confidence = confidence_value
            reason = str(judgment.get("reason", ""))
        except Exception as exc:  # one failed review means this candidate cannot be accepted
            return ValidationResult.fail(
                "semantic", f"Stage {stage.stage_number}: semantic validation call failed ({exc})."
            )

        if confidence < SEMANTIC_CONFIDENCE_THRESHOLD:
            return ValidationResult.fail("semantic", f"Stage {stage.stage_number} scored {confidence}/100: {reason}")
        if confidence < 90:
            warnings.append(f"Stage {stage.stage_number} scored {confidence}/100: {reason}")
    return ValidationResult.ok("semantic", warnings)


WHOLE_MYSTERY_VALIDATION_PROMPT = """You are an adversarial whole-mystery reviewer for Pairza, a cooperative two-player mystery game. Each stage gives player_a and player_b distinct clues; they must communicate to combine them. Review the COMPLETE mystery as a connected challenge, not as unrelated individually good stages.

CATEGORY: {category}
REQUESTED DIFFICULTY: {difficulty} — {difficulty_style}
TOTAL TIME LIMIT: {time_limit_minutes} minutes
PYTHON-ENFORCED DIFFICULTY RULES:
{rules}
{plan_section}
COMPLETE MYSTERY JSON (includes answer patterns, checkpoint answers, all stage contexts/clues, and validation metadata):
{mystery_json}

Evaluate all of these:
1. difficulty match (the structure and reasoning really merit the requested level)
2. stage dependency (later stages genuinely require prior checkpoint results)
3. reasoning depth and transformations across the whole challenge
4. progression (each stage advances the same challenge)
5. mechanic diversity (different meaningful operations, not adjective changes)
6. non-skippability (each required intermediate stage matters)
7. final-answer dependency (at levels 3–5 the final answer cannot be derived from initial clues without later results)
8. complementary player_a/player_b clues at every stage
9. solvability and a unique answer without unprovided assumptions
10. for levels 2–5, the mystery feels materially more demanding than a Level 1 single-operation puzzle, at the appropriate level

Do not give high scores just because metadata claims dependencies. Verify whether the actual clues/context make the checkpoint useful. A Level 5 mystery must have exactly three connected stages: Stage 1 yields checkpoint A, Stage 2 requires A and yields checkpoint B, Stage 3 requires B and yields the final answer. Reject three independent mini-puzzles, checkpoints that are decorative, or a final answer that is directly apparent from Stage 1. Be fair: difficulty must come from reasoning, dependency, cross-referencing, transformations, and deduction—not vague or unnecessarily long wording.

Return ONLY a JSON object with integer scores from 0 to 100:
{{
  "confidence": 0,
  "difficulty_match_score": 0,
  "dependency_score": 0,
  "reasoning_depth_score": 0,
  "mechanic_diversity_score": 0,
  "non_skippable_score": 0,
  "reason": "short explanation, identify the main weakness if any"
}}
For a single-stage Level 1 mystery, dependency/non-skippable scores should reflect that no multi-stage dependency is required; judge whether the answer still needs both players' complementary clues. Never downgrade or change the requested difficulty. Score the provided candidate as-is.
"""


_SCORE_KEYS = (
    "confidence",
    "difficulty_match_score",
    "dependency_score",
    "reasoning_depth_score",
    "mechanic_diversity_score",
    "non_skippable_score",
)


def _required_whole_scores(candidate: MysteryCandidate) -> set[str]:
    required = {"confidence", "difficulty_match_score", "reasoning_depth_score"}
    if len(candidate.stages) > 1 or candidate.difficulty >= 3:
        required.update({"dependency_score", "non_skippable_score"})
    if candidate.difficulty >= 4:
        required.add("mechanic_diversity_score")
    if candidate.difficulty == 5:
        required.update(_SCORE_KEYS)
    return required


async def validate_whole_mystery(
    candidate: MysteryCandidate,
    api_key: str,
    model: str,
    challenge_plan: dict[str, Any] | None = None,
) -> ValidationResult:
    """Review cross-stage logic after all deterministic checks and per-stage reviews pass."""
    if not api_key:
        return ValidationResult.fail("whole_mystery", "No GEMINI_API_KEY configured — cannot run whole-mystery validation.")

    tier = get_difficulty_tier(candidate.difficulty)
    plan_section = (
        "EMBEDDED CHALLENGE PLAN (check implementation against it):\n"
        + json.dumps(challenge_plan, indent=2, ensure_ascii=False)
        if challenge_plan else "No embedded challenge plan was supplied; judge the candidate's own structure and metadata independently."
    )
    prompt = WHOLE_MYSTERY_VALIDATION_PROMPT.format(
        category=candidate.category,
        difficulty=candidate.difficulty,
        difficulty_style=tier.style,
        time_limit_minutes=tier.time_limit_minutes,
        rules=json.dumps(DIFFICULTY_RULES[candidate.difficulty], indent=2),
        plan_section=plan_section,
        mystery_json=json.dumps(candidate.model_dump(mode="json"), indent=2, ensure_ascii=False),
    )
    try:
        judgment = _extract_json(await call_gemini(prompt, api_key, model))
    except Exception as exc:
        return ValidationResult.fail("whole_mystery", f"Whole-mystery semantic validation call failed ({exc}).")

    scores: dict[str, int] = {}
    for key in _SCORE_KEYS:
        value = judgment.get(key)
        if type(value) is not int or not 0 <= value <= 100:
            return ValidationResult.fail(
                "whole_mystery", f"Whole-mystery reviewer returned a missing or invalid {key} (expected integer 0–100)."
            )
        scores[key] = value
    reason = str(judgment.get("reason", "")).strip()

    thresholds = {
        "confidence": WHOLE_MYSTERY_THRESHOLD,
        "difficulty_match_score": DIFFICULTY_MATCH_THRESHOLD,
        "dependency_score": DEPENDENCY_THRESHOLD,
        "reasoning_depth_score": REASONING_DEPTH_THRESHOLD,
        "mechanic_diversity_score": MECHANIC_DIVERSITY_THRESHOLD,
        "non_skippable_score": NON_SKIPPABLE_THRESHOLD,
    }
    failures = [
        f"{key} {scores[key]}/100 is below required {thresholds[key]}"
        for key in sorted(_required_whole_scores(candidate))
        if scores[key] < thresholds[key]
    ]
    if failures:
        return ValidationResult.fail(
            "whole_mystery",
            "Whole-mystery validation rejected candidate: " + "; ".join(failures) + (f". Reviewer: {reason}" if reason else "."),
        )

    return ValidationResult.ok(
        "whole_mystery",
        [f"Whole-mystery scores: {', '.join(f'{key}={scores[key]}' for key in sorted(scores))}."],
    )


async def validate_mystery(
    db: AsyncSession,
    raw: Any,
    api_key: str,
    model: str,
    skip_semantic: bool = False,
) -> tuple[MysteryCandidate | None, ValidationResult]:
    """Full validation pipeline. Deterministic checks always precede DB/Gemini work."""
    candidate, structure_result = validate_structure(raw)
    if not structure_result.is_valid or candidate is None:
        return candidate, structure_result

    duplicate_result = await check_duplicates(db, candidate)
    if not duplicate_result.is_valid:
        return candidate, duplicate_result

    if skip_semantic:
        return candidate, ValidationResult.ok(
            "semantic", structure_result.warnings + duplicate_result.warnings + [
                "Per-stage and whole-mystery semantic validation skipped by --skip-semantic."
            ]
        )

    stage_result = await validate_semantics(candidate, api_key, model)
    if not stage_result.is_valid:
        return candidate, stage_result

    plan = None
    if isinstance(raw, dict):
        candidate_plan = raw.get("_challenge_plan") or raw.get("challenge_plan") or raw.get("plan")
        if isinstance(candidate_plan, dict):
            plan = candidate_plan

    whole_result = await validate_whole_mystery(candidate, api_key, model, challenge_plan=plan)
    if not whole_result.is_valid:
        return candidate, whole_result

    return candidate, ValidationResult.ok(
        "whole_mystery",
        structure_result.warnings + duplicate_result.warnings + stage_result.warnings + whole_result.warnings,
    )


async def _main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m scripts.validate_mystery <path_to_candidate.json> [--skip-semantic]")
        sys.exit(1)

    path = Path(sys.argv[1])
    skip_semantic = "--skip-semantic" in sys.argv[2:]
    raw = json.loads(path.read_text(encoding="utf-8"))

    from app.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        candidate, result = await validate_mystery(
            db, raw, settings.GEMINI_API_KEY, settings.MYSTERY_GENERATOR_MODEL, skip_semantic
        )

    print(f"Valid: {result.is_valid}")
    print(f"Stage reached: {result.stage}")
    if result.reason:
        print(f"Reason: {result.reason}")
    for warning in result.warnings:
        print(f"Warning: {warning}")
    sys.exit(0 if result.is_valid else 1)


if __name__ == "__main__":
    asyncio.run(_main())
