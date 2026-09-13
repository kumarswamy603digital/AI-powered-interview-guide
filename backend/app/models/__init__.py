"""
SQLAlchemy models for the application.

Every model is imported here so that `init_db()` registers all tables with
Base.metadata. Previously this module was empty and tables were only created as a
side effect of a route importing them, which meant a new model could silently
never get a table.
"""

from app.models.hr import Candidate, JobRequisition
from app.models.interview import InterviewSession, InterviewTurn
from app.models.onboarding import OnboardingPlan, OnboardingTask
from app.models.performance import Feedback, Goal, PerformanceReview
from app.models.policy import PolicyChunk, PolicyDocument
from app.models.resume import Resume
from app.models.user import User
from app.models.workforce import (
    AttendanceRecord,
    Employee,
    EmployeeSkill,
    SkillRequirement,
)


__all__ = [
    "AttendanceRecord",
    "Candidate",
    "Employee",
    "EmployeeSkill",
    "Feedback",
    "Goal",
    "InterviewSession",
    "InterviewTurn",
    "JobRequisition",
    "OnboardingPlan",
    "OnboardingTask",
    "PerformanceReview",
    "PolicyChunk",
    "PolicyDocument",
    "Resume",
    "SkillRequirement",
    "User",
]
