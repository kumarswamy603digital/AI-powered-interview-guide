from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.interview import InterviewSession, InterviewTurn


def create_session(
    db: Session,
    *,
    user_id: Optional[int],
    resume_text: str,
    target_role: str,
    difficulty: str,
    personality_mode: str,
) -> InterviewSession:
    session = InterviewSession(
        user_id=user_id,
        resume_text=resume_text,
        target_role=target_role,
        difficulty=difficulty,
        personality_mode=personality_mode,
        status="active",
        question_index=0,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def get_session(db: Session, session_id: int) -> Optional[InterviewSession]:
    return db.query(InterviewSession).filter(InterviewSession.id == session_id).first()


def add_turn(
    db: Session,
    *,
    session_id: int,
    role: str,
    content: str,
    turn_index: int,
) -> InterviewTurn:
    turn = InterviewTurn(
        session_id=session_id,
        role=role,
        content=content,
        turn_index=turn_index,
    )
    db.add(turn)
    db.commit()
    db.refresh(turn)
    return turn


def list_turns(db: Session, session_id: int) -> list[InterviewTurn]:
    return (
        db.query(InterviewTurn)
        .filter(InterviewTurn.session_id == session_id)
        .order_by(InterviewTurn.turn_index.asc())
        .all()
    )


def set_question_index(db: Session, session: InterviewSession, question_index: int) -> InterviewSession:
    session.question_index = question_index
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def end_session(db: Session, session: InterviewSession) -> InterviewSession:
    session.status = "ended"
    session.ended_at = datetime.utcnow()
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def list_sessions_for_user(db: Session, user_id: int) -> list[InterviewSession]:
    return (
        db.query(InterviewSession)
        .filter(InterviewSession.user_id == user_id)
        .order_by(InterviewSession.started_at.asc())
        .all()
    )

