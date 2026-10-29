"""Tests for deterministic difficulty enforcement and whole-mystery scoring.

Place at apps/api/tests/test_validate_mystery_difficulty.py. The tests never
call a real Gemini endpoint or mutate a database.
"""
from __future__ import annotations

import json

import pytest

from app.mysteries.schemas import MysteryCandidate
from scripts import validate_mystery as validator


def make_candidate(difficulty: int, stage_count: int | None = None, category: str = "investigation") -> dict:
    stage_count = stage_count or {1: 1, 2: 2, 3: 2, 4: 3, 5: 3}[difficulty]
    mechanics_by_category = {
        "investigation": ["evidence correlation", "timeline reconstruction", "cross-reference"],
        "logic": ["deduction", "logical constraints", "contradiction analysis"],
        "geo": ["spatial reasoning", "coordinate interpretation", "evidence correlation"],
        "cipher": ["cipher decoding", "key extraction", "symbol mapping"],
    }
    mechanics = mechanics_by_category[category]
    stages = []
    for index in range(1, stage_count + 1):
        final = index == stage_count
        if stage_count == 1:
            requires = []
        elif index == 1:
            requires = []
        elif index == 2:
            requires = ["checkpoint A"]
        else:
            requires = ["checkpoint B"]

        if difficulty == 1:
            operation = "Infer one relation by combining the two complementary observations"
        elif difficulty == 2 and stage_count == 1:
            operation = "Operation 1: combine both observations; Operation 2: eliminate inconsistent options"
        else:
            operation = {
                1: "Correlate two independent pieces of evidence to derive an intermediate result",
                2: "Use the prior checkpoint to reconstruct the missing timeline relation",
                3: "Cross-reference the derived relation to identify the final destination",
            }[index]

        stages.append({
            "stage_number": index,
            "is_final": final,
            "context": (
                "Begin by comparing the two separate records."
                if index == 1 else
                "Use the result established by the preceding stage to interpret this new evidence."
            ),
            "checkpoint_answer_patterns": None if final else ["amber token" if index == 1 else "north passage"],
            "mechanic": mechanics[(index - 1) % len(mechanics)],
            "reasoning_operation": operation,
            "requires_checkpoints": requires,
            "clues": [
                {"role": "player_a", "text": f"Player A holds a unique observation about record number {index}."},
                {"role": "player_b", "text": f"Player B holds a complementary detail about witness entry {index}."},
            ],
        })

    return {
        "title": "The Lantern Ledger",
        "category": category,
        "difficulty": difficulty,
        "summary": "Two investigators combine records to resolve a hidden destination.",
        "flavor_text": "The scattered notes settle into a single account.",
        "final_answer_patterns": ["silver bell"],
        "stages": stages,
    }


def test_difficulty_five_one_stage_is_rejected_before_database_or_ai() -> None:
    candidate = make_candidate(5, stage_count=1)
    parsed, result = validator.validate_structure(candidate)
    assert parsed is not None
    assert not result.is_valid
    assert result.stage == "difficulty"
    assert result.reason == "Difficulty 5 requires exactly 3 stages, got 1."


def test_difficulty_three_requires_exactly_two_stages() -> None:
    _, result = validator.validate_structure(make_candidate(3, stage_count=1))
    assert not result.is_valid
    assert "Difficulty 3 requires exactly 2 stages" in (result.reason or "")


def test_difficulty_four_rejects_one_stage() -> None:
    _, result = validator.validate_structure(make_candidate(4, stage_count=1))
    assert not result.is_valid
    assert "Difficulty 4 requires 2–3 stages" in (result.reason or "")


def test_level_five_requires_stage_two_checkpoint_a() -> None:
    raw = make_candidate(5)
    raw["stages"][1]["requires_checkpoints"] = []
    _, result = validator.validate_structure(raw)
    assert not result.is_valid
    assert result.stage == "dependency"
    assert "Stage 2 must require checkpoint A" in (result.reason or "")


def test_level_five_requires_stage_three_checkpoint_b() -> None:
    raw = make_candidate(5)
    raw["stages"][2]["requires_checkpoints"] = ["checkpoint A"]
    _, result = validator.validate_structure(raw)
    assert not result.is_valid
    assert "Stage 3 must require checkpoint B" in (result.reason or "")


def test_level_five_rejects_duplicate_mechanics_even_if_adjectives_differ() -> None:
    raw = make_candidate(5, category="logic")
    raw["stages"][0]["mechanic"] = "advanced deduction"
    raw["stages"][1]["mechanic"] = "complex deduction"
    raw["stages"][2]["mechanic"] = "deduction"
    _, result = validator.validate_structure(raw)
    assert not result.is_valid
    assert "meaningfully different mechanics" in (result.reason or "")


def test_mechanic_must_be_valid_for_category() -> None:
    raw = make_candidate(4, category="geo")
    raw["stages"][0]["mechanic"] = "cipher decoding"
    _, result = validator.validate_structure(raw)
    assert not result.is_valid
    assert "not an approved, category-appropriate mechanic" in (result.reason or "")


def test_level_one_requires_exactly_one_operation() -> None:
    raw = make_candidate(1)
    raw["stages"][0]["reasoning_operation"] = "Operation 1: infer a relationship; Operation 2: eliminate an option"
    _, result = validator.validate_structure(raw)
    assert not result.is_valid
    assert "Difficulty 1 must use exactly one core reasoning operation" in (result.reason or "")


def test_one_stage_level_two_requires_two_operations() -> None:
    raw = make_candidate(2, stage_count=1)
    raw["stages"][0]["reasoning_operation"] = "Infer the result by combining clues"
    _, result = validator.validate_structure(raw)
    assert not result.is_valid
    assert "requires at least 2 meaningful reasoning operations" in (result.reason or "")


def test_literal_final_answer_in_clue_is_rejected() -> None:
    raw = make_candidate(1)
    raw["stages"][0]["clues"][0]["text"] = "The silver bell is recorded on the card."
    _, result = validator.validate_structure(raw)
    assert not result.is_valid
    assert "exposes the literal final answer" in (result.reason or "")


def test_literal_checkpoint_in_own_clue_is_rejected() -> None:
    raw = make_candidate(3)
    raw["stages"][0]["clues"][0]["text"] = "The amber token is written on this note."
    _, result = validator.validate_structure(raw)
    assert not result.is_valid
    assert "exposes its literal checkpoint answer" in (result.reason or "")


def test_embedded_plan_must_match_candidate_metadata() -> None:
    raw = make_candidate(5)
    raw["_challenge_plan"] = {
        "difficulty": 5,
        "stage_count": 3,
        "stages": [
            {
                "stage_number": stage["stage_number"],
                "mechanic": stage["mechanic"],
                "reasoning_operation": stage["reasoning_operation"],
                "requires": stage["requires_checkpoints"],
                "produces": ["checkpoint A", "checkpoint B", "final answer"][i],
            }
            for i, stage in enumerate(raw["stages"])
        ],
    }
    _, result = validator.validate_structure(raw)
    assert result.is_valid, result.reason
    raw["_challenge_plan"]["stages"][2]["requires"] = ["checkpoint A"]
    _, result = validator.validate_structure(raw)
    assert not result.is_valid
    assert "violates the required checkpoint dependency chain" in (result.reason or "")


@pytest.mark.asyncio
async def test_whole_review_rejects_low_dependency_score(monkeypatch: pytest.MonkeyPatch) -> None:
    candidate = MysteryCandidate.model_validate(make_candidate(5))
    payload = {
        "confidence": 97,
        "difficulty_match_score": 94,
        "dependency_score": 61,
        "reasoning_depth_score": 92,
        "mechanic_diversity_score": 93,
        "non_skippable_score": 60,
        "reason": "Stage 3 can be solved using only the first stage.",
    }

    async def fake_gemini(*args, **kwargs) -> str:
        return json.dumps(payload)

    monkeypatch.setattr(validator, "call_gemini", fake_gemini)
    result = await validator.validate_whole_mystery(candidate, "test-key", "test-model")
    assert not result.is_valid
    assert result.stage == "whole_mystery"
    assert "dependency_score 61/100 is below required 80" in (result.reason or "")


@pytest.mark.asyncio
async def test_whole_review_accepts_when_all_required_level_five_scores_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    candidate = MysteryCandidate.model_validate(make_candidate(5))
    payload = {
        "confidence": 95,
        "difficulty_match_score": 90,
        "dependency_score": 91,
        "reasoning_depth_score": 90,
        "mechanic_diversity_score": 88,
        "non_skippable_score": 90,
        "reason": "All stages form one connected chain.",
    }

    async def fake_gemini(*args, **kwargs) -> str:
        return json.dumps(payload)

    monkeypatch.setattr(validator, "call_gemini", fake_gemini)
    result = await validator.validate_whole_mystery(candidate, "test-key", "test-model")
    assert result.is_valid, result.reason


@pytest.mark.asyncio
async def test_level_one_does_not_require_multistage_dependency_scores(monkeypatch: pytest.MonkeyPatch) -> None:
    candidate = MysteryCandidate.model_validate(make_candidate(1))
    payload = {
        "confidence": 92,
        "difficulty_match_score": 91,
        "dependency_score": 30,
        "reasoning_depth_score": 86,
        "mechanic_diversity_score": 20,
        "non_skippable_score": 40,
        "reason": "It is intentionally a single-stage mystery.",
    }

    async def fake_gemini(*args, **kwargs) -> str:
        return json.dumps(payload)

    monkeypatch.setattr(validator, "call_gemini", fake_gemini)
    result = await validator.validate_whole_mystery(candidate, "test-key", "test-model")
    assert result.is_valid, result.reason
