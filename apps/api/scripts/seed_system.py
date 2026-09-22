"""
Production-safe system/bootstrap initialization for Pairza.

Run with: python -m scripts.seed_system

This is the ONLY seed script safe to run against a production database. It
creates exclusively legitimate system/configuration data that Pairza ships
with — badge definitions, the initial hand-authored mystery library, and one
config row per mystery category. It NEVER creates users, matches, sessions,
history rows, or activity records: real gameplay is the only thing that may
create those (see auth/service.py, matchmaking/service.py, sessions/service.py,
rewards/service.py).

Every function here is idempotent (checks for an existing row before
inserting), so running this script twice — or on every deploy — is safe and
a no-op the second time.

For a rich local development environment with demo/test users, matches, and
history, use `python -m scripts.seed_demo` instead (development only — see
that script's own guard).
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.common.database import AsyncSessionLocal
from app.common.mixins import utcnow
from app.mysteries.difficulty import time_limit_for_difficulty
from app.mysteries.models import MYSTERY_CATEGORIES, Mystery, MysteryCategoryConfig, MysteryClue, MysteryStage
from app.rewards.models import Badge


async def seed_badges(db) -> None:
    badges = [
        ("FIRST_SOLVE", "First Case Closed", "Solve your very first mystery.", "sparkles", "first_solve", 1),
        ("SOLVE_10", "Seasoned Investigator", "Solve 10 mysteries.", "search", "solve_count", 10),
        ("SOLVE_50", "Master Detective", "Solve 50 mysteries.", "badge-check", "solve_count", 50),
        ("SOLVE_100", "Legendary Sleuth", "Solve 100 mysteries.", "crown", "solve_count", 100),
        ("STREAK_7", "Week-Long Watch", "Keep a 7-day streak alive.", "flame", "streak", 7),
        ("STREAK_30", "Unbroken Vigil", "Keep a 30-day streak alive.", "flame", "streak", 30),
        ("SPEED_10MIN", "Quick Draw", "Solve a mystery in under 10 minutes.", "zap", "speed_solver", 600),
        ("SPEED_5MIN", "Lightning Round", "Solve a mystery in under 5 minutes.", "zap", "speed_solver", 300),
        ("COUNTRIES_5", "Passport Stamped", "Cross paths with strangers from 5 different countries.", "globe", "countries", 5),
        ("COUNTRIES_15", "Global Citizen", "Cross paths with strangers from 15 different countries.", "globe-2", "countries", 15),
        ("CATEGORIES_3", "Well-Rounded", "Complete mysteries in 3 different categories.", "layers", "categories", 3),
        ("CATEGORIES_ALL", "Renaissance Detective", "Complete a mystery in every category.", "layout-grid", "categories", 9),
    ]
    for code, name, desc, icon, criteria_type, value in badges:
        existing = await db.execute(select(Badge).where(Badge.code == code))
        if existing.scalar_one_or_none():
            continue
        db.add(Badge(code=code, name=name, description=desc, icon=icon, criteria_type=criteria_type, criteria_value=value))
    await db.commit()


async def _add_mystery(db, title, category, difficulty, summary, flavor_text, final_answers, stages_spec):
    existing = await db.execute(select(Mystery).where(Mystery.title == title))
    if existing.scalar_one_or_none():
        return
    mystery = Mystery(
        title=title, category=category, difficulty=difficulty, summary=summary,
        flavor_text=flavor_text, final_answer_patterns=final_answers, is_published=True, status="PUBLISHED",
    )
    db.add(mystery)
    await db.flush()
    for stage_spec in stages_spec:
        stage = MysteryStage(
            mystery_id=mystery.id, stage_number=stage_spec["number"], is_final=stage_spec["is_final"],
            context=stage_spec["context"], checkpoint_answer_patterns=stage_spec.get("checkpoint_answers"),
        )
        db.add(stage)
        await db.flush()
        db.add(MysteryClue(stage_id=stage.id, role="player_a", text=stage_spec["clue_a"]))
        db.add(MysteryClue(stage_id=stage.id, role="player_b", text=stage_spec["clue_b"]))


async def seed_mysteries(db) -> None:
    # The exact worked example from the product spec's own clue-design section.
    await _add_mystery(
        db, "The Vanishing Photograph", "geo", 3,
        "A single photograph, and two strangers who each only have half the story.",
        "A photograph surfaces with no caption, no date, and no obvious location. You each hold one half of the puzzle.",
        ["iguazu falls", "iguacu falls", "the iguazu falls"],
        [{
            "number": 1, "is_final": True, "context": "Compare what you each see in the margins of the photograph.",
            "clue_a": "Look where three borders almost touch.",
            "clue_b": "The answer is connected to a place that shares its name with a song released before 2010.",
        }],
    )

    await _add_mystery(
        db, "The Cipher in the Margins", "cipher", 2,
        "A secondhand book arrives with a coded note pressed between its pages.",
        "The note uses a substitution you've seen before — if you can remember where.",
        ["meet me at midnight", "meet at midnight"],
        [
            {
                "number": 1, "is_final": False,
                "context": "The note is split into two halves, each encoded differently.",
                "clue_a": "Your half reads: WKH ILUVW KDOI RI WKH PHVVDJH. (Hint: each letter is shifted forward by the same small number.)",
                "clue_b": "Your half reads: PHHW PH DW. Try shifting each letter three places back through the alphabet.",
                "checkpoint_answers": ["the first half of the message", "meet me at"],
            },
            {
                "number": 2, "is_final": True,
                "context": "Both halves decode with the same shift. Put them together.",
                "clue_a": "Your fragment, once shifted, ends in a time of day.",
                "clue_b": "Your fragment, once shifted, ends in a place: a clock tower.",
            },
        ],
    )

    await _add_mystery(
        db, "Coordinates of a Stranger", "geo", 1,
        "Someone left a set of coordinates and nothing else. Where do they lead?",
        "No note, no name — just a pin on an otherwise empty map.",
        ["greenwich observatory", "royal observatory greenwich", "the royal observatory"],
        [{
            "number": 1, "is_final": True,
            "context": "The coordinates alone aren't enough — you'll need both readings to plot the point.",
            "clue_a": "Your reading gives the latitude: 51.4769° N.",
            "clue_b": "Your reading gives the longitude: 0.0005° W — very close to a very famous line.",
        }],
    )

    await _add_mystery(
        db, "The Locked Forum Thread", "internet_hunt", 3,
        "An abandoned forum thread from 2009 references a file that no longer exists anywhere — except maybe it does.",
        "Half the thread was archived. Half wasn't. You'll need to dig through what's left of each.",
        ["hollowlight.zip", "hollowlight"],
        [{
            "number": 1, "is_final": True,
            "context": "The thread's replies were split across two now-dead forums with different archiving luck.",
            "clue_a": "Your archive shows a reply mentioning a filename ending in '.zip', partially redacted: 'hollow____'.",
            "clue_b": "Your archive shows a different reply completing it: someone typed out 'light.zip' by itself, mocking the original poster.",
        }],
    )

    await _add_mystery(
        db, "Two Halves of a Riddle", "logic", 2,
        "An old riddle, split down the middle, deliberately, by someone who wanted it solved together or not at all.",
        "Riddles built for two rarely make sense alone. That's the point.",
        ["a shadow", "shadow"],
        [{
            "number": 1, "is_final": True,
            "context": "Read each half aloud to each other before guessing — it's meant to be heard, not just read.",
            "clue_a": "I follow you all day but vanish at noon and again at night.",
            "clue_b": "I have no weight, no voice, yet everyone has one. What am I?",
        }],
    )

    await _add_mystery(
        db, "The Redacted Report", "investigation", 4,
        "A leaked internal memo has half its lines blacked out — but not the same half in each copy that circulated.",
        "Two copies leaked from two different sources. Compare what survived in each.",
        ["project nightingale", "operation nightingale"],
        [
            {
                "number": 1, "is_final": False,
                "context": "Start by identifying what kind of document this even is.",
                "clue_a": "Your copy's header is intact: 'INTERNAL MEMO — RE: BUDGET REALLOCATION'.",
                "clue_b": "Your copy's footer is intact: 'Distribution restricted to Project [REDACTED] leads.'",
                "checkpoint_answers": ["budget memo", "internal memo", "budget reallocation memo"],
            },
            {
                "number": 2, "is_final": True,
                "context": "The project's codename appears twice in the memo — once in each of your copies, each time partially legible.",
                "clue_a": "Your copy shows the codename starting with 'Night...' before the ink gives out.",
                "clue_b": "Your copy shows the codename ending in '...ingale' with the beginning smudged.",
            },
        ],
    )

    await _add_mystery(
        db, "The Pattern in the Static", "pattern", 3,
        "A radio recording contains what sounds like noise — until you notice it repeats.",
        "Not everyone hears the same part of the pattern clearly. That's by design.",
        ["morse for help", "sos", "help"],
        [{
            "number": 1, "is_final": True,
            "context": "Focus on rhythm, not volume — the pattern is timing, not sound.",
            "clue_a": "You can clearly hear three short pulses, then a long gap.",
            "clue_b": "You can clearly hear three long pulses, then three short ones, on a loop.",
        }],
    )

    await _add_mystery(
        db, "The Split Testimony", "investigation", 2,
        "Two witnesses to the same event, interviewed separately, remember different details.",
        "Neither account alone tells the whole story. Together, they might.",
        ["the blue car", "a blue car"],
        [{
            "number": 1, "is_final": True,
            "context": "Witnesses often remember the same event from different angles — literally.",
            "clue_a": "Witness A is certain about the color: it was blue, no question.",
            "clue_b": "Witness B is certain about the object: it was definitely a car, though they never saw the color.",
        }],
    )

    # --- Difficulty 5: three-stage Morse investigations ---
    # Every Morse string below was checked letter-by-letter against standard International Morse
    # Code before being added. One correction from the source design: a couple of source final
    # stages handed one player the ENTIRE decoded phrase while the other got an unrelated or
    # near-useless detail, which would let that player solve alone — against Pairza's own
    # "neither player solves a phase alone" rule. Those two stages (The Hidden Door, The Key Is
    # Underneath) have their final Morse phrase split across clue_a/clue_b here, the same way
    # every other stage already splits information. Nothing else was changed.
    await _add_mystery(
        db, "The Hidden Door", "cipher", 5,
        "A message arrives in two pieces. Somewhere in this room is a door that isn't a door.",
        "Not every door looks like a door.",
        ["don't trust the mirror", "dont trust the mirror"],
        [
            {
                "number": 1, "is_final": False,
                "context": "A message arrives in Morse, split between the two of you.",
                "clue_a": "Your fragment: .... .. -.. -.. . -.",
                "clue_b": "Your fragment: -.. --- --- .-.",
                "checkpoint_answers": ["hidden door"],
            },
            {
                "number": 2, "is_final": False,
                "context": "Something in this room is not what it seems.",
                "clue_a": "You see a painting, a mirror, a bookshelf, and a statue. The painting hangs normally, and the mirror has no unusual markings.",
                "clue_b": "The bookshelf has a thin dark line running around its outer frame, and there's a small gap between it and the wall.",
                "checkpoint_answers": ["bookshelf"],
            },
            {
                "number": 3, "is_final": True,
                "context": "Behind the bookshelf is one last message, in two halves again.",
                "clue_a": "Your half: -.. --- -. .----. - / - .-. ..- ... -",
                "clue_b": "Your half: - .... . / -- .. .-. .-. --- .-.",
            },
        ],
    )
    await _add_mystery(
        db, "Follow the Shadow", "cipher", 5,
        "A shadow falls where it shouldn't. Something is waiting at the end of it.",
        "Shadows don't lie about where they point.",
        ["hidden compartment"],
        [
            {
                "number": 1, "is_final": False,
                "context": "A message arrives in Morse, split between the two of you.",
                "clue_a": "Your fragment: ..-. --- .-.. .-.. --- .--",
                "clue_b": "Your fragment: - .... . / ... .... .- -.. --- .--",
                "checkpoint_answers": ["follow the shadow"],
            },
            {
                "number": 2, "is_final": False,
                "context": "A statue stands beneath a single light, its shadow stretching across the floor toward a wall.",
                "clue_a": "The wall ahead has three symbols on it: a diamond, a circle, and a triangle.",
                "clue_b": "The statue's shadow ends directly beneath one of the three symbols on the wall: the diamond.",
                "checkpoint_answers": ["diamond"],
            },
            {
                "number": 3, "is_final": True,
                "context": "Behind the diamond, a coded message reads NOT THE DOOR — a decoy. Something else here is real.",
                "clue_a": "The diamond symbol also appears on one floor tile.",
                "clue_b": "That marked floor tile sounds hollow when tapped.",
            },
        ],
    )
    await _add_mystery(
        db, "Someone Is Watching", "cipher", 5,
        "A camera with its light off. A reflection that doesn't belong. You are not alone here.",
        "Not every reflection shows what's really there.",
        ["you are not alone"],
        [
            {
                "number": 1, "is_final": False,
                "context": "A message arrives in Morse, in three pieces — the middle one is yours to hold apart from the rest.",
                "clue_a": "Your two fragments, in order (first, then third): ... --- -- . --- -. .  and  .-- .- - -.-. .... .. -. --.",
                "clue_b": "Your fragment (it goes in the middle): .. ...",
                "checkpoint_answers": ["someone is watching"],
            },
            {
                "number": 2, "is_final": False,
                "context": "A security camera is mounted in the corner of the room. Its indicator light is off.",
                "clue_a": "The camera's indicator light is off — it shouldn't be recording anything.",
                "clue_b": "The camera lens reflects something anyway: what looks like the silhouette of a person.",
                "checkpoint_answers": ["reflection"],
            },
            {
                "number": 3, "is_final": True,
                "context": "Look at what the reflection is actually showing.",
                "clue_a": "The reflection doesn't match the room directly in front of the camera.",
                "clue_b": "What the reflection actually shows is a mirror — one that's behind both of you.",
            },
        ],
    )
    await _add_mystery(
        db, "The Key Is Underneath", "cipher", 5,
        "A key is hidden somewhere close. The truth is, quite literally, underneath.",
        "The first piece of something larger is waiting to be found.",
        ["the first piece", "first piece"],
        [
            {
                "number": 1, "is_final": False,
                "context": "A message arrives in Morse, split between the two of you.",
                "clue_a": "Your fragment: - .... . / -.- . -.--",
                "clue_b": "Your fragment: .. ... / ..- -. -.. . .-. -. . .- - ....",
                "checkpoint_answers": ["the key is underneath"],
            },
            {
                "number": 2, "is_final": False,
                "context": "The room holds a desk, a chair, a lamp, and a locked box.",
                "clue_a": "Nothing is visible on top of the desk.",
                "clue_b": "There's writing underneath the desk that reads NOT HERE. The chair sits directly underneath the desk.",
                "checkpoint_answers": ["key", "the key"],
            },
            {
                "number": 3, "is_final": True,
                "context": "The key opens the locked box. Inside is one last message, in two halves.",
                "clue_a": "Your half: -.-- --- ..- / ..-. --- ..- -. -..",
                "clue_b": "Your half: - .... . / ..-. .. .-. ... - / .--. .. . -.-. .",
            },
        ],
    )
    await _add_mystery(
        db, "Don't Look Back", "cipher", 5,
        "A hallway. A mirror at the end of it. Something in the reflection that shouldn't be there.",
        "Not everything the mirror shows exists in the room behind you.",
        ["exit"],
        [
            {
                "number": 1, "is_final": False,
                "context": "A message arrives in Morse, split between the two of you.",
                "clue_a": "Your fragment: -.. --- -. .----. -",
                "clue_b": "Your fragment: .-.. --- --- -.- / -... .- -.-. -.-",
                "checkpoint_answers": ["don't look back", "dont look back"],
            },
            {
                "number": 2, "is_final": False,
                "context": "You're standing in a long hallway. At the end of it is a large mirror.",
                "clue_a": "Looking directly at the hallway, nothing about it seems unusual.",
                "clue_b": "Looking in the mirror instead, you can see a triangle symbol that doesn't exist anywhere in the hallway itself.",
                "checkpoint_answers": ["triangle mark", "triangle"],
            },
            {
                "number": 3, "is_final": True,
                "context": "Under a loose floor tile is a small piece of paper, marked in Morse: . -..- .. -",
                "clue_a": "The triangular mark on the floor points toward one loose tile.",
                "clue_b": "Under that tile is a small piece of paper.",
            },
        ],
    )
    await db.commit()


async def seed_category_configs(db) -> None:
    """One explicit, enabled config row per known category — not strictly
    required (absence already means enabled, see MysteryCategoryConfig's
    docstring), but gives the admin panel something real to show and
    toggle for every category from the very first load."""
    existing = set((await db.execute(select(MysteryCategoryConfig.category))).scalars().all())
    for category in MYSTERY_CATEGORIES:
        if category not in existing:
            db.add(MysteryCategoryConfig(category=category, is_enabled=True, updated_at=utcnow()))
    await db.commit()


async def main() -> None:
    async with AsyncSessionLocal() as db:
        await seed_badges(db)
        await seed_mysteries(db)
        await seed_category_configs(db)
        print("System bootstrap complete: badges, mystery library, and category config are in place.")
        print("No users, matches, sessions, or activity were created — that only happens through real gameplay.")


if __name__ == "__main__":
    asyncio.run(main())
