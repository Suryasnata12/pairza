"""Focused tests for the plan-first generator's deterministic safeguards.

Copy to apps/api/tests/test_generate_mysteries_plan.py in Pairza's repository.
These tests do not call Gemini or a database.
"""
from __future__ import annotations

import pytest
from types import SimpleNamespace

from scripts.generate_mysteries import (
    MECHANICS_BY_CATEGORY,
    _build_plan_prompt,
    _build_generation_prompt,
    _example_is_structurally_relevant,
    DIFFICULTY_RULES,
    MYSTERY_CATEGORIES,
    validate_challenge_plan,
    validate_generated_structure,
)


def make_plan(category: str, difficulty: int, stage_count: int | None = None) -> dict:
    preferred = {1: 1, 2: 2, 3: 2, 4: 3, 5: 3}
    count = stage_count or preferred[difficulty]
    outputs = []
    for index in range(1, count + 1):
        if count == 1:
            outputs.append(([], "final answer"))
        elif count == 2:
            outputs.append(([], "checkpoint A") if index == 1 else (["checkpoint A"], "final answer"))
        else:
            outputs.append(
                ([], "checkpoint A") if index == 1 else
                (["checkpoint A"], "checkpoint B") if index == 2 else
                (["checkpoint B"], "final answer")
            )

    mechanics = sorted(MECHANICS_BY_CATEGORY[category])
    stages = []
    for index, (requires, produces) in enumerate(outputs, start=1):
        operation = f"Operation {index}: derive a distinct useful relation"
        if difficulty == 1:
            operation = "Infer one clear relationship from the two complementary clues"
        if difficulty == 2 and count == 1:
            operation = "Operation 1: combine clues; Operation 2: eliminate the wrong option"
        stages.append({
            "stage_number": index,
            "mechanic": mechanics[(index - 1) % len(mechanics)],
            "reasoning_operation": operation,
            "purpose": f"stage {index} establishes information needed by the chain",
            "requires": requires,
            "produces": produces,
        })
    return {"difficulty": difficulty, "stage_count": count, "stages": stages}


@pytest.mark.parametrize("difficulty,expected_count", [(1, 1), (3, 2), (5, 3)])
def test_exact_stage_count_levels(difficulty: int, expected_count: int) -> None:
    plan = make_plan("logic", difficulty)
    assert plan["stage_count"] == expected_count
    assert validate_challenge_plan(plan, "logic", difficulty) is None


def test_level_two_one_stage_requires_two_operations() -> None:
    plan = make_plan("logic", 2, stage_count=1)
    assert validate_challenge_plan(plan, "logic", 2) is None
    plan["stages"][0]["reasoning_operation"] = "Use the clue fragments to infer the result"
    assert "two linked reasoning operations" in validate_challenge_plan(plan, "logic", 2)


def test_level_five_rejects_missing_stage_dependency() -> None:
    plan = make_plan("investigation", 5)
    plan["stages"][2]["requires"] = ["checkpoint A"]
    assert "directly depend on 'checkpoint B'" in validate_challenge_plan(plan, "investigation", 5)


def test_level_five_rejects_reused_mechanics() -> None:
    plan = make_plan("investigation", 5)
    plan["stages"][1]["mechanic"] = plan["stages"][0]["mechanic"]
    reason = validate_challenge_plan(plan, "investigation", 5)
    assert reason and "distinct mechanics" in reason


def test_rejects_mechanic_not_allowed_for_category() -> None:
    plan = make_plan("geo", 4)
    plan["stages"][0]["mechanic"] = "cipher decoding"
    reason = validate_challenge_plan(plan, "geo", 4)
    assert reason and "category-appropriate" in reason


def make_candidate(plan: dict) -> dict:
    stages = []
    for index in range(1, plan["stage_count"] + 1):
        final = index == plan["stage_count"]
        plan_stage = plan["stages"][index - 1]
        stages.append({
            "stage_number": index,
            "is_final": final,
            "context": f"Stage {index} continues the investigation.",
            "checkpoint_answer_patterns": None if final else [f"checkpoint result {index}"],
            "mechanic": plan_stage["mechanic"],
            "reasoning_operation": plan_stage["reasoning_operation"],
            "requires_checkpoints": plan_stage["requires"],
            "clues": [
                {"role": "player_a", "text": f"Player A observes a distinct detail for stage {index}."},
                {"role": "player_b", "text": f"Player B holds another separate fact for stage {index}."},
            ],
        })
    return {
        "title": "The Chain of Quiet Evidence",
        "category": "investigation",
        "difficulty": plan["difficulty"],
        "summary": "Two investigators combine evidence to uncover a hidden destination.",
        "flavor_text": "The scattered notes finally align.",
        "final_answer_patterns": ["hidden lighthouse"],
        "stages": stages,
    }


def test_generated_candidate_must_match_plan_stage_count() -> None:
    plan = make_plan("investigation", 5)
    raw = make_candidate(plan)
    raw["stages"].pop()
    candidate, reason = validate_generated_structure(raw, "investigation", 5, plan)
    assert candidate is None
    assert reason and "does not match validated plan" in reason


def test_generated_candidate_requires_null_checkpoint_on_final_stage() -> None:
    plan = make_plan("investigation", 5)
    raw = make_candidate(plan)
    raw["stages"][-1]["checkpoint_answer_patterns"] = ["stray checkpoint"]
    candidate, reason = validate_generated_structure(raw, "investigation", 5, plan)
    assert candidate is None
    assert reason and "must have checkpoint_answer_patterns=null" in reason


def test_generated_candidate_rejects_final_answer_leak_in_checkpoint() -> None:
    plan = make_plan("investigation", 5)
    raw = make_candidate(plan)
    raw["stages"][0]["checkpoint_answer_patterns"] = ["hidden lighthouse"]
    candidate, reason = validate_generated_structure(raw, "investigation", 5, plan)
    assert candidate is None
    assert reason and "checkpoint answer duplicates a final answer" in reason


@pytest.mark.parametrize("category", MYSTERY_CATEGORIES)
@pytest.mark.parametrize("difficulty", sorted(DIFFICULTY_RULES))
def test_every_category_has_a_valid_plan_shape(category: str, difficulty: int) -> None:
    plan = make_plan(category, difficulty)
    assert validate_challenge_plan(plan, category, difficulty) is None
    prompt = _build_plan_prompt(category, difficulty)
    assert f"Difficulty selected by the admin: {difficulty}" in prompt
    assert f'"stage_count": {plan["stage_count"]}' in prompt


def _example(difficulty: int, stage_count: int):
    stages = []
    for index in range(1, stage_count + 1):
        final = index == stage_count
        stages.append(SimpleNamespace(
            is_final=final,
            checkpoint_answer_patterns=None if final else [f"checkpoint {index}"],
            clues=[SimpleNamespace(role="player_a"), SimpleNamespace(role="player_b")],
        ))
    return SimpleNamespace(difficulty=difficulty, stages=stages)


def test_level_five_does_not_use_single_stage_few_shot_example() -> None:
    assert not _example_is_structurally_relevant(_example(2, 1), 5)


def test_level_five_can_use_three_stage_example_from_nearby_difficulty() -> None:
    assert _example_is_structurally_relevant(_example(4, 3), 5)


def test_prompt_has_explicit_answer_leak_self_audit() -> None:
    plan = make_plan("logic", 5)
    prompt = _build_generation_prompt("logic", 5, plan, "(no relevant example)")
    assert "CRITICAL ANSWER-LEAK AUDIT" in prompt
    assert "Do not change the answer merely to evade the check" in prompt
