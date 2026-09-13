from __future__ import annotations

from dataclasses import asdict
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import require_hr_user
from app.core.hr_intelligence import (
    build_candidate_evidence,
    job_requirements_from_model,
    rank_candidates_for_job,
)
from app.core.ranking import CandidateRanking, aggregate_skill_gaps, rank_candidate
from app.crud.hr import (
    create_candidate,
    get_candidate,
    get_job,
    latest_resume_for_candidate,
    list_candidates,
    list_candidates_by_ids,
    list_scored_sessions_for_candidate,
    list_sessions_for_candidate,
    update_candidate,
)
from app.db.session import get_db
from app.models.hr import Candidate
from app.models.user import User
from app.schemas.hr import (
    CandidateCreate,
    CandidateProfileRead,
    CandidateRankingRead,
    CandidateRead,
    CandidateStage,
    CandidateUpdate,
    InterviewSummaryRead,
    RankRequest,
    RankResponse,
    SkillGapRead,
)


router = APIRouter(prefix="/api/candidates", tags=["candidates"])

DbSessionDep = Annotated[Session, Depends(get_db)]
HrUserDep = Annotated[User, Depends(require_hr_user)]


def _ranking_to_read(ranking: CandidateRanking) -> CandidateRankingRead:
    return CandidateRankingRead.model_validate(asdict(ranking))


def _candidate_to_read(db: Session, candidate: Candidate) -> CandidateRead:
    payload = CandidateRead.model_validate(candidate)
    resume = latest_resume_for_candidate(db, candidate.id)
    payload.has_resume_text = bool(resume and (resume.extracted_text or "").strip())
    payload.extracted_skills = list((resume.extracted_skills or []) if resume else [])

    scored = list_scored_sessions_for_candidate(db, candidate.id)
    payload.interviews_completed = len(scored)
    payload.latest_interview_score = scored[0].overall_score if scored else None
    return payload


@router.post("", response_model=CandidateRead, status_code=status.HTTP_201_CREATED)
def add_candidate(
    payload: CandidateCreate,
    db: DbSessionDep,
    hr_user: HrUserDep,
) -> CandidateRead:
    if payload.job_requisition_id is not None and get_job(db, payload.job_requisition_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job requisition {payload.job_requisition_id} not found.",
        )

    candidate = create_candidate(
        db,
        created_by_user_id=hr_user.id,
        full_name=payload.full_name,
        email=str(payload.email) if payload.email else None,
        phone=payload.phone,
        current_title=payload.current_title,
        years_experience=payload.years_experience,
        source=payload.source,
        job_requisition_id=payload.job_requisition_id,
        notes=payload.notes,
    )
    return _candidate_to_read(db, candidate)


@router.get("", response_model=List[CandidateRead])
def list_all_candidates(
    db: DbSessionDep,
    hr_user: HrUserDep,
    job_requisition_id: Optional[int] = Query(default=None),
    stage: Optional[CandidateStage] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
) -> List[CandidateRead]:
    candidates = list_candidates(
        db,
        job_requisition_id=job_requisition_id,
        stage=stage,
        limit=limit,
    )
    return [_candidate_to_read(db, c) for c in candidates]


@router.post("/rank", response_model=RankResponse)
def rank_for_job(
    payload: RankRequest,
    db: DbSessionDep,
    hr_user: HrUserDep,
) -> RankResponse:
    """
    Rank candidates against a job requisition.

    This is the multi-source reasoning endpoint: it joins parsed resume skills,
    the requisition's stated requirements, and persisted interview scores into one
    ranked list, each row carrying the reasoning behind its recommendation.
    """
    job = get_job(db, payload.job_requisition_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job requisition not found")

    if payload.candidate_ids:
        candidates = list_candidates_by_ids(db, payload.candidate_ids)
        found_ids = {c.id for c in candidates}
        missing_ids = [cid for cid in payload.candidate_ids if cid not in found_ids]
        if missing_ids:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Candidates not found: {missing_ids}",
            )
    else:
        candidates = list_candidates(db, job_requisition_id=job.id)
        if payload.include_unassigned:
            candidates = candidates + list_candidates(db, unassigned_only=True)

    rankings, warnings = rank_candidates_for_job(db, job, candidates)
    limited = rankings[: payload.limit]

    return RankResponse(
        job_requisition_id=job.id,
        job_title=job.title,
        required_skills=list(job.required_skills or []),
        candidates_evaluated=len(rankings),
        rankings=[_ranking_to_read(r) for r in limited],
        skill_gaps=[
            SkillGapRead(skill=skill, candidates_missing=count)
            for skill, count in aggregate_skill_gaps(rankings)
        ],
        warnings=warnings,
    )


@router.get("/{candidate_id}", response_model=CandidateRead)
def read_candidate(
    candidate_id: int,
    db: DbSessionDep,
    hr_user: HrUserDep,
) -> CandidateRead:
    candidate = get_candidate(db, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")
    return _candidate_to_read(db, candidate)


@router.patch("/{candidate_id}", response_model=CandidateRead)
def patch_candidate(
    candidate_id: int,
    payload: CandidateUpdate,
    db: DbSessionDep,
    hr_user: HrUserDep,
) -> CandidateRead:
    candidate = get_candidate(db, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")

    fields = payload.model_dump(exclude_unset=True)
    if fields.get("job_requisition_id") is not None and get_job(db, fields["job_requisition_id"]) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job requisition {fields['job_requisition_id']} not found.",
        )
    if "email" in fields and fields["email"] is not None:
        fields["email"] = str(fields["email"])

    candidate = update_candidate(db, candidate, **fields)
    return _candidate_to_read(db, candidate)


@router.get("/{candidate_id}/profile", response_model=CandidateProfileRead)
def read_candidate_profile(
    candidate_id: int,
    db: DbSessionDep,
    hr_user: HrUserDep,
) -> CandidateProfileRead:
    """
    Candidate intelligence profile: resume, job match, interviews and the
    resulting recommendation in one response.
    """
    candidate = get_candidate(db, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")

    resume = latest_resume_for_candidate(db, candidate.id)

    interviews: List[InterviewSummaryRead] = []
    for session in list_sessions_for_candidate(db, candidate.id):
        skill_scores = {}
        for entry in session.skill_scores or []:
            if isinstance(entry, dict) and entry.get("name") is not None:
                try:
                    skill_scores[str(entry["name"])] = float(entry.get("score") or 0.0)
                except (TypeError, ValueError):
                    continue
        interviews.append(
            InterviewSummaryRead(
                id=session.id,
                target_role=session.target_role,
                status=session.status,
                overall_score=session.overall_score,
                skill_scores=skill_scores,
                summary=session.report_summary,
                started_at=session.started_at,
                ended_at=session.ended_at,
            )
        )

    ranking_read: Optional[CandidateRankingRead] = None
    if candidate.job_requisition_id is not None:
        job = get_job(db, candidate.job_requisition_id)
        if job is not None:
            evidence = build_candidate_evidence(db, candidate, job_requisition_id=job.id)
            ranking_read = _ranking_to_read(
                rank_candidate(evidence, job_requirements_from_model(job))
            )

    return CandidateProfileRead(
        candidate=_candidate_to_read(db, candidate),
        resume_skills=list((resume.extracted_skills or []) if resume else []),
        resume_extraction_status=resume.extraction_status if resume else None,
        resume_extraction_detail=resume.extraction_detail if resume else None,
        interviews=interviews,
        ranking=ranking_read,
    )
