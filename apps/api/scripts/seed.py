"""
Seeds a demo-ready database: real users with profiles across many
countries, a badge set, and a mystery library spanning categories with
genuinely complementary two-player clues — including the exact tripoint
example from the product spec's own worked example.

Run with: python -m scripts.seed
"""
import asyncio
import random
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from faker import Faker
from sqlalchemy import select

from app.common.database import AsyncSessionLocal
from app.common.mixins import utcnow
from app.common.security import hash_password
from app.mysteries.models import Mystery, MysteryClue, MysteryStage
from app.rewards.models import Badge
from app.users.models import Profile, User, UserPreferences

fake = Faker()

COUNTRIES = [
    "US", "GB", "CA", "AU", "DE", "FR", "JP", "KR", "BR", "IN",
    "MX", "IT", "ES", "NL", "SE", "NO", "PL", "AR", "ZA", "NG",
    "EG", "TH", "VN", "PH", "TR", "PT", "IE", "NZ", "SG", "CH",
]
INTERESTS_POOL = [
    "true crime", "chess", "astronomy", "language learning", "cartography",
    "cryptography", "birdwatching", "film noir", "vintage synths", "urban exploring",
    "linguistics", "archaeology", "board games", "amateur radio", "cold cases",
]
EXPERIENCE_LEVELS = ["beginner", "intermediate", "advanced"]


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


async def seed_users(db, count: int = 24) -> list[User]:
    users = []
    # A stable, memorable demo account first.
    demo_email = "demo@pairza.app"
    existing = await db.execute(select(User).where(User.email == demo_email))
    if not existing.scalar_one_or_none():
        demo_user = User(email=demo_email, hashed_password=hash_password("PairzaDemo123!"), is_verified=True)
        db.add(demo_user)
        await db.flush()
        db.add(Profile(user_id=demo_user.id, username="curious_fox", country_code="US", xp=250, mystery_count=2, solved_count=2, current_streak=2, longest_streak=2, countries_encountered=["GB"], categories_completed=["geo"]))
        db.add(UserPreferences(user_id=demo_user.id, timezone_region="America/New_York", interests=["true crime", "cartography"], puzzle_experience_level="intermediate"))
        users.append(demo_user)

    admin_email = "admin@pairza.app"
    existing_admin = await db.execute(select(User).where(User.email == admin_email))
    if not existing_admin.scalar_one_or_none():
        admin_user = User(email=admin_email, hashed_password=hash_password("PairzaAdmin123!"), is_verified=True, is_admin=True)
        db.add(admin_user)
        await db.flush()
        db.add(Profile(user_id=admin_user.id, username="pairza_hq", country_code="US"))
        db.add(UserPreferences(user_id=admin_user.id))
        users.append(admin_user)

    for i in range(count):
        email = f"seed_user_{i}@pairza.app"
        existing_u = await db.execute(select(User).where(User.email == email))
        if existing_u.scalar_one_or_none():
            continue
        u = User(email=email, hashed_password=hash_password("SeedPassword123!"), is_verified=True)
        db.add(u)
        await db.flush()
        username = f"{fake.word()}_{fake.word()}{random.randint(1,99)}"[:32]
        db.add(Profile(
            user_id=u.id, username=username, country_code=random.choice(COUNTRIES),
            xp=random.randint(0, 4000), mystery_count=random.randint(0, 40),
        ))
        db.add(UserPreferences(
            user_id=u.id, timezone_region=fake.timezone(),
            interests=random.sample(INTERESTS_POOL, k=3),
            puzzle_experience_level=random.choice(EXPERIENCE_LEVELS),
        ))
        users.append(u)

    await db.commit()
    return users


async def _add_mystery(db, title, category, difficulty, summary, flavor_text, final_answers, stages_spec):
    existing = await db.execute(select(Mystery).where(Mystery.title == title))
    if existing.scalar_one_or_none():
        return
    mystery = Mystery(
        title=title, category=category, difficulty=difficulty, summary=summary,
        flavor_text=flavor_text, final_answer_patterns=final_answers, is_published=True,
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
    await db.commit()


async def main() -> None:
    async with AsyncSessionLocal() as db:
        await seed_badges(db)
        users = await seed_users(db)
        await seed_mysteries(db)
        print(f"Seeded {len(users)} users (or already present), badge set, and mystery library.")
        print("Demo login: demo@pairza.app / PairzaDemo123!")
        print("Admin login: admin@pairza.app / PairzaAdmin123!")
        print("All seed_user_* accounts use password: SeedPassword123!")


if __name__ == "__main__":
    asyncio.run(main())
