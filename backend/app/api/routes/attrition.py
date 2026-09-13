from __future__ import annotations

from dataclasses import asdict
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import require_hr_user
from app.core.attrition import FEATURE_LABELS, FEATURE_WEIGHTS, attrition_overview
from app.core.workforce_intelligence import (
    assess_employee_attrition,
    assess_workforce_attrition,
)
from app.crud.workforce import get_employee
from app.db.session import get_db
from app.models.user import User
from app.schemas.workforce import AttritionAssessmentRead, AttritionOverviewRead


router = APIRouter(prefix="/api/attrition", tags=["attrition"])

DbSessionDep = Annotated[Session, Depends(get_db)]
HrUserDep = Annotated[User, Depends(require_hr_user)]


@router.get("/model", response_model=dict)
def describe_model(hr_user: HrUserDep) -> dict:
    """
    Expose the model's signals and weights.

    A retention recommendation that cannot be explained will not be acted on, so
    the weighting is part of the API rather than hidden in the implementation.
    """
    return {
        "approach": "deterministic weighted signals, renormalised over available data",
        "signals": [
            {"name": name, "label": FEATURE_LABELS[name], "weight": weight}
            for name, weight in sorted(FEATURE_WEIGHTS.items(), key=lambda kv: -kv[1])
        ],
        "bands": {"low": "<35", "moderate": "35-55", "high": "55-72", "critical": ">=72"},
        "notes": [
            "Approved leave never counts towards absence risk.",
            "Weights are renormalised when a signal has no data, so missing data lowers "
            "confidence instead of inventing risk.",
            "Every factor maps to a retention action with an estimated risk reduction.",
        ],
    }


@router.get("/employees/{employee_id}", response_model=AttritionAssessmentRead)
def assess_one(
    employee_id: int,
    db: DbSessionDep,
    hr_user: HrUserDep,
) -> AttritionAssessmentRead:
    employee = get_employee(db, employee_id)
    if employee is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    return AttritionAssessmentRead.model_validate(asdict(assess_employee_attrition(db, employee)))


@router.get("", response_model=AttritionOverviewRead)
def assess_workforce(
    db: DbSessionDep,
    hr_user: HrUserDep,
    department: Optional[str] = Query(default=None),
    band: Optional[str] = Query(default=None, description="Filter to low|moderate|high|critical"),
    limit: int = Query(default=200, ge=1, le=1000),
) -> AttritionOverviewRead:
    """Risk for the whole workforce, highest first, with org-level drivers."""
    assessments = assess_workforce_attrition(db, department=department, limit=limit)
    overview = attrition_overview(assessments)

    if band:
        assessments = [a for a in assessments if a.risk_band == band]

    return AttritionOverviewRead(
        employees_assessed=int(overview["employees_assessed"]),  # type: ignore[arg-type]
        average_risk=float(overview["average_risk"]),  # type: ignore[arg-type]
        band_distribution=overview["band_distribution"],  # type: ignore[arg-type]
        high_risk_count=int(overview["high_risk_count"]),  # type: ignore[arg-type]
        by_department=overview["by_department"],  # type: ignore[arg-type]
        top_drivers=overview["top_drivers"],  # type: ignore[arg-type]
        assessments=[AttritionAssessmentRead.model_validate(asdict(a)) for a in assessments],
    )
