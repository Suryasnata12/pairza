from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.database import get_db
from app.common.deps import get_current_user
from datetime import datetime, timezone
from app.common.redis_client import RedisKeys, get_redis
from app.matchmaking import service
from app.matchmaking.schemas import MatchmakingStatusResponse
from app.users.models import User

router = APIRouter(prefix="/api/matchmaking", tags=["matchmaking"])
async def _include_waiting_since(result: dict, user_id, redis) -> dict:
    if result.get("status") != "waiting":
        return result

    score = await redis.zscore(
        RedisKeys.MATCHMAKING_POOL,
        str(user_id),
    )

    result["waiting_since"] = (
        datetime.fromtimestamp(score, tz=timezone.utc)
        if score is not None
        else None
    )

    return result

def _to_response(result: dict) -> MatchmakingStatusResponse:
    session = result.get("session")
    if session is None:
        return MatchmakingStatusResponse(status=result["status"], waiting_since=result.get("waiting_since"),)
    return MatchmakingStatusResponse(
        status=result["status"], session_id=session.id, expires_at=session.expires_at
    )


@router.post("/join", response_model=MatchmakingStatusResponse)
async def join(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    redis = get_redis()
    result = await service.join_matchmaking(db, redis, user)
    result = await _include_waiting_since(result, user.id, redis)
    return _to_response(result)


@router.get("/status", response_model=MatchmakingStatusResponse)
async def status(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    redis = get_redis()
    result = await service.get_status(db, redis, user)
    result = await _include_waiting_since(result, user.id, redis)
    return _to_response(result)


@router.post("/leave")
async def leave(user: User = Depends(get_current_user)):
    await service.leave_matchmaking(get_redis(), user)
    return {"status": "left"}
