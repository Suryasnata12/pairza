"""
DEPRECATED — kept only so `python -m scripts.seed` doesn't silently break for
anyone with it in a script or their muscle memory.

seed.py used to conflate two very different things: legitimate system
bootstrap data and fake demo activity, including printing default admin
credentials. It has been split so production and development can no longer
share a script by accident:

    python -m scripts.seed_system   — production-safe: badges, mystery
                                       library, category config. No users,
                                       no matches, no fake activity, ever.
    python -m scripts.seed_demo     — DEVELOPMENT ONLY (refuses to run
                                       unless ENVIRONMENT=development): the
                                       full fake-user/match/history demo
                                       environment this script used to build.
    python -m scripts.create_admin  — the real way to get an admin account
                                       onto a production database: reads
                                       ADMIN_EMAIL / ADMIN_PASSWORD from the
                                       environment with no default, and
                                       never prints the password.

This file forwards to seed_demo.py (the closest match to this script's old
behavior) so existing local dev setups keep working, and does nothing else.
"""
import asyncio
import sys

from scripts.seed_demo import main as seed_demo_main

if __name__ == "__main__":
    print("scripts/seed.py is deprecated — see this file's own docstring for the replacement scripts.\n", file=sys.stderr)
    asyncio.run(seed_demo_main())
