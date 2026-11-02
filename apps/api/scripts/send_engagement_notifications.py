"""
CLI entry point for Pairza promotional engagement notifications.

Usage:
    python -m scripts.send_engagement_notifications
    python -m scripts.send_engagement_notifications --dry-run
"""

import argparse
import asyncio
import logging

from app.common.database import engine
from app.common.redis_client import get_redis
from app.notifications.engagement_service import run


async def run_and_cleanup(dry_run: bool = False) -> None:
    redis = get_redis()

    try:
        await run(dry_run=dry_run)
    finally:
        try:
            await engine.dispose()
        finally:
            await redis.aclose()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Send Pairza promotional engagement notifications."
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List eligible users without sending pushes.",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    asyncio.run(run_and_cleanup(dry_run=args.dry_run))


if __name__ == "__main__":
    main()