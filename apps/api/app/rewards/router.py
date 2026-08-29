from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.database import get_db
from app.common.deps import get_current_user
from app.rewards.models import Badge, Reward, UserBadge
from app.rewards.schemas import BadgeOut, MemoryOut, RewardOut
from app.sessions.models import Memory
from app.users.models import User

router = APIRouter(prefix="/api", tags=["rewards"])


@router.get("/badges", response_model=list[BadgeOut])
async def list_badges(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    all_badges = (await db.execute(select(Badge))).scalars().all()
    earned = {
        ub.badge_id: ub.earned_at
        for ub in (await db.execute(select(UserBadge).where(UserBadge.user_id == user.id))).scalars().all()
    }
    return [
        BadgeOut(
            id=b.id, code=b.code, name=b.name, description=b.description, icon=b.icon,
            earned=b.id in earned, earned_at=earned.get(b.id),
        )
        for b in all_badges
    ]


@router.get("/rewards", response_model=list[RewardOut])
async def list_rewards(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Reward).where(Reward.user_id == user.id).order_by(Reward.created_at.desc()).limit(100))
    return result.scalars().all()


@router.get("/memories", response_model=list[MemoryOut])
async def list_memories(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Memory).where(Memory.user_id == user.id).order_by(Memory.created_at.desc())
    )
    return result.scalars().all()
