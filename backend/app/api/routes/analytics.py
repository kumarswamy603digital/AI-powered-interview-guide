from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.analytics import (
    build_interview_history,
    build_performance_trends,
    build_skill_progress,
)
from app.crud.interview import list_sessions_for_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.analytics import (
    InterviewHistoryResponse,
    PerformanceTrendsResponse,
    SkillProgressResponse,
)


router = APIRouter(prefix="/api/analytics", tags=["analytics"])

DbSessionDep = Annotated[Session, Depends(get_db)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]


@router.get("/interviews/history", response_model=InterviewHistoryResponse)
def get_interview_history(
    db: DbSessionDep,
    current_user: CurrentUserDep,
) -> InterviewHistoryResponse:
    sessions = list_sessions_for_user(db, user_id=current_user.id)
    items = build_interview_history(sessions, db=db)
    return InterviewHistoryResponse(items=items)


@router.get("/skills/progress", response_model=SkillProgressResponse)
def get_skill_progress(
    db: DbSessionDep,
    current_user: CurrentUserDep,
) -> SkillProgressResponse:
    sessions = list_sessions_for_user(db, user_id=current_user.id)
    items = build_skill_progress(sessions, db=db)
    return SkillProgressResponse(items=items)


@router.get("/performance/trends", response_model=PerformanceTrendsResponse)
def get_performance_trends(
    db: DbSessionDep,
    current_user: CurrentUserDep,
) -> PerformanceTrendsResponse:
    sessions = list_sessions_for_user(db, user_id=current_user.id)
    points = build_performance_trends(sessions, db=db)
    return PerformanceTrendsResponse(points=points)

