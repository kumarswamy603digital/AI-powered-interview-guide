from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.db.base import Base


class InterviewSession(Base):
    __tablename__ = "interview_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    # Set when HR interviews a candidate for a specific requisition. Null for
    # self-service practice sessions, which must keep working unchanged.
    candidate_id = Column(Integer, ForeignKey("candidates.id"), nullable=True, index=True)
    job_requisition_id = Column(
        Integer, ForeignKey("job_requisitions.id"), nullable=True, index=True
    )

    target_role = Column(String(255), nullable=False)
    difficulty = Column(String(32), nullable=False)
    personality_mode = Column(String(32), nullable=False)

    resume_text = Column(Text, nullable=False)

    status = Column(String(32), default="active", nullable=False)  # active|ended
    question_index = Column(Integer, default=0, nullable=False)

    # Scores persisted once, when the interview ends. Analytics and ranking read
    # these instead of regenerating the report on every request.
    overall_score = Column(Float, nullable=True)
    skill_scores = Column(JSON, nullable=True)  # [{"name","score","comment"}]
    report_summary = Column(Text, nullable=True)
    report_strengths = Column(JSON, nullable=True)
    report_weaknesses = Column(JSON, nullable=True)
    scored_at = Column(DateTime, nullable=True)

    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    ended_at = Column(DateTime, nullable=True)

    user = relationship("User", backref="interview_sessions")
    candidate = relationship("Candidate", back_populates="interview_sessions")
    job_requisition = relationship("JobRequisition")
    turns = relationship(
        "InterviewTurn",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="InterviewTurn.turn_index",
    )


class InterviewTurn(Base):
    __tablename__ = "interview_turns"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(
        Integer, ForeignKey("interview_sessions.id"), nullable=False, index=True
    )

    role = Column(String(16), nullable=False)  # assistant|user
    content = Column(Text, nullable=False)
    turn_index = Column(Integer, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    session = relationship("InterviewSession", back_populates="turns")

