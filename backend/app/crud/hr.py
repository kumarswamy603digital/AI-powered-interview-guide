from __future__ import annotations

from typing import Iterable, List, Optional

from sqlalchemy.orm import Session

from app.models.hr import Candidate, JobRequisition
from app.models.interview import InterviewSession
from app.models.resume import Resume


# --------------------------------------------------------------------------
# Job requisitions
# --------------------------------------------------------------------------
def create_job(
    db: Session,
    *,
    created_by_user_id: Optional[int],
    title: str,
    department: Optional[str] = None,
    seniority: Optional[str] = None,
    location: Optional[str] = None,
    employment_type: Optional[str] = None,
    description: Optional[str] = None,
    required_skills: Optional[List[str]] = None,
    preferred_skills: Optional[List[str]] = None,
    min_years_experience: Optional[float] = None,
    headcount: int = 1,
) -> JobRequisition:
    job = JobRequisition(
        created_by_user_id=created_by_user_id,
        title=title,
        department=department,
        seniority=seniority,
        location=location,
        employment_type=employment_type,
        description=description,
        required_skills=list(required_skills or []),
        preferred_skills=list(preferred_skills or []),
        min_years_experience=min_years_experience,
        headcount=headcount,
        status="open",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def get_job(db: Session, job_id: int) -> Optional[JobRequisition]:
    return db.query(JobRequisition).filter(JobRequisition.id == job_id).first()


def list_jobs(
    db: Session,
    *,
    status: Optional[str] = None,
    limit: int = 100,
) -> List[JobRequisition]:
    query = db.query(JobRequisition)
    if status:
        query = query.filter(JobRequisition.status == status)
    return query.order_by(JobRequisition.created_at.desc()).limit(limit).all()


def update_job(db: Session, job: JobRequisition, **fields) -> JobRequisition:
    for key, value in fields.items():
        if value is not None and hasattr(job, key):
            setattr(job, key, value)
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def count_candidates_for_job(db: Session, job_id: int) -> int:
    return db.query(Candidate).filter(Candidate.job_requisition_id == job_id).count()


# --------------------------------------------------------------------------
# Candidates
# --------------------------------------------------------------------------
def create_candidate(
    db: Session,
    *,
    created_by_user_id: Optional[int],
    full_name: str,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    current_title: Optional[str] = None,
    years_experience: Optional[float] = None,
    source: Optional[str] = None,
    job_requisition_id: Optional[int] = None,
    notes: Optional[str] = None,
) -> Candidate:
    candidate = Candidate(
        created_by_user_id=created_by_user_id,
        full_name=full_name,
        email=email,
        phone=phone,
        current_title=current_title,
        years_experience=years_experience,
        source=source,
        job_requisition_id=job_requisition_id,
        notes=notes,
        stage="applied",
    )
    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    return candidate


def get_candidate(db: Session, candidate_id: int) -> Optional[Candidate]:
    return db.query(Candidate).filter(Candidate.id == candidate_id).first()


def list_candidates(
    db: Session,
    *,
    job_requisition_id: Optional[int] = None,
    stage: Optional[str] = None,
    unassigned_only: bool = False,
    limit: int = 200,
) -> List[Candidate]:
    query = db.query(Candidate)
    if job_requisition_id is not None:
        query = query.filter(Candidate.job_requisition_id == job_requisition_id)
    if unassigned_only:
        query = query.filter(Candidate.job_requisition_id.is_(None))
    if stage:
        query = query.filter(Candidate.stage == stage)
    return query.order_by(Candidate.created_at.desc()).limit(limit).all()


def list_candidates_by_ids(db: Session, candidate_ids: Iterable[int]) -> List[Candidate]:
    ids = list(candidate_ids)
    if not ids:
        return []
    return db.query(Candidate).filter(Candidate.id.in_(ids)).all()


def update_candidate(db: Session, candidate: Candidate, **fields) -> Candidate:
    for key, value in fields.items():
        if value is not None and hasattr(candidate, key):
            setattr(candidate, key, value)
    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    return candidate


def set_candidate_stage(db: Session, candidate: Candidate, stage: str) -> Candidate:
    candidate.stage = stage
    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    return candidate


# --------------------------------------------------------------------------
# Cross-entity reads used when assembling candidate evidence
# --------------------------------------------------------------------------
def latest_resume_for_candidate(db: Session, candidate_id: int) -> Optional[Resume]:
    return (
        db.query(Resume)
        .filter(Resume.candidate_id == candidate_id)
        .order_by(Resume.created_at.desc())
        .first()
    )


def list_scored_sessions_for_candidate(
    db: Session,
    candidate_id: int,
    *,
    job_requisition_id: Optional[int] = None,
) -> List[InterviewSession]:
    """
    Scored interviews for a candidate, most recent first.

    When a job is given, interviews for that job come first so ranking prefers
    role-specific evidence over an interview for a different position.
    """
    query = db.query(InterviewSession).filter(
        InterviewSession.candidate_id == candidate_id,
        InterviewSession.overall_score.isnot(None),
    )
    sessions = query.order_by(InterviewSession.scored_at.desc()).all()
    if job_requisition_id is None:
        return sessions
    return sorted(
        sessions,
        key=lambda s: (s.job_requisition_id == job_requisition_id,),
        reverse=True,
    )


def list_sessions_for_candidate(db: Session, candidate_id: int) -> List[InterviewSession]:
    return (
        db.query(InterviewSession)
        .filter(InterviewSession.candidate_id == candidate_id)
        .order_by(InterviewSession.started_at.desc())
        .all()
    )
