"""
The authoritative core of the investigation workspace. Three rules this
module never breaks (spec sections 14/16/17):

  1. The backend is the only clock that matters — expiry is checked here,
     on access, never trusted from the client.
  2. A player only ever sees their OWN clue for a stage, never their
     partner's — complementary information is the entire mechanic.
  3. A session becomes terminal (SOLVED/FAILED/EXPIRED) exactly once; the
     `with_for_update` row lock below is what makes that true even if two
     requests race (e.g. the background sweeper and a live answer submit).
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.chat.models import Message
from app.common.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.common.mixins import utcnow
from app.matchmaking.service import partner_profile_teaser
from app.mysteries.models import Mystery, MysteryStage
from app.mysteries.schemas import ClueOut, MysteryDetailForSession, StageOut
from app.mysteries.service import answer_matches
from app.rewards import service as rewards_service
from app.sessions.models import InvestigationEvidence, Memory, MysterySession, MysterySubmission
from app.sessions.schemas import (
    AnswerSubmitResponse,
    EvidenceCreate,
    EvidenceOut,
    PartnerTeaser,
    SessionDetailResponse,
)
from app.users.models import UserPreferences
from app.websockets.manager import manager


async def get_current_session(db: AsyncSession, user_id: uuid.UUID) -> MysterySession | None:
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(MysterySession).where(
            MysterySession.status.in_(["WAITING", "ACTIVE"]),
            MysterySession.expires_at > now,
            (MysterySession.player_a_id == user_id) | (MysterySession.player_b_id == user_id),
        )
    )
    return result.scalars().first()


async def _load_owned_session(db: AsyncSession, session_id: uuid.UUID, user_id: uuid.UUID, lock: bool = False) -> MysterySession:
    query = select(MysterySession).where(MysterySession.id == session_id)
    if lock:
        query = query.with_for_update()
    result = await db.execute(query)
    session = result.scalar_one_or_none()
    if session is None:
        raise NotFoundError("This mystery session doesn't exist.")
    if session.role_for(user_id) is None:
        raise ForbiddenError("This isn't your investigation.")
    return session


async def _get_mystery_with_stages(db: AsyncSession, mystery_id: uuid.UUID) -> Mystery:
    result = await db.execute(
        select(Mystery)
        .options(selectinload(Mystery.stages).selectinload(MysteryStage.clues))
        .where(Mystery.id == mystery_id)
    )
    return result.scalar_one()


async def ensure_not_expired(db: AsyncSession, session: MysterySession) -> MysterySession:
    """Lazy expiry-on-access. Re-fetches with a row lock so a concurrent
    background sweep and a live request can't both try to finalize it."""
    if session.status not in ("ACTIVE", "WAITING"):
        return session
    now = datetime.now(timezone.utc)
    if now < session.expires_at:
        return session

    locked = await _load_owned_session(db, session.id, session.player_a_id, lock=True)
    if locked.status not in ("ACTIVE", "WAITING") or now < locked.expires_at:
        return locked

    locked.status = "EXPIRED"
    await db.flush()
    mystery = await _get_mystery_with_stages(db, locked.mystery_id)
    await rewards_service.process_non_solve(db, locked, mystery, "expired")
    await manager.broadcast(locked.id, "session.expired", {"session_id": str(locked.id)})
    return locked


async def sweep_expired_sessions(db: AsyncSession) -> int:
    """Called by the background task in main.py every ~30s so `session.expired`
    fires proactively over the WebSocket instead of only lazily on next access."""
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(MysterySession).where(MysterySession.status == "ACTIVE", MysterySession.expires_at <= now)
    )
    expired = list(result.scalars().all())
    for session in expired:
        await ensure_not_expired(db, session)
    return len(expired)


async def sweep_expiring_warnings(db: AsyncSession, warning_window) -> int:
    """Fires the one-time `session.expiring` heads-up used for the countdown's urgent-color treatment."""
    now = datetime.now(timezone.utc)
    threshold = now + warning_window
    result = await db.execute(
        select(MysterySession).where(
            MysterySession.status == "ACTIVE",
            MysterySession.expires_at <= threshold,
            MysterySession.expires_at > now,
            MysterySession.expiring_notice_sent.is_(False),
        )
    )
    sessions = list(result.scalars().all())
    for session in sessions:
        session.expiring_notice_sent = True
        seconds_left = int((session.expires_at - now).total_seconds())
        await manager.broadcast(session.id, "session.expiring", {"seconds_remaining": seconds_left})
    if sessions:
        await db.commit()
    return len(sessions)


def _build_stage_outs(mystery: Mystery, session: MysterySession, user_id: uuid.UUID) -> list[StageOut]:
    role = session.role_for(user_id)
    stages_out = []
    for stage in sorted(mystery.stages, key=lambda s: s.stage_number):
        if stage.stage_number > session.current_stage_number:
            break  # future stages are not just locked — they're not revealed to the client at all
        your_clue = next((c for c in stage.clues if c.role == role), None)
        stages_out.append(
            StageOut(
                id=stage.id, stage_number=stage.stage_number, is_final=stage.is_final,
                context=stage.context, unlocked=True,
                your_clue=ClueOut.model_validate(your_clue) if your_clue else None,
            )
        )
    return stages_out


async def build_session_detail(db: AsyncSession, session: MysterySession, user_id: uuid.UUID) -> SessionDetailResponse:
    mystery = await _get_mystery_with_stages(db, session.mystery_id)

    partner_profile = await partner_profile_teaser(db, session, user_id)
    partner_teaser = None
    if partner_profile:
        prefs_result = await db.execute(select(UserPreferences).where(UserPreferences.user_id == partner_profile.user_id))
        prefs = prefs_result.scalar_one_or_none()
        partner_teaser = PartnerTeaser(
            country_code=partner_profile.country_code,
            timezone_region=prefs.timezone_region if prefs else "UTC",
            interests=prefs.interests if prefs else [],
            language=prefs.language if prefs else "en",
            puzzle_experience_level=prefs.puzzle_experience_level if prefs else "beginner",
        )

    evidence_result = await db.execute(
        select(InvestigationEvidence).where(InvestigationEvidence.session_id == session.id).order_by(InvestigationEvidence.created_at)
    )
    evidence_list = evidence_result.scalars().all()

    wrong_count_result = await db.execute(
        select(func.count()).select_from(MysterySubmission).where(
            MysterySubmission.session_id == session.id, MysterySubmission.is_correct.is_(False)
        )
    )

    now = datetime.now(timezone.utc)
    seconds_remaining = max(0, int((session.expires_at - now).total_seconds()))

    return SessionDetailResponse(
        id=session.id, status=session.status, current_stage_number=session.current_stage_number,
        started_at=session.started_at, expires_at=session.expires_at, seconds_remaining=seconds_remaining,
        solved_at=session.solved_at, your_role=session.role_for(user_id),
        mystery=MysteryDetailForSession(
            id=mystery.id, title=mystery.title, category=mystery.category, difficulty=mystery.difficulty,
            flavor_text=mystery.flavor_text, stages=_build_stage_outs(mystery, session, user_id),
        ),
        partner=partner_teaser,
        partner_id=session.partner_id(user_id),
        evidence=[EvidenceOut.model_validate(e) for e in evidence_list],
        wrong_attempt_count=wrong_count_result.scalar_one(),
    )


async def add_evidence(db: AsyncSession, session: MysterySession, user_id: uuid.UUID, payload: EvidenceCreate) -> EvidenceOut:
    if session.status != "ACTIVE":
        raise ConflictError("This investigation has already ended.")
    evidence = InvestigationEvidence(
        session_id=session.id, submitted_by=user_id, title=payload.title,
        content=payload.content, source_url=payload.source_url, created_at=utcnow(),
    )
    db.add(evidence)
    await db.commit()
    await db.refresh(evidence)

    out = EvidenceOut.model_validate(evidence)
    await manager.broadcast(session.id, "evidence.added", out.model_dump(mode="json"))
    return out


async def list_messages(db: AsyncSession, session_id: uuid.UUID) -> list[Message]:
    result = await db.execute(select(Message).where(Message.session_id == session_id).order_by(Message.created_at))
    return list(result.scalars().all())


async def submit_answer(db: AsyncSession, session: MysterySession, user_id: uuid.UUID, answer_text: str) -> AnswerSubmitResponse:
    locked_session = await _load_owned_session(db, session.id, user_id, lock=True)

    if locked_session.status != "ACTIVE":
        raise ConflictError("This investigation has already ended.")

    mystery = await _get_mystery_with_stages(db, locked_session.mystery_id)
    current_stage = next(s for s in mystery.stages if s.stage_number == locked_session.current_stage_number)

    if current_stage.is_final:
        is_correct = answer_matches(answer_text, mystery.final_answer_patterns)
    else:
        patterns = current_stage.checkpoint_answer_patterns or []
        is_correct = bool(patterns) and answer_matches(answer_text, patterns)

    db.add(MysterySubmission(
        session_id=locked_session.id, stage_id=current_stage.id, submitted_by=user_id,
        answer_text=answer_text, is_correct=is_correct, created_at=utcnow(),
    ))

    if not is_correct:
        await db.commit()
        await manager.broadcast(
            locked_session.id, "answer.incorrect",
            {"submitted_by": str(user_id), "stage_number": current_stage.stage_number}, 
        )
        return AnswerSubmitResponse(
            is_correct=False, session_status=locked_session.status,
            current_stage_number=locked_session.current_stage_number,
            message="Not quite it. Compare notes with your stranger and try again.",
        )

    if current_stage.is_final:
        locked_session.status = "SOLVED"
        locked_session.solved_at = utcnow()
        await db.flush()
        results = await rewards_service.process_solve(db, locked_session, mystery)
        my_result = results[user_id]

        from app.chat.service import create_message
        sys_msg = await create_message(db, locked_session.id, None, "discovery", "Mystery solved. Case closed.")
        await manager.broadcast(locked_session.id, "message.created", {
            "id": str(sys_msg.id), "session_id": str(locked_session.id), "sender_id": None,
            "type": "discovery", "content": sys_msg.content, "created_at": sys_msg.created_at.isoformat(),
        })

        await manager.broadcast(locked_session.id, "mystery.solved", {
            "solved_by": str(user_id),
            "solve_seconds": (locked_session.solved_at - locked_session.started_at).total_seconds(),
        })
        for uid, r in results.items():
            if r["new_badge_codes"]:
                await manager.send_to_user(locked_session.id, uid, "reward.unlocked", {
                    "xp_awarded": r["xp_awarded"], "new_badge_codes": r["new_badge_codes"],
                })

        return AnswerSubmitResponse(
            is_correct=True, session_status="SOLVED", current_stage_number=locked_session.current_stage_number,
            message="Solved. Your stranger will see it too.",
            xp_awarded=my_result["xp_awarded"], new_badges=my_result["new_badge_codes"],
        )

    # Correct checkpoint on a non-final stage: advance.
    locked_session.current_stage_number += 1
    await db.flush()
    from app.chat.service import create_message
    sys_msg = await create_message(
        db, locked_session.id, None, "system",
        f"Stage {locked_session.current_stage_number} unlocked. New clues are waiting for both of you.",
    )
    await db.commit()
    await manager.broadcast(locked_session.id, "mystery.progress", {
        "new_stage_number": locked_session.current_stage_number,
    })
    await manager.broadcast(locked_session.id, "message.created", {
        "id": str(sys_msg.id), "session_id": str(locked_session.id), "sender_id": None,
        "type": "system", "content": sys_msg.content, "created_at": sys_msg.created_at.isoformat(),
    })
    return AnswerSubmitResponse(
        is_correct=True, session_status="ACTIVE", current_stage_number=locked_session.current_stage_number,
        message="That's it — the next stage just unlocked for both of you.",
    )
