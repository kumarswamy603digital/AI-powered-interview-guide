from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.ats import score_resume
from app.core.skills import match_skills
from app.crud.hr import get_candidate, get_job, latest_resume_for_candidate
from app.crud.resume import get_resume
from app.db.session import get_db
from app.models.user import User
from app.schemas.ats import AtsScoreRequest, AtsScoreResponse


router = APIRouter(prefix="/api/ats", tags=["ats"])

DbSessionDep = Annotated[Session, Depends(get_db)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]


@router.post("/score", response_model=AtsScoreResponse)
def score_ats(
    payload: AtsScoreRequest,
    db: DbSessionDep,
    current_user: CurrentUserDep,
) -> AtsScoreResponse:
    """
    Compute ATS scores for a resume against a job role.

    Accepts pasted text, a stored resume id, or a candidate id (using their latest
    parsed resume). When a requisition is given, the matched/missing required
    skills are returned alongside the scores.

    Uses Gemini when GEMINI_API_KEY is configured; otherwise falls back to a
    deterministic heuristic-based scorer.
    """
    resume_text = payload.resume_text or ""
    resume_id = payload.resume_id
    candidate_id = payload.candidate_id
    extracted_skills: list[str] = []

    if not resume_text and resume_id is not None:
        resume = get_resume(db, resume_id)
        if resume is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found")
        if resume.user_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")
        resume_text = resume.extracted_text or ""
        candidate_id = candidate_id or resume.candidate_id
        extracted_skills = list(resume.extracted_skills or [])

    if not resume_text and candidate_id is not None:
        if get_candidate(db, candidate_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")
        resume = latest_resume_for_candidate(db, candidate_id)
        if resume is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No resume uploaded for this candidate",
            )
        resume_text = resume.extracted_text or ""
        resume_id = resume_id or resume.id
        extracted_skills = list(resume.extracted_skills or [])

    if not resume_text.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "No resume text available. The upload may be a scanned PDF, or the "
                "parser dependencies may not be installed."
            ),
        )

    job_role = payload.job_role
    matched: list[str] = []
    missing: list[str] = []
    if payload.job_requisition_id is not None:
        job = get_job(db, payload.job_requisition_id)
        if job is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Job requisition not found"
            )
        job_role = job.title
        matched, missing = match_skills(
            job.required_skills or [],
            resume_text=resume_text,
            known_skills=extracted_skills,
        )

    result = score_resume(resume_text=resume_text, job_role=job_role)
    return AtsScoreResponse(
        keyword_match_score=result.keyword_match_score,
        formatting_score=result.formatting_score,
        final_score=result.final_score,
        matched_skills=matched,
        missing_skills=missing,
        resume_id=resume_id,
        candidate_id=candidate_id,
    )
