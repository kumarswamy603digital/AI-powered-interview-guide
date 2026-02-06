from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_optional
from app.core.live_interview import next_question_gemini, next_question_mock
from app.crud.interview import (
    add_turn,
    create_session,
    end_session,
    get_session,
    list_turns,
    set_question_index,
)
from app.db.session import get_db
from app.models.user import User
from app.schemas.live_interview import (
    LiveInterviewEndResponse,
    LiveInterviewStartRequest,
    LiveInterviewStartResponse,
    LiveInterviewSubmitRequest,
    LiveInterviewSubmitResponse,
)


router = APIRouter(prefix="/api/interviews/live", tags=["interviews-live"])

DbSessionDep = Annotated[Session, Depends(get_db)]
OptionalUserDep = Annotated[Optional[User], Depends(get_current_user_optional)]


@router.post("/start", response_model=LiveInterviewStartResponse, status_code=status.HTTP_201_CREATED)
def start_live_interview(
    payload: LiveInterviewStartRequest,
    db: DbSessionDep,
    user: OptionalUserDep,
) -> LiveInterviewStartResponse:
    session = create_session(
        db,
        user_id=user.id if user else None,
        resume_text=payload.resume_text,
        target_role=payload.target_role,
        difficulty=payload.difficulty,
        personality_mode=payload.personality_mode,
    )

    # First question (no last answer yet)
    nq = next_question_gemini(
        resume_text=session.resume_text,
        target_role=session.target_role,
        difficulty=payload.difficulty,
        personality_mode=payload.personality_mode,
        transcript=[],
        question_index=0,
        max_questions=payload.max_questions,
    ) or next_question_mock(
        target_role=session.target_role,
        difficulty=payload.difficulty,
        personality_mode=payload.personality_mode,
        question_index=0,
        last_answer=None,
        max_questions=payload.max_questions,
    )

    add_turn(db, session_id=session.id, role="assistant", content=nq.question, turn_index=0)
    set_question_index(db, session, question_index=0)

    return LiveInterviewStartResponse(id=session.id, first_question=nq.question, question_index=0)


@router.post("/{id}/submit", response_model=LiveInterviewSubmitResponse)
def submit_answer(
    id: int,
    payload: LiveInterviewSubmitRequest,
    db: DbSessionDep,
    user: OptionalUserDep,
) -> LiveInterviewSubmitResponse:
    session = get_session(db, session_id=id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview session not found")

    if session.status != "active":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Interview session has ended")

    # If session is bound to a user, enforce ownership
    if session.user_id is not None and (not user or user.id != session.user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")

    turns = list_turns(db, session_id=session.id)
    next_turn_index = len(turns)
    add_turn(db, session_id=session.id, role="user", content=payload.answer, turn_index=next_turn_index)

    transcript = [{"role": t.role, "content": t.content} for t in turns] + [
        {"role": "user", "content": payload.answer}
    ]

    # Generate next question
    # Increment question index on non-follow-up. We'll detect follow-up from model/mock.
    candidate_next_index = session.question_index + 1

    nq = next_question_gemini(
        resume_text=session.resume_text,
        target_role=session.target_role,
        difficulty=session.difficulty,  # stored as string but matches Difficulty literal
        personality_mode=session.personality_mode,
        transcript=transcript,
        question_index=session.question_index,
        max_questions=25,
    )

    if nq is None:
        nq = next_question_mock(
            target_role=session.target_role,
            difficulty=session.difficulty,  # type: ignore[arg-type]
            personality_mode=session.personality_mode,  # type: ignore[arg-type]
            question_index=session.question_index,
            last_answer=payload.answer,
            max_questions=25,
        )

    # Update question index: follow-ups do not increment; new questions do.
    new_index = session.question_index if nq.is_follow_up else candidate_next_index
    set_question_index(db, session, question_index=new_index)

    turns2 = list_turns(db, session_id=session.id)
    add_turn(db, session_id=session.id, role="assistant", content=nq.question, turn_index=len(turns2))

    return LiveInterviewSubmitResponse(
        id=session.id,
        next_question=nq.question,
        question_index=new_index,
        is_follow_up=nq.is_follow_up,
    )


@router.post("/{id}/end", response_model=LiveInterviewEndResponse)
def end_live_interview(
    id: int,
    db: DbSessionDep,
    user: OptionalUserDep,
) -> LiveInterviewEndResponse:
    session = get_session(db, session_id=id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview session not found")

    if session.user_id is not None and (not user or user.id != session.user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")

    if session.status != "ended":
        session = end_session(db, session)

    turns = list_turns(db, session_id=session.id)
    return LiveInterviewEndResponse(
        id=session.id,
        status=session.status,
        total_turns=len(turns),
        ended_at=session.ended_at.isoformat() if session.ended_at else None,
    )

