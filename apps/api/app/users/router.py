import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.database import get_db
from app.common.deps import get_current_user
from app.common.exceptions import NotFoundError
from app.users import service
from app.users.models import Profile, User, UserPreferences
from app.users.schemas import (
    MeResponse,
    ProfileResponse,
    UpdatePreferencesRequest,
    UpdateProfileRequest,
)
from app.config.settings import get_settings #this will remove this after domain verification is done
settings = get_settings()

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("/me", response_model=MeResponse)
async def get_me(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    profile = await service.get_profile_by_user_id(db, user.id)
    profile_response = await service.build_profile_response(db, profile)
    return MeResponse(
        id=user.id, email=user.email, is_verified=user.is_verified or not settings.EMAIL_VERIFICATION_REQUIRED, is_admin=user.is_admin,
        created_at=user.created_at, profile=profile_response,
    ) # or not settings.EMAIL_VERIFICATION_REQUIRED will remove this after domain verification is done


@router.patch("/me", response_model=ProfileResponse)
async def update_me(
    payload: UpdateProfileRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    profile = await service.get_profile_by_user_id(db, user.id)
    if payload.avatar_url is not None:
        profile.avatar_url = payload.avatar_url
    if payload.country_code is not None:
        profile.country_code = payload.country_code.upper()
    await db.commit()
    await db.refresh(profile)
    return await service.build_profile_response(db, profile)


@router.patch("/me/preferences")
async def update_preferences(
    payload: UpdatePreferencesRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(UserPreferences).where(UserPreferences.user_id == user.id))
    prefs = result.scalar_one()
    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(prefs, field, value)
    await db.commit()
    return {"status": "updated"}


@router.get("/{user_id}", response_model=ProfileResponse)
async def get_public_profile(
    user_id: uuid.UUID, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """
    Achievement-only view of another player — used from the Memory Vault / stranger card, both
    already login-only features in the app, so requiring login here closes nothing a legitimate
    caller needs. Requiring auth also means every lookup is now attributable to a real account,
    rather than open to anonymous scraping of every user's stats by iterating user IDs.

    A banned or deactivated account is treated the same as one that doesn't exist: there's no
    reason to let anyone keep viewing a profile Pairza itself has already taken action on.
    """
    result = await db.execute(select(Profile, User).join(User, User.id == Profile.user_id).where(Profile.user_id == user_id))
    row = result.one_or_none()
    if row is None:
        raise NotFoundError("That player doesn't exist.")
    profile, target_user = row
    if not target_user.is_active or target_user.is_banned:
        raise NotFoundError("That player doesn't exist.")
    return await service.build_profile_response(db, profile)
