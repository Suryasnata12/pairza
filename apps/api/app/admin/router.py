import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin import service
from app.admin.schemas import (
    ActiveSessionOut,
    AdminUserOut,
    AnalyticsOut,
    ReportReviewRequest,
    SuspendUserRequest,
)
from app.common.database import get_db
from app.common.deps import get_current_admin
from app.moderation.schemas import ReportOut
from app.mysteries.schemas import MysteryAdminOut, MysteryCreate, MysteryUpdate
from app.users.models import User

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/users", response_model=list[AdminUserOut])
async def list_users(
    search: str | None = None, limit: int = Query(default=50, le=200), offset: int = 0,
    admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db),
):
    rows = await service.list_users(db, search, limit, offset)
    return [
        AdminUserOut(
            id=r["user"].id, email=r["user"].email, username=r["profile"].username,
            country_code=r["profile"].country_code, is_active=r["user"].is_active,
            is_suspended=r["user"].is_suspended, is_banned=r["user"].is_banned, is_admin=r["user"].is_admin,
            created_at=r["user"].created_at, mystery_count=r["profile"].mystery_count,
            solved_count=r["profile"].solved_count,
        )
        for r in rows
    ]


@router.post("/users/{user_id}/suspend")
async def suspend(user_id: uuid.UUID, payload: SuspendUserRequest, admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    await service.suspend_user(db, user_id, payload.reason)
    return {"status": "suspended"}


@router.post("/users/{user_id}/unsuspend")
async def unsuspend(user_id: uuid.UUID, admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    await service.unsuspend_user(db, user_id)
    return {"status": "unsuspended"}


@router.post("/users/{user_id}/ban")
async def ban(user_id: uuid.UUID, payload: SuspendUserRequest, admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    await service.ban_user(db, user_id, payload.reason)
    return {"status": "banned"}


@router.get("/reports", response_model=list[ReportOut])
async def get_reports(status: str | None = None, admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    return await service.list_reports(db, status)


@router.post("/reports/{report_id}/review", response_model=ReportOut)
async def review(report_id: uuid.UUID, payload: ReportReviewRequest, admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    return await service.review_report(db, admin.id, report_id, payload.status)


@router.get("/mysteries", response_model=list[MysteryAdminOut])
async def list_mysteries(category: str | None = None, admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    mysteries = await service.list_mysteries_admin(db, category)
    return [
        MysteryAdminOut(
            id=m.id, title=m.title, category=m.category, difficulty=m.difficulty,
            summary=m.summary, is_published=m.is_published, stage_count=len(m.stages),
        )
        for m in mysteries
    ]


@router.post("/mysteries", response_model=MysteryAdminOut, status_code=201)
async def create_mystery(payload: MysteryCreate, admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    m = await service.create_mystery(db, admin.id, payload)
    return MysteryAdminOut(id=m.id, title=m.title, category=m.category, difficulty=m.difficulty, summary=m.summary, is_published=m.is_published, stage_count=len(payload.stages))


@router.patch("/mysteries/{mystery_id}", response_model=MysteryAdminOut)
async def update_mystery(mystery_id: uuid.UUID, payload: MysteryUpdate, admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    m = await service.update_mystery(db, mystery_id, payload)
    return MysteryAdminOut(id=m.id, title=m.title, category=m.category, difficulty=m.difficulty, summary=m.summary, is_published=m.is_published)


@router.post("/mysteries/{mystery_id}/publish")
async def publish(mystery_id: uuid.UUID, admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    await service.set_publish_state(db, mystery_id, True)
    return {"status": "published"}


@router.post("/mysteries/{mystery_id}/unpublish")
async def unpublish(mystery_id: uuid.UUID, admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    await service.set_publish_state(db, mystery_id, False)
    return {"status": "unpublished"}


@router.post("/mysteries/{mystery_id}/archive")
async def archive(mystery_id: uuid.UUID, admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    await service.set_publish_state(db, mystery_id, False)
    return {"status": "archived"}


@router.get("/sessions/active", response_model=list[ActiveSessionOut])
async def active_sessions(admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    rows = await service.list_active_sessions(db)
    return [
        ActiveSessionOut(
            id=r["session"].id, status=r["session"].status, mystery_title=r["mystery_title"],
            category=r["category"], current_stage_number=r["session"].current_stage_number,
            started_at=r["session"].started_at, expires_at=r["session"].expires_at,
        )
        for r in rows
    ]


@router.get("/analytics", response_model=AnalyticsOut)
async def analytics(admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    return await service.get_analytics(db)
