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

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("/me", response_model=MeResponse)
async def get_me(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    profile = await service.get_profile_by_user_id(db, user.id)
    profile_response = await service.build_profile_response(db, profile)
    return MeResponse(
        id=user.id, email=user.email, is_verified=user.is_verified, is_admin=user.is_admin,
        created_at=user.created_at, profile=profile_response,
    )


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
async def get_public_profile(user_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Public, achievement-only view of another player — used from the Memory Vault / stranger card."""
    result = await db.execute(select(Profile).where(Profile.user_id == user_id))
    profile = result.scalar_one_or_none()
    if not profile:
        raise NotFoundError("That player doesn't exist.")
    return await service.build_profile_response(db, profile)
