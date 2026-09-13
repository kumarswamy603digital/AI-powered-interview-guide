"""
SQLAlchemy models for the application.

Every model is imported here so that `init_db()` registers all tables with
Base.metadata. Previously this module was empty and tables were only created as a
side effect of a route importing them, which meant a new model could silently
never get a table.
"""

from app.models.hr import Candidate, JobRequisition
from app.models.interview import InterviewSession, InterviewTurn
from app.models.resume import Resume
from app.models.user import User


__all__ = [
    "Candidate",
    "InterviewSession",
    "InterviewTurn",
    "JobRequisition",
    "Resume",
    "User",
]
