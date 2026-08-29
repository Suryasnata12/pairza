from app.chat.models import Message
from app.common.mixins import utcnow
from sqlalchemy.ext.asyncio import AsyncSession
import uuid

# A minimal placeholder filter — flags obvious slur/harassment patterns so
# the moderation hook exists end-to-end. Swap for a real moderation
# provider (or a proper classifier) before shipping to production; this is
# intentionally not a comprehensive filter.
_BLOCKED_SUBSTRINGS = {"kill yourself", "kys"}


def passes_content_safety(content: str) -> bool:
    lowered = content.lower()
    return not any(bad in lowered for bad in _BLOCKED_SUBSTRINGS)


async def create_message(db: AsyncSession, session_id: uuid.UUID, sender_id: uuid.UUID | None, type_: str, content: str) -> Message:
    message = Message(session_id=session_id, sender_id=sender_id, type=type_, content=content, created_at=utcnow())
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return message
