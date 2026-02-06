from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_optional
from app.core.report import generate_report
from app.core.roadmap import generate_roadmap
from app.crud.interview import get_session, list_turns
from app.db.session import get_db
from app.models.user import User
from app.schemas.report import InterviewReport
from app.schemas.roadmap import CareerRoadmap


router = APIRouter(prefix="/api/reports", tags=["reports"])

DbSessionDep = Annotated[Session, Depends(get_db)]
OptionalUserDep = Annotated[Optional[User], Depends(get_current_user_optional)]


@router.get("/{interview_id}", response_model=InterviewReport)
def get_interview_report(
    interview_id: int,
    db: DbSessionDep,
    user: OptionalUserDep,
) -> InterviewReport:
    session = get_session(db, session_id=interview_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview session not found")

    # Enforce ownership when session is tied to a user
    if session.user_id is not None and (not user or user.id != session.user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")

    turns = list_turns(db, session_id=session.id)
    transcript = [{"role": t.role, "content": t.content} for t in turns]

    return generate_report(
        interview_id=session.id,
        target_role=session.target_role,
        difficulty=session.difficulty,
        personality_mode=session.personality_mode,
        transcript=transcript,
    )


@router.get("/{interview_id}/roadmap", response_model=CareerRoadmap)
def get_career_roadmap(
    interview_id: int,
    db: DbSessionDep,
    user: OptionalUserDep,
) -> CareerRoadmap:
    """
    Generate a personalized career roadmap using the interview report.
    """
    session = get_session(db, session_id=interview_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview session not found")

    if session.user_id is not None and (not user or user.id != session.user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")

    turns = list_turns(db, session_id=session.id)
    transcript = [{"role": t.role, "content": t.content} for t in turns]

    report = generate_report(
        interview_id=session.id,
        target_role=session.target_role,
        difficulty=session.difficulty,
        personality_mode=session.personality_mode,
        transcript=transcript,
    )

    return generate_roadmap(report)

