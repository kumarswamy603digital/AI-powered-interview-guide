from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.db.base import Base


GOAL_STATUSES = ("not_started", "on_track", "at_risk", "missed", "achieved")
FEEDBACK_SOURCES = ("manager", "peer", "self", "skip_level", "customer")


class PerformanceReview(Base):
    """A completed review cycle for one employee."""

    __tablename__ = "performance_reviews"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False, index=True)
    reviewer_id = Column(Integer, ForeignKey("employees.id"), nullable=True)

    # e.g. "2025-H1". Sortable strings keep period ordering trivial.
    period = Column(String(32), nullable=False, index=True)
    review_date = Column(Date, nullable=True)

    # 1-5 where 5 is outstanding.
    rating = Column(Float, nullable=False)
    potential_rating = Column(Float, nullable=True)  # for 9-box style placement

    strengths = Column(JSON, nullable=True)  # list[str]
    improvements = Column(JSON, nullable=True)  # list[str]
    comments = Column(Text, nullable=True)

    promotion_ready = Column(String(32), nullable=True)  # yes|not_yet|no

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    employee = relationship(
        "Employee", back_populates="reviews", foreign_keys=[employee_id]
    )
    reviewer = relationship("Employee", foreign_keys=[reviewer_id])


class Goal(Base):
    """A goal or OKR assigned to an employee."""

    __tablename__ = "goals"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False, index=True)

    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    period = Column(String(32), nullable=True, index=True)

    status = Column(String(32), default="not_started", nullable=False)
    progress = Column(Float, default=0.0, nullable=False)  # 0-100
    weight = Column(Float, default=1.0, nullable=False)

    due_date = Column(Date, nullable=True)
    # Skills this goal is meant to build - links performance to the skill graph.
    related_skills = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    employee = relationship("Employee", back_populates="goals")


class Feedback(Base):
    """A free-text feedback note about an employee."""

    __tablename__ = "feedback"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False, index=True)
    author_id = Column(Integer, ForeignKey("employees.id"), nullable=True)

    source = Column(String(32), default="peer", nullable=False)
    content = Column(Text, nullable=False)

    # Optional pre-computed sentiment; when absent the performance engine infers
    # it from the text so imported feedback still contributes.
    sentiment = Column(Float, nullable=True)  # -1.0 .. 1.0

    given_on = Column(Date, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    employee = relationship(
        "Employee", back_populates="feedback", foreign_keys=[employee_id]
    )
    author = relationship("Employee", foreign_keys=[author_id])
