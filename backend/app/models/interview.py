from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.db.base import Base


class InterviewSession(Base):
    __tablename__ = "interview_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    target_role = Column(String(255), nullable=False)
    difficulty = Column(String(32), nullable=False)
    personality_mode = Column(String(32), nullable=False)

    resume_text = Column(Text, nullable=False)

    status = Column(String(32), default="active", nullable=False)  # active|ended
    question_index = Column(Integer, default=0, nullable=False)

    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    ended_at = Column(DateTime, nullable=True)

    user = relationship("User", backref="interview_sessions")
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

