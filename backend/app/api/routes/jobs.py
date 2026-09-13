from __future__ import annotations

from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import require_hr_user
from app.crud.hr import (
    count_candidates_for_job,
    create_job,
    get_job,
    list_candidates,
    list_jobs,
    update_job,
)
from app.db.session import get_db
from app.models.user import User
from app.schemas.hr import (
    JobRequisitionCreate,
    JobRequisitionRead,
    JobRequisitionUpdate,
    JobStatus,
)


router = APIRouter(prefix="/api/jobs", tags=["jobs"])

DbSessionDep = Annotated[Session, Depends(get_db)]
HrUserDep = Annotated[User, Depends(require_hr_user)]


def _to_read(db: Session, job) -> JobRequisitionRead:
    payload = JobRequisitionRead.model_validate(job)
    payload.candidate_count = count_candidates_for_job(db, job.id)
    return payload


@router.post("", response_model=JobRequisitionRead, status_code=status.HTTP_201_CREATED)
def create_requisition(
    payload: JobRequisitionCreate,
    db: DbSessionDep,
    hr_user: HrUserDep,
) -> JobRequisitionRead:
    job = create_job(
        db,
        created_by_user_id=hr_user.id,
        title=payload.title,
        department=payload.department,
        seniority=payload.seniority,
        location=payload.location,
        employment_type=payload.employment_type,
        description=payload.description,
        required_skills=payload.required_skills,
        preferred_skills=payload.preferred_skills,
        min_years_experience=payload.min_years_experience,
        headcount=payload.headcount,
    )
    return _to_read(db, job)


@router.get("", response_model=List[JobRequisitionRead])
def list_requisitions(
    db: DbSessionDep,
    hr_user: HrUserDep,
    status_filter: Optional[JobStatus] = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
) -> List[JobRequisitionRead]:
    jobs = list_jobs(db, status=status_filter, limit=limit)
    return [_to_read(db, job) for job in jobs]


@router.get("/{job_id}", response_model=JobRequisitionRead)
def read_requisition(
    job_id: int,
    db: DbSessionDep,
    hr_user: HrUserDep,
) -> JobRequisitionRead:
    job = get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job requisition not found")
    return _to_read(db, job)


@router.patch("/{job_id}", response_model=JobRequisitionRead)
def patch_requisition(
    job_id: int,
    payload: JobRequisitionUpdate,
    db: DbSessionDep,
    hr_user: HrUserDep,
) -> JobRequisitionRead:
    job = get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job requisition not found")

    job = update_job(db, job, **payload.model_dump(exclude_unset=True))
    return _to_read(db, job)


@router.get("/{job_id}/candidate-count", response_model=dict)
def candidate_count(
    job_id: int,
    db: DbSessionDep,
    hr_user: HrUserDep,
) -> dict:
    if get_job(db, job_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job requisition not found")
    candidates = list_candidates(db, job_requisition_id=job_id)
    stages: dict[str, int] = {}
    for candidate in candidates:
        stages[candidate.stage] = stages.get(candidate.stage, 0) + 1
    return {"job_requisition_id": job_id, "total": len(candidates), "by_stage": stages}
