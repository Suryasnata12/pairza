import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exceptions import ConflictError
from app.common.mixins import utcnow
from app.moderation.models import Block, Report
from app.rewards import service as rewards_service
from app.sessions.models import MysterySession
from app.sessions.service import _get_mystery_with_stages
from app.websockets.manager import manager


async def _active_session_between(db: AsyncSession, user_a: uuid.UUID, user_b: uuid.UUID) -> MysterySession | None:
    result = await db.execute(
        select(MysterySession).where(
            MysterySession.status == "ACTIVE",
            or_(
                (MysterySession.player_a_id == user_a) & (MysterySession.player_b_id == user_b),
                (MysterySession.player_a_id == user_b) & (MysterySession.player_b_id == user_a),
            ),
        )
    )
    return result.scalars().first()


async def block_user(db: AsyncSession, blocker_id: uuid.UUID, blocked_id: uuid.UUID) -> Block:
    if blocker_id == blocked_id:
        raise ConflictError("You can't block yourself.")

    existing = await db.execute(
        select(Block).where(Block.blocker_id == blocker_id, Block.blocked_id == blocked_id)
    )
    if existing.scalar_one_or_none():
        raise ConflictError("You've already blocked this person.", code="already_blocked")

    block = Block(blocker_id=blocker_id, blocked_id=blocked_id, created_at=utcnow())
    db.add(block)

    # Blocking someone mid-investigation ends it immediately for both sides
    # — nobody should be stuck finishing a mystery with someone they just
    # blocked. Ends as FAILED, not EXPIRED: it stopped early, not out of time.
    session = await _active_session_between(db, blocker_id, blocked_id)
    if session:
        session.status = "FAILED"
        await db.flush()
        mystery = await _get_mystery_with_stages(db, session.mystery_id)
        await rewards_service.process_non_solve(db, session, mystery, "failed")
        await manager.broadcast(session.id, "session.expired", {"session_id": str(session.id), "reason": "blocked"})

    await db.commit()
    await db.refresh(block)
    return block


async def unblock_user(db: AsyncSession, blocker_id: uuid.UUID, blocked_id: uuid.UUID) -> None:
    result = await db.execute(select(Block).where(Block.blocker_id == blocker_id, Block.blocked_id == blocked_id))
    block = result.scalar_one_or_none()
    if block:
        await db.delete(block)
        await db.commit()


async def list_blocks(db: AsyncSession, blocker_id: uuid.UUID) -> list[Block]:
    result = await db.execute(select(Block).where(Block.blocker_id == blocker_id).order_by(Block.created_at.desc()))
    return list(result.scalars().all())


async def create_report(db: AsyncSession, reporter_id: uuid.UUID, reported_user_id: uuid.UUID, session_id: uuid.UUID | None, reason: str, details: str | None) -> Report:
    if reporter_id == reported_user_id:
        raise ConflictError("You can't report yourself.")
    report = Report(
        reporter_id=reporter_id, reported_user_id=reported_user_id, session_id=session_id,
        reason=reason, details=details, status="open", created_at=utcnow(),
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)
    return report
