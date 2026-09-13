from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.db.base import Base


EMPLOYEE_STATUSES = ("active", "on_leave", "notice_period", "resigned", "terminated")

# Attendance statuses. 'absent' is unplanned; 'leave' is approved and must not
# count towards absenteeism risk.
ATTENDANCE_STATUSES = ("present", "remote", "leave", "absent", "holiday")

PROFICIENCY_LEVELS = (1, 2, 3, 4, 5)

SKILL_IMPORTANCE = ("core", "important", "nice_to_have")
SKILL_HORIZONS = ("current", "future")


class Employee(Base):
    """
    A person employed by the organisation.

    Separate from Candidate (a person being hired) and User (a login account).
    `source_candidate_id` closes the recruitment -> workforce loop: a hired
    candidate becomes an employee carrying their assessed skills with them.
    """

    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, index=True)
    employee_code = Column(String(32), unique=True, index=True, nullable=True)

    full_name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=True, index=True)

    department = Column(String(128), nullable=False, index=True)
    job_title = Column(String(255), nullable=False)
    # junior|mid|senior|lead|principal|manager - drives onboarding and expectations.
    seniority = Column(String(64), nullable=True)
    location = Column(String(128), nullable=True)
    employment_type = Column(String(64), nullable=True)  # full_time|contract|intern
    work_mode = Column(String(32), nullable=True)  # onsite|hybrid|remote

    manager_id = Column(Integer, ForeignKey("employees.id"), nullable=True, index=True)

    hire_date = Column(Date, nullable=False)
    exit_date = Column(Date, nullable=True)
    last_promotion_date = Column(Date, nullable=True)

    status = Column(String(32), default="active", nullable=False, index=True)

    # Compensation position within band (1.0 == at midpoint). Used as an
    # attrition signal; deliberately a ratio so no absolute salary is stored.
    compa_ratio = Column(Float, nullable=True)

    # Latest engagement survey result, 0-100, if the organisation runs one.
    engagement_score = Column(Float, nullable=True)

    source_candidate_id = Column(Integer, ForeignKey("candidates.id"), nullable=True)

    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    manager = relationship("Employee", remote_side=[id], backref="direct_reports")
    source_candidate = relationship("Candidate")

    skills = relationship(
        "EmployeeSkill", back_populates="employee", cascade="all, delete-orphan"
    )
    attendance = relationship(
        "AttendanceRecord", back_populates="employee", cascade="all, delete-orphan"
    )
    reviews = relationship(
        "PerformanceReview", back_populates="employee", cascade="all, delete-orphan"
    )
    goals = relationship("Goal", back_populates="employee", cascade="all, delete-orphan")
    feedback = relationship(
        "Feedback", back_populates="employee", cascade="all, delete-orphan"
    )
    onboarding_plans = relationship(
        "OnboardingPlan", back_populates="employee", cascade="all, delete-orphan"
    )

    @property
    def tenure_years(self) -> float:
        end = self.exit_date or date.today()
        if not self.hire_date:
            return 0.0
        return max(0.0, (end - self.hire_date).days / 365.25)


class EmployeeSkill(Base):
    """A skill an employee holds, with how strongly it is evidenced."""

    __tablename__ = "employee_skills"
    __table_args__ = (UniqueConstraint("employee_id", "skill", name="uq_employee_skill"),)

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False, index=True)

    skill = Column(String(128), nullable=False, index=True)  # canonical form
    proficiency = Column(Integer, default=3, nullable=False)  # 1-5

    # resume|interview|review|self_reported|manager - lets the skill graph weight
    # verified skills above self-reported ones.
    source = Column(String(32), default="self_reported", nullable=False)
    verified = Column(Boolean, default=False, nullable=False)

    last_used_on = Column(Date, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    employee = relationship("Employee", back_populates="skills")


class AttendanceRecord(Base):
    """One day of attendance for one employee."""

    __tablename__ = "attendance_records"
    __table_args__ = (UniqueConstraint("employee_id", "work_date", name="uq_attendance_day"),)

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False, index=True)

    work_date = Column(Date, nullable=False, index=True)
    status = Column(String(32), default="present", nullable=False)

    hours_worked = Column(Float, nullable=True)
    overtime_hours = Column(Float, default=0.0, nullable=False)
    late_arrival = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    employee = relationship("Employee", back_populates="attendance")


class SkillRequirement(Base):
    """
    Organisational demand for a skill.

    The demand side of the workforce skill graph: what the organisation needs now
    (`horizon='current'`) versus what it will need (`horizon='future'`), so gaps
    can be identified before they become vacancies.
    """

    __tablename__ = "skill_requirements"

    id = Column(Integer, primary_key=True, index=True)

    skill = Column(String(128), nullable=False, index=True)
    department = Column(String(128), nullable=True, index=True)
    role = Column(String(255), nullable=True)

    importance = Column(String(32), default="important", nullable=False)
    horizon = Column(String(32), default="current", nullable=False, index=True)

    required_headcount = Column(Integer, default=1, nullable=False)
    required_proficiency = Column(Integer, default=3, nullable=False)

    target_date = Column(Date, nullable=True)
    rationale = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
