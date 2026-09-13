from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.db.base import Base


# Candidate pipeline stages, in order.
CANDIDATE_STAGES = (
    "applied",
    "screened",
    "interviewed",
    "recommended",
    "rejected",
    "hired",
)

JOB_STATUSES = ("open", "on_hold", "closed")


class JobRequisition(Base):
    """
    A role the organisation is hiring for.

    This is the 'job requirements' data source: without explicit required skills
    there is nothing to rank candidates against, which is why the target role
    cannot just be a free-text string.
    """

    __tablename__ = "job_requisitions"

    id = Column(Integer, primary_key=True, index=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    title = Column(String(255), nullable=False)
    department = Column(String(128), nullable=True)
    seniority = Column(String(64), nullable=True)
    location = Column(String(128), nullable=True)
    employment_type = Column(String(64), nullable=True)

    description = Column(Text, nullable=True)

    # Lists of skill strings. JSON keeps them queryable-enough for SQLite while
    # avoiding a join table that this scope does not need.
    required_skills = Column(JSON, nullable=False, default=list)
    preferred_skills = Column(JSON, nullable=False, default=list)

    min_years_experience = Column(Float, nullable=True)

    status = Column(String(32), default="open", nullable=False)  # open|on_hold|closed
    headcount = Column(Integer, default=1, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    created_by = relationship("User", backref="job_requisitions")
    candidates = relationship("Candidate", back_populates="job_requisition")


class Candidate(Base):
    """
    A person being considered for a role.

    Distinct from User on purpose: candidates are records managed by HR, not
    accounts that log in. Previously the only 'candidate' was the logged-in user
    interviewing themselves, which made cross-candidate ranking impossible.
    """

    __tablename__ = "candidates"

    id = Column(Integer, primary_key=True, index=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    job_requisition_id = Column(
        Integer, ForeignKey("job_requisitions.id"), nullable=True, index=True
    )

    full_name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=True, index=True)
    phone = Column(String(64), nullable=True)

    current_title = Column(String(255), nullable=True)
    years_experience = Column(Float, nullable=True)
    source = Column(String(128), nullable=True)  # referral|job board|agency|...

    stage = Column(String(32), default="applied", nullable=False)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    created_by = relationship("User", backref="candidates")
    job_requisition = relationship("JobRequisition", back_populates="candidates")
    resumes = relationship("Resume", back_populates="candidate")
    interview_sessions = relationship("InterviewSession", back_populates="candidate")
