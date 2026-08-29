import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat.schemas import MessageOut
from app.common.database import get_db
from app.common.deps import get_current_user
from app.common.exceptions import NotFoundError
from app.sessions import service
from app.sessions.schemas import (
    AnswerSubmitRequest,
    AnswerSubmitResponse,
    EvidenceCreate,
    EvidenceOut,
    SessionDetailResponse,
)
from app.users.models import User

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.get("/current", response_model=SessionDetailResponse | None)
async def get_current(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    session = await service.get_current_session(db, user.id)
    if not session:
        return None
    session = await service.ensure_not_expired(db, session)
    if session.status not in ("ACTIVE", "WAITING"):
        return None
    return await service.build_session_detail(db, session, user.id)


@router.get("/{session_id}", response_model=SessionDetailResponse)
async def get_session(session_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    session = await service._load_owned_session(db, session_id, user.id)
    session = await service.ensure_not_expired(db, session)
    return await service.build_session_detail(db, session, user.id)


@router.post("/{session_id}/answer", response_model=AnswerSubmitResponse)
async def submit_answer(
    session_id: uuid.UUID, payload: AnswerSubmitRequest,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    session = await service._load_owned_session(db, session_id, user.id)
    session = await service.ensure_not_expired(db, session)
    return await service.submit_answer(db, session, user.id, payload.answer_text)


@router.get("/{session_id}/evidence", response_model=list[EvidenceOut])
async def get_evidence(session_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    session = await service._load_owned_session(db, session_id, user.id)
    detail = await service.build_session_detail(db, session, user.id)
    return detail.evidence


@router.post("/{session_id}/evidence", response_model=EvidenceOut, status_code=201)
async def post_evidence(
    session_id: uuid.UUID, payload: EvidenceCreate,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    session = await service._load_owned_session(db, session_id, user.id)
    session = await service.ensure_not_expired(db, session)
    return await service.add_evidence(db, session, user.id, payload)


@router.get("/{session_id}/messages", response_model=list[MessageOut])
async def get_messages(session_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await service._load_owned_session(db, session_id, user.id)  # authorization check
    return await service.list_messages(db, session_id)
