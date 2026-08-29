from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.database import get_db
from app.common.deps import get_current_user
from app.common.redis_client import get_redis
from app.matchmaking import service
from app.matchmaking.schemas import MatchmakingStatusResponse
from app.users.models import User

router = APIRouter(prefix="/api/matchmaking", tags=["matchmaking"])


def _to_response(result: dict) -> MatchmakingStatusResponse:
    session = result.get("session")
    if session is None:
        return MatchmakingStatusResponse(status=result["status"])
    return MatchmakingStatusResponse(
        status=result["status"], session_id=session.id, expires_at=session.expires_at
    )


@router.post("/join", response_model=MatchmakingStatusResponse)
async def join(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await service.join_matchmaking(db, get_redis(), user)
    return _to_response(result)


@router.get("/status", response_model=MatchmakingStatusResponse)
async def status(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await service.get_status(db, get_redis(), user)
    return _to_response(result)


@router.post("/leave")
async def leave(user: User = Depends(get_current_user)):
    await service.leave_matchmaking(get_redis(), user)
    return {"status": "left"}
