from __future__ import annotations

"""
Service layer that assembles HR evidence from the database and hands it to the
(pure, DB-free) ranking engine in app.core.ranking.

Keeping the assembly here means the ranking rules stay unit-testable without a
database, while the 'which sources exist for this candidate' question lives in
one place instead of being duplicated across routes.
"""

from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.ranking import (
    CandidateEvidence,
    CandidateRanking,
    JobRequirements,
    rank_candidates,
)
from app.crud.hr import (
    latest_resume_for_candidate,
    list_scored_sessions_for_candidate,
)
from app.models.hr import Candidate, JobRequisition


def job_requirements_from_model(job: JobRequisition) -> JobRequirements:
    return JobRequirements(
        id=job.id,
        title=job.title,
        required_skills=list(job.required_skills or []),
        preferred_skills=list(job.preferred_skills or []),
        min_years_experience=job.min_years_experience,
    )


def _skill_scores_to_dict(skill_scores) -> Dict[str, float]:
    """Normalise the persisted skill_scores JSON into {name: score}."""
    result: Dict[str, float] = {}
    for entry in skill_scores or []:
        if isinstance(entry, dict):
            name = str(entry.get("name") or "").strip()
            raw_score = entry.get("score")
        else:  # pragma: no cover - defensive
            continue
        if not name or raw_score is None:
            continue
        try:
            result[name] = float(raw_score)
        except (TypeError, ValueError):
            continue
    return result


def build_candidate_evidence(
    db: Session,
    candidate: Candidate,
    *,
    job_requisition_id: Optional[int] = None,
) -> CandidateEvidence:
    """
    Gather every available signal for one candidate.

    Sources: the candidate record, their latest parsed resume, and their most
    recent scored interview (preferring one held for this requisition).
    """
    resume = latest_resume_for_candidate(db, candidate.id)
    resume_text = (resume.extracted_text or "") if resume else ""
    extracted_skills = list((resume.extracted_skills or []) if resume else [])

    sessions = list_scored_sessions_for_candidate(
        db, candidate.id, job_requisition_id=job_requisition_id
    )
    latest = sessions[0] if sessions else None

    return CandidateEvidence(
        id=candidate.id,
        full_name=candidate.full_name,
        stage=candidate.stage,
        resume_text=resume_text,
        extracted_skills=extracted_skills,
        years_experience=candidate.years_experience,
        interview_score=latest.overall_score if latest else None,
        interview_skill_scores=_skill_scores_to_dict(latest.skill_scores) if latest else {},
        interview_session_id=latest.id if latest else None,
        interviews_completed=len(sessions),
    )


def rank_candidates_for_job(
    db: Session,
    job: JobRequisition,
    candidates: List[Candidate],
) -> Tuple[List[CandidateRanking], List[str]]:
    """
    Rank candidates for a job and return (rankings, warnings).

    Warnings surface data-quality problems that would otherwise make the ranking
    quietly misleading — an empty requirement list, or resumes that never parsed.
    """
    requirements = job_requirements_from_model(job)
    evidence = [
        build_candidate_evidence(db, candidate, job_requisition_id=job.id)
        for candidate in candidates
    ]
    rankings = rank_candidates(evidence, requirements)

    warnings: List[str] = []
    if not requirements.required_skills:
        warnings.append(
            "This requisition lists no required skills, so skill fit could not be "
            "scored. Add required skills for a meaningful ranking."
        )
    unparsed = [r.full_name for r in rankings if "no_resume_text" in r.flags]
    if unparsed:
        preview = ", ".join(unparsed[:5])
        suffix = "" if len(unparsed) <= 5 else f" (+{len(unparsed) - 5} more)"
        warnings.append(
            f"No resume text available for: {preview}{suffix}. "
            "Upload a text-based PDF/DOCX so their skills can be matched."
        )
    if not candidates:
        warnings.append("No candidates are attached to this requisition yet.")

    return rankings, warnings
