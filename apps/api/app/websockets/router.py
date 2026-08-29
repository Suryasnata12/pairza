"""
WS /api/ws/session/{session_id} — spec section 20's real-time transport.

Auth over WebSocket doesn't get an Authorization header from browsers, so
we accept the access token as a query param (`?token=...`), which is the
standard pragmatic approach for browser-native WebSocket auth.
"""
import json
import uuid

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.chat import service as chat_service
from app.chat.models import Message
from app.common.database import AsyncSessionLocal
from app.common.mixins import utcnow
from app.common.redis_client import RedisKeys, get_redis
from app.common.security import TokenType, decode_token
from app.config.settings import get_settings
from app.sessions.models import MysterySession
from app.websockets.manager import manager

router = APIRouter()
settings = get_settings()


async def _authenticate(token: str | None, ticket: str | None) -> uuid.UUID | None:
    if ticket:
        redis = get_redis()
        key = f"pairza:ws_ticket:{ticket}"
        user_id_str = await redis.get(key)
        if user_id_str:
            await redis.delete(key)  # single-use
            return uuid.UUID(user_id_str)
        return None
    if token:
        payload = decode_token(token)
        if not payload or payload.get("type") != TokenType.ACCESS.value:
            return None
        return uuid.UUID(payload["sub"])
    return None


@router.websocket("/api/ws/session/{session_id}")
async def session_socket(
    websocket: WebSocket, session_id: uuid.UUID,
    token: str | None = Query(default=None), ticket: str | None = Query(default=None),
):
    user_id = await _authenticate(token, ticket)
    if user_id is None:
        await websocket.close(code=4401)
        return

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(MysterySession).where(MysterySession.id == session_id))
        session = result.scalar_one_or_none()
        if session is None or session.role_for(user_id) is None:
            await websocket.close(code=4403)
            return
        if session.status not in ("ACTIVE", "WAITING"):
            await websocket.close(code=4409)
            return
        partner_id = session.partner_id(user_id)

    partner_was_online = manager.is_online(session_id, partner_id) if partner_id else False
    await manager.connect(session_id, user_id, websocket)
    await manager.broadcast(session_id, "user.online", {"user_id": str(user_id)}, exclude_user=user_id)

    # First time both participants have ever been in the room together —
    # drop a persisted "partner_joined" system message, once per session.
    if partner_was_online:
        async with AsyncSessionLocal() as db:
            existing = await db.execute(
                select(Message).where(Message.session_id == session_id, Message.type == "partner_joined")
            )
            if existing.scalar_one_or_none() is None:
                msg = await chat_service.create_message(
                    db, session_id, None, "partner_joined", "Your stranger has entered the investigation."
                )
                await manager.broadcast(session_id, "message.created", {
                    "id": str(msg.id), "session_id": str(session_id), "sender_id": None,
                    "type": "partner_joined", "content": msg.content, "created_at": msg.created_at.isoformat(),
                })

    redis = get_redis()
    await redis.hset(RedisKeys.PRESENCE, str(user_id), str(utcnow().timestamp()))

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue

            event_type = data.get("type")

            if event_type == "message.send":
                content = (data.get("content") or "").strip()
                if not content or len(content) > 2000:
                    continue

                limit_key = RedisKeys.RATE_LIMIT.format(scope="ws_message", identity=str(user_id))
                count = await redis.incr(limit_key)
                if count == 1:
                    await redis.expire(limit_key, 60)
                if count > settings.RATE_LIMIT_MESSAGES_PER_MINUTE:
                    await manager.send_to_user(session_id, user_id, "error", {"message": "Slow down a little — you're sending messages too fast."})
                    continue

                if not chat_service.passes_content_safety(content):
                    await manager.send_to_user(session_id, user_id, "error", {"message": "That message couldn't be sent."})
                    continue

                async with AsyncSessionLocal() as db:
                    msg = await chat_service.create_message(db, session_id, user_id, "normal", content)

                await manager.broadcast(session_id, "message.created", {
                    "id": str(msg.id), "session_id": str(session_id), "sender_id": str(user_id),
                    "type": "normal", "content": msg.content, "created_at": msg.created_at.isoformat(),
                })

            elif event_type == "typing":
                await manager.broadcast(session_id, "user.typing", {"user_id": str(user_id)}, exclude_user=user_id)

    except (WebSocketDisconnect, RuntimeError):
        # RuntimeError covers the rare case where the ASGI server tears down
        # the socket mid-receive (e.g. abrupt process shutdown) without a
        # clean disconnect frame — either way, the outcome is "this
        # connection is gone," so it's treated identically to a normal
        # disconnect rather than surfacing a stack trace.
        pass
    finally:
        manager.disconnect(session_id, user_id, websocket)
        await manager.broadcast(session_id, "user.offline", {"user_id": str(user_id)}, exclude_user=user_id)
