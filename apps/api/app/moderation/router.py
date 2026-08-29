import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.database import get_db
from app.common.deps import get_current_user
from app.moderation import service
from app.moderation.schemas import BlockCreate, BlockOut, ReportCreate, ReportOut
from app.users.models import User

router = APIRouter(prefix="/api", tags=["moderation"])


@router.post("/reports", response_model=ReportOut, status_code=201)
async def report_user(payload: ReportCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await service.create_report(
        db, user.id, payload.reported_user_id, payload.session_id, payload.reason, payload.details
    )


@router.post("/blocks", response_model=BlockOut, status_code=201)
async def create_block(payload: BlockCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await service.block_user(db, user.id, payload.blocked_id)


@router.get("/blocks", response_model=list[BlockOut])
async def get_blocks(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await service.list_blocks(db, user.id)


@router.delete("/blocks/{blocked_id}", status_code=204)
async def delete_block(blocked_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await service.unblock_user(db, user.id, blocked_id)
