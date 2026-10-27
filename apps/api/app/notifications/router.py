import hashlib

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.database import get_db
from app.common.deps import get_current_user
from app.config.settings import get_settings
from app.notifications.models import PushSubscription
from app.notifications.schemas import (
    PushSubscriptionCreate,
    PushSubscriptionDelete,
)
from app.users.models import User

router = APIRouter(prefix="/api/notifications", tags=["notifications"])
settings = get_settings()


def _endpoint_hash(endpoint: str) -> str:
    return hashlib.sha256(endpoint.encode("utf-8")).hexdigest()


@router.get("/public-key")
async def get_public_key():
    """Return the VAPID public key needed by the browser."""
    if not settings.VAPID_PUBLIC_KEY:
        raise HTTPException(
            status_code=503,
            detail="Push notifications are not configured.",
        )

    return {"public_key": settings.VAPID_PUBLIC_KEY}


@router.post("/subscribe", status_code=201)
async def subscribe_push(
    payload: PushSubscriptionCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create or update the current user's browser subscription."""
    if not settings.VAPID_PUBLIC_KEY or not settings.VAPID_PRIVATE_KEY:
        raise HTTPException(
            status_code=503,
            detail="Push notifications are not configured.",
        )

    endpoint_hash = _endpoint_hash(payload.endpoint)

    result = await db.execute(
        select(PushSubscription).where(
            PushSubscription.endpoint_hash == endpoint_hash
        )
    )
    subscription = result.scalar_one_or_none()

    if subscription is None:
        subscription = PushSubscription(
            user_id=user.id,
            endpoint=payload.endpoint,
            endpoint_hash=endpoint_hash,
            p256dh_key=payload.keys.p256dh,
            auth_key=payload.keys.auth,
        )
        db.add(subscription)
    else:
        # A browser endpoint can belong to only one Pairza account.
        subscription.user_id = user.id
        subscription.endpoint = payload.endpoint
        subscription.p256dh_key = payload.keys.p256dh
        subscription.auth_key = payload.keys.auth

    await db.commit()

    return {"status": "subscribed"}


@router.post("/unsubscribe")
async def unsubscribe_push(
    payload: PushSubscriptionDelete,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove this browser subscription for the authenticated user."""
    await db.execute(
        delete(PushSubscription).where(
            PushSubscription.user_id == user.id,
            PushSubscription.endpoint_hash
            == _endpoint_hash(payload.endpoint),
        )
    )
    await db.commit()

    return {"status": "unsubscribed"}