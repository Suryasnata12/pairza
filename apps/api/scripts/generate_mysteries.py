"""
scripts/generate_mysteries.py

Offline/admin-only mystery generator. Never call this from live request-
handling code — it makes real, sometimes-slow AI API calls, one per
generation attempt. It's meant to run as a standalone batch job: a
developer's terminal, or the admin panel's "Generate more" button, which
runs this same logic as a FastAPI background task (see
app/admin/service.py::trigger_mystery_generation) rather than during any
actual player-facing request.

Usage:
    python -m scripts.generate_mysteries --category geo --quantity 10
    python -m scripts.generate_mysteries --all-categories --quantity 5
    python -m scripts.generate_mysteries --category cipher --quantity 3 --difficulty 4 --dry-run

Every candidate goes through the full three-stage pipeline in
scripts/validate_mystery.py before it's ever saved. Rejected candidates
are logged (with the specific reason) and never written to the database.
"""
import argparse
import asyncio
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.common.database import AsyncSessionLocal
from app.config.settings import get_settings
from app.mysteries.difficulty import DIFFICULTY_TIERS, MAX_DIFFICULTY, MIN_DIFFICULTY, get_difficulty_tier
from app.mysteries.models import MYSTERY_CATEGORIES, Mystery, MysteryClue, MysteryStage
from app.mysteries.schemas import MysteryCandidate
from scripts.validate_mystery import _call_anthropic, _extract_json, validate_mystery

settings = get_settings()

MAX_ATTEMPTS_PER_MYSTERY = 3  # give up on ONE more valid mystery after this many failed tries
GENERATOR_VERSION_PREFIX = "v1"

CATEGORY_GUIDANCE = {
    "internet_hunt": "an archived forum post, a dead link, a filename, or some other trace of 'old internet' content",
    "visual": "something that must be described visually — colors, shapes, a described image or scene (text-only, there's no actual image)",
    "geo": "a real-world place, identified via coordinates, landmarks, or geographic trivia",
    "audio": "a described sound, rhythm, or piece of audio (described in text — there's no actual audio)",
    "logic": "a riddle or logic puzzle that only makes sense when both halves are combined",
    "cipher": "a code or cipher (substitution, shift, etc.) that must be decoded",
    "investigation": "a case-file style mystery — documents, testimony, or evidence pieced together",
    "pattern": "a sequence or pattern (numeric, rhythmic, symbolic) that must be recognized",
    "arg": "an alternate-reality-game style puzzle with a narrative hook",
}

GENERATION_PROMPT_TEMPLATE = """You write puzzle content for Pairza, a game where two strangers are matched daily \
and each gets ONE of two complementary clues to a mystery. Neither alone is enough — they must describe what they \
see to each other in chat to combine them and reach the answer.

Generate exactly ONE new mystery in the "{category}" category, at difficulty {difficulty} (1=gentle, 5=brutal). \
Difficulty {difficulty} means: {difficulty_style}. The pair gets a hard time limit of {time_limit_minutes} minutes to \
solve the WHOLE mystery together in chat, so it must be genuinely solvable in that time. If the style involves \
misleading or indirect clues, use red herrings and indirect phrasing sparingly — the two clues combined must still \
point to exactly ONE answer. This category is about {category_guidance}.

Here is a real, already-published example from this exact game, to show you the tone, format, and complementary-\
clue mechanic (do NOT reuse this example's content — write something entirely new):

{example}

Requirements:
- 1 or 2 stages. If 2 stages, the first is a checkpoint (its own separate, easier sub-answer) that unlocks the \
second, and only the second is marked "is_final": true.
- Every stage has EXACTLY two clues: one with "role": "player_a", one with "role": "player_b". They must be \
genuinely different — neither alone should give away the answer, but combining them should make the answer clear.
- Never let a clue contain the literal answer text.
- Keep tone consistent with the example: atmospheric, concise, a little mysterious, no purple prose.

Respond with ONLY a single JSON object, no other text, no markdown code fences, matching exactly this shape:
{{
  "title": "...", "category": "{category}", "difficulty": {difficulty}, "summary": "one spoiler-free sentence",
  "flavor_text": "one atmospheric sentence shown during the reveal animation",
  "final_answer_patterns": ["normalized answer", "an accepted variant"],
  "stages": [
    {{"stage_number": 1, "is_final": true, "context": "short framing sentence", "checkpoint_answer_patterns": null,
      "clues": [{{"role": "player_a", "text": "..."}}, {{"role": "player_b", "text": "..."}}]}}
  ]
}}
"""


async def _fetch_example(db: AsyncSession, category: str) -> str:
    """Pulls one real, already-published mystery in this category as a
    few-shot example — dramatically improves output consistency versus
    describing the desired format only in the abstract."""
    result = await db.execute(
        select(Mystery)
        .options(selectinload(Mystery.stages).selectinload(MysteryStage.clues))
        .where(Mystery.category == category, Mystery.status == "PUBLISHED")
        .limit(5)
    )
    candidates = list(result.scalars().all())
    if not candidates:
        # No example in this category yet (e.g. a brand-new category) — fall
        # back to any published mystery so the model still sees the right shape.
        result = await db.execute(
            select(Mystery)
            .options(selectinload(Mystery.stages).selectinload(MysteryStage.clues))
            .where(Mystery.status == "PUBLISHED")
            .limit(1)
        )
        candidates = list(result.scalars().all())
    if not candidates:
        return "(no example available)"

    example = random.choice(candidates)
    return json.dumps(
        {
            "title": example.title, "category": example.category, "difficulty": example.difficulty,
            "summary": example.summary, "final_answer_patterns": example.final_answer_patterns,
            "stages": [
                {
                    "stage_number": s.stage_number, "is_final": s.is_final, "context": s.context,
                    "clues": [{"role": c.role, "text": c.text} for c in s.clues],
                }
                for s in example.stages
            ],
        },
        indent=2,
    )


async def generate_one_candidate(db: AsyncSession, category: str, difficulty: int) -> dict:
    example = await _fetch_example(db, category)
    tier = get_difficulty_tier(difficulty)
    prompt = GENERATION_PROMPT_TEMPLATE.format(
        category=category, difficulty=difficulty,
        difficulty_style=tier.style, time_limit_minutes=tier.time_limit_minutes,
        category_guidance=CATEGORY_GUIDANCE.get(category, "an original puzzle concept"), example=example,
    )
    raw_response = await _call_anthropic(prompt, settings.ANTHROPIC_API_KEY, settings.MYSTERY_GENERATOR_MODEL)
    return _extract_json(raw_response)


async def save_mystery(db: AsyncSession, candidate: MysteryCandidate, auto_publish: bool) -> None:
    status = "PUBLISHED" if auto_publish else "VALIDATED"
    mystery = Mystery(
        title=candidate.title, category=candidate.category, difficulty=candidate.difficulty,
        summary=candidate.summary, flavor_text=candidate.flavor_text,
        final_answer_patterns=candidate.final_answer_patterns,
        is_published=auto_publish, status=status,
        generator_version=f"{settings.MYSTERY_GENERATOR_MODEL}:{GENERATOR_VERSION_PREFIX}",
    )
    db.add(mystery)
    await db.flush()
    for stage_c in candidate.stages:
        stage = MysteryStage(
            mystery_id=mystery.id, stage_number=stage_c.stage_number, is_final=stage_c.is_final,
            context=stage_c.context, checkpoint_answer_patterns=stage_c.checkpoint_answer_patterns,
        )
        db.add(stage)
        await db.flush()
        for clue_c in stage_c.clues:
            db.add(MysteryClue(stage_id=stage.id, role=clue_c.role, text=clue_c.text))
    await db.commit()


async def generate_for_category(
    db: AsyncSession, category: str, quantity: int, difficulty: int | None, dry_run: bool
) -> dict:
    stats = {
        "category": category, "requested": quantity, "attempts": 0,
        "rejected": 0, "valid": 0, "saved": 0, "rejections": [],
    }

    if not settings.ANTHROPIC_API_KEY:
        stats["rejections"].append("ANTHROPIC_API_KEY is not configured — see .env.example.")
        return stats

    saved = 0
    max_total_attempts = quantity * MAX_ATTEMPTS_PER_MYSTERY
    while saved < quantity and stats["attempts"] < max_total_attempts:
        stats["attempts"] += 1
        this_difficulty = difficulty or random.randint(MIN_DIFFICULTY, MAX_DIFFICULTY)
        try:
            raw = await generate_one_candidate(db, category, this_difficulty)
        except Exception as exc:  # noqa: BLE001 — one bad call must not kill the whole batch
            stats["rejected"] += 1
            stats["rejections"].append(f"Attempt {stats['attempts']}: generation call failed ({exc}).")
            continue

        candidate, result = await validate_mystery(db, raw, settings.ANTHROPIC_API_KEY, settings.MYSTERY_GENERATOR_MODEL)
        if not result.is_valid:
            stats["rejected"] += 1
            stats["rejections"].append(f"Attempt {stats['attempts']} ({result.stage}): {result.reason}")
            continue

        stats["valid"] += 1
        if not dry_run:
            await save_mystery(db, candidate, settings.MYSTERY_AUTO_PUBLISH)
            stats["saved"] += 1
        saved += 1

    return stats


def _print_report(all_stats: list[dict]) -> None:
    print()
    print(f"{'Category':<16} {'Requested':>10} {'Attempts':>10} {'Rejected':>10} {'Valid':>8} {'Saved':>8}")
    print("-" * 66)
    for s in all_stats:
        print(f"{s['category']:<16} {s['requested']:>10} {s['attempts']:>10} {s['rejected']:>10} {s['valid']:>8} {s['saved']:>8}")
    print()
    for s in all_stats:
        if s["rejections"]:
            print(f"--- {s['category']} rejections ---")
            for r in s["rejections"]:
                print(f"  {r}")
    print()


async def main() -> None:
    parser = argparse.ArgumentParser(description="Generate new Pairza mysteries via AI, with full validation.")
    parser.add_argument("--category", choices=MYSTERY_CATEGORIES, help="Generate for one specific category.")
    parser.add_argument("--all-categories", action="store_true", help="Generate for every category in MYSTERY_CATEGORIES.")
    parser.add_argument("--quantity", type=int, default=5, help="How many VALID mysteries to save per category (default 5).")
    parser.add_argument("--difficulty", type=int, choices=sorted(DIFFICULTY_TIERS), help="Fix difficulty instead of randomizing per mystery.")
    parser.add_argument("--dry-run", action="store_true", help="Generate and validate but save nothing.")
    args = parser.parse_args()

    if not args.category and not args.all_categories:
        parser.error("Specify either --category <name> or --all-categories.")

    categories = MYSTERY_CATEGORIES if args.all_categories else [args.category]

    all_stats = []
    async with AsyncSessionLocal() as db:
        for category in categories:
            print(f"Generating for '{category}'...")
            stats = await generate_for_category(db, category, args.quantity, args.difficulty, args.dry_run)
            all_stats.append(stats)

    _print_report(all_stats)


if __name__ == "__main__":
    asyncio.run(main())
