from __future__ import annotations

from dataclasses import asdict
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.performance_intel import score_sentiment
from app.api.deps import require_hr_user
from app.core.workforce_intelligence import (
    analyze_employee_performance,
    analyze_workforce_performance,
)
from app.crud.workforce import (
    create_feedback,
    create_goal,
    create_review,
    department_average_rating,
    get_employee,
    get_goal,
    list_feedback,
    list_goals,
    list_reviews,
    update_goal,
)
from app.db.session import get_db
from app.models.user import User
from app.schemas.workforce import (
    FeedbackCreate,
    FeedbackRead,
    GoalCreate,
    GoalRead,
    GoalUpdate,
    PerformanceInsightRead,
    ReviewCreate,
    ReviewRead,
)


router = APIRouter(prefix="/api/performance", tags=["performance"])

DbSessionDep = Annotated[Session, Depends(get_db)]
HrUserDep = Annotated[User, Depends(require_hr_user)]


def _require_employee(db: Session, employee_id: int):
    employee = get_employee(db, employee_id)
    if employee is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    return employee


# --------------------------------------------------------------------------
# Reviews
# --------------------------------------------------------------------------
@router.post("/reviews", response_model=ReviewRead, status_code=status.HTTP_201_CREATED)
def add_review(payload: ReviewCreate, db: DbSessionDep, hr_user: HrUserDep) -> ReviewRead:
    _require_employee(db, payload.employee_id)
    if payload.reviewer_id is not None:
        _require_employee(db, payload.reviewer_id)
    review = create_review(db, **payload.model_dump())
    return ReviewRead.model_validate(review)


@router.get("/reviews/{employee_id}", response_model=List[ReviewRead])
def read_reviews(employee_id: int, db: DbSessionDep, hr_user: HrUserDep) -> List[ReviewRead]:
    _require_employee(db, employee_id)
    return [ReviewRead.model_validate(r) for r in list_reviews(db, employee_id)]


# --------------------------------------------------------------------------
# Goals
# --------------------------------------------------------------------------
@router.post("/goals", response_model=GoalRead, status_code=status.HTTP_201_CREATED)
def add_goal(payload: GoalCreate, db: DbSessionDep, hr_user: HrUserDep) -> GoalRead:
    _require_employee(db, payload.employee_id)
    goal = create_goal(db, **payload.model_dump())
    return GoalRead.model_validate(goal)


@router.get("/goals/{employee_id}", response_model=List[GoalRead])
def read_goals(
    employee_id: int,
    db: DbSessionDep,
    hr_user: HrUserDep,
    period: Optional[str] = Query(default=None),
) -> List[GoalRead]:
    _require_employee(db, employee_id)
    return [GoalRead.model_validate(g) for g in list_goals(db, employee_id, period=period)]


@router.patch("/goals/{goal_id}", response_model=GoalRead)
def patch_goal(
    goal_id: int,
    payload: GoalUpdate,
    db: DbSessionDep,
    hr_user: HrUserDep,
) -> GoalRead:
    goal = get_goal(db, goal_id)
    if goal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Goal not found")
    goal = update_goal(db, goal, **payload.model_dump(exclude_unset=True))
    return GoalRead.model_validate(goal)


# --------------------------------------------------------------------------
# Feedback
# --------------------------------------------------------------------------
@router.post("/feedback", response_model=FeedbackRead, status_code=status.HTTP_201_CREATED)
def add_feedback(payload: FeedbackCreate, db: DbSessionDep, hr_user: HrUserDep) -> FeedbackRead:
    _require_employee(db, payload.employee_id)
    if payload.author_id is not None:
        _require_employee(db, payload.author_id)
    item = create_feedback(db, **payload.model_dump())
    result = FeedbackRead.model_validate(item)
    if item.sentiment is None:
        # Surface what the lexicon read, so a reviewer can sanity-check it.
        result.inferred_sentiment = score_sentiment(item.content or "")
    return result


@router.get("/feedback/{employee_id}", response_model=List[FeedbackRead])
def read_feedback(employee_id: int, db: DbSessionDep, hr_user: HrUserDep) -> List[FeedbackRead]:
    _require_employee(db, employee_id)
    items: List[FeedbackRead] = []
    for item in list_feedback(db, employee_id):
        payload = FeedbackRead.model_validate(item)
        if item.sentiment is None:
            payload.inferred_sentiment = score_sentiment(item.content or "")
        items.append(payload)
    return items


# --------------------------------------------------------------------------
# Intelligence
# --------------------------------------------------------------------------
@router.get("/insights/{employee_id}", response_model=PerformanceInsightRead)
def read_insight(
    employee_id: int, db: DbSessionDep, hr_user: HrUserDep
) -> PerformanceInsightRead:
    """
    Strengths, improvement areas, trajectory and calibration for one employee,
    derived from goals, feedback themes and review history.
    """
    employee = _require_employee(db, employee_id)
    insight = analyze_employee_performance(db, employee)
    return PerformanceInsightRead.model_validate(asdict(insight))


@router.get("/insights", response_model=List[PerformanceInsightRead])
def read_all_insights(
    db: DbSessionDep,
    hr_user: HrUserDep,
    department: Optional[str] = Query(default=None),
    trajectory: Optional[str] = Query(default=None, description="improving|steady|declining"),
    promotion_readiness: Optional[str] = Query(default=None, description="ready|developing|not_yet"),
    limit: int = Query(default=200, ge=1, le=1000),
) -> List[PerformanceInsightRead]:
    insights = analyze_workforce_performance(db, department=department, limit=limit)
    if trajectory:
        insights = [i for i in insights if i.rating_trajectory == trajectory]
    if promotion_readiness:
        insights = [i for i in insights if i.promotion_readiness == promotion_readiness]
    return [PerformanceInsightRead.model_validate(asdict(i)) for i in insights]


@router.get("/calibration", response_model=dict)
def read_calibration(
    db: DbSessionDep,
    hr_user: HrUserDep,
    department: Optional[str] = Query(default=None),
) -> dict:
    """Department rating averages, used to calibrate individual ratings."""
    from app.crud.workforce import list_departments

    departments = [department] if department else list_departments(db)
    return {
        "departments": [
            {"department": name, "average_rating": department_average_rating(db, name)}
            for name in departments
        ]
    }
