import argparse
import asyncio
import json
import sys

from pywebpush import WebPushException, webpush
from sqlalchemy import select

from app.common.database import AsyncSessionLocal
from app.config.settings import get_settings
from app.notifications.models import PushSubscription
from app.users.models import User

settings = get_settings()


async def find_subscription(email: str):
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(PushSubscription)
            .join(User, PushSubscription.user_id == User.id)
            .where(User.email == email)
            .order_by(PushSubscription.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()


async def main(email: str) -> int:
    if not settings.VAPID_PUBLIC_KEY or not settings.VAPID_PRIVATE_KEY:
        print("ERROR: VAPID keys are not configured in the API environment.")
        return 1

    subscription = await find_subscription(email)

    if subscription is None:
        print("ERROR: No push subscription found for that email.")
        print("Sign in to Pairza and enable reminders first.")
        return 1

    subscription_info = {
        "endpoint": subscription.endpoint,
        "keys": {
            "p256dh": subscription.p256dh_key,
            "auth": subscription.auth_key,
        },
    }

    payload = {
        "title": "Pairza — Test Notification",
        "body": "Push delivery is working! Your next mystery awaits.",
        "url": "/profile",
        "tag": "pairza-test-push",
    }

    try:
        response = webpush(
            subscription_info=subscription_info,
            data=json.dumps(payload),
            vapid_private_key=settings.VAPID_PRIVATE_KEY,
            vapid_claims={"sub": settings.VAPID_SUBJECT},
            ttl=300,
        )
        print(f"Push service accepted the notification: HTTP {response.status_code}.")
        print("Check your device for the Pairza test notification.")
        return 0

    except WebPushException as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        print(f"ERROR: Push delivery failed. HTTP status: {status or 'unknown'}.")

        if status in (404, 410):
            print("This browser subscription may have expired. Re-enable reminders.")

        elif status in (401, 403):
            print("Check that the API's VAPID public/private keys are a matching pair.")

        else:
            print("Check the API environment and push-service response.")

        return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Send one Pairza test push.")
    parser.add_argument("--email", required=True, help="Email of the subscribed Pairza user")
    args = parser.parse_args()

    sys.exit(asyncio.run(main(args.email)))