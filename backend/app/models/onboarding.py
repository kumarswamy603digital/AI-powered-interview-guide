from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.db.base import Base


ONBOARDING_PHASES = ("pre_boarding", "week_1", "day_30", "day_60", "day_90")
TASK_CATEGORIES = (
    "it_setup",
    "compliance",
    "training",
    "role_ramp",
    "social",
    "manager",
    "skill_gap",
)
TASK_STATUSES = ("pending", "in_progress", "done", "skipped")


class OnboardingPlan(Base):
    """
    A generated onboarding journey for one employee.

    Stored rather than computed on the fly so progress can be tracked and so the
    plan an employee actually received is auditable.
    """

    __tablename__ = "onboarding_plans"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False, index=True)

    # Snapshot of the inputs the plan was generated from, so a later change to
    # the employee record does not silently invalidate the stored rationale.
    role = Column(String(255), nullable=True)
    department = Column(String(128), nullable=True)
    seniority = Column(String(64), nullable=True)
    work_mode = Column(String(32), nullable=True)

    buddy_id = Column(Integer, ForeignKey("employees.id"), nullable=True)
    start_date = Column(Date, nullable=True)

    status = Column(String(32), default="active", nullable=False)
    summary = Column(Text, nullable=True)
    # Skills the plan targets, derived from role requirements vs the employee's
    # existing skills.
    targeted_skill_gaps = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    employee = relationship(
        "Employee", back_populates="onboarding_plans", foreign_keys=[employee_id]
    )
    buddy = relationship("Employee", foreign_keys=[buddy_id])
    tasks = relationship(
        "OnboardingTask",
        back_populates="plan",
        cascade="all, delete-orphan",
        order_by="OnboardingTask.day_offset",
    )


class OnboardingTask(Base):
    """One task in an onboarding journey."""

    __tablename__ = "onboarding_tasks"

    id = Column(Integer, primary_key=True, index=True)
    plan_id = Column(Integer, ForeignKey("onboarding_plans.id"), nullable=False, index=True)

    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    phase = Column(String(32), default="week_1", nullable=False)
    category = Column(String(32), default="role_ramp", nullable=False)
    day_offset = Column(Integer, default=0, nullable=False)  # days from start date

    owner = Column(String(128), nullable=True)  # e.g. "IT", "Manager", "Buddy"
    mandatory = Column(Boolean, default=False, nullable=False)
    status = Column(String(32), default="pending", nullable=False)

    # Why this task is in *this* person's plan - what makes the journey adaptive
    # rather than a fixed checklist.
    rationale = Column(Text, nullable=True)
    resource_url = Column(String(1024), nullable=True)

    completed_on = Column(Date, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    plan = relationship("OnboardingPlan", back_populates="tasks")
