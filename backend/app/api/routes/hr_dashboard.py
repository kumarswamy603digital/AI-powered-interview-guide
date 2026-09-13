from __future__ import annotations

from typing import Annotated, Dict, List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from dataclasses import asdict

from app.api.deps import require_hr_user
from app.core.decision_dashboard import build_decision_dashboard
from app.core.hr_intelligence import rank_candidates_for_job
from app.core.ranking import CandidateRanking, aggregate_skill_gaps
from app.crud.hr import list_candidates, list_jobs
from app.db.session import get_db
from app.models.user import User
from app.schemas.hr import HrDashboardRead, PipelineCounts, SkillGapRead
from app.schemas.workforce import DecisionDashboardRead


router = APIRouter(prefix="/api/hr", tags=["hr-dashboard"])

DbSessionDep = Annotated[Session, Depends(get_db)]
HrUserDep = Annotated[User, Depends(require_hr_user)]


RECOMMENDATION_LABELS = {
    "recommend_hire": "recommended for hire",
    "advance_to_interview": "ready to advance to interview",
    "further_assessment": "need further assessment",
    "reject": "not a fit for their current role",
}


def _build_insights(
    *,
    rankings: List[CandidateRanking],
    skill_gaps: List[tuple[str, int]],
    open_job_count: int,
    missing_resume_text: int,
) -> List[str]:
    """
    Turn aggregate numbers into recommended actions.

    Ordered by how actionable they are: blockers first, then opportunities, then
    data-quality problems.
    """
    insights: List[str] = []

    if open_job_count == 0:
        insights.append("No open requisitions. Create one to start ranking candidates.")
        return insights

    if not rankings:
        insights.append(
            "No candidates attached to open requisitions yet. Add candidates and upload "
            "their resumes to generate rankings."
        )

    conflicts = [r for r in rankings if "resume_interview_mismatch" in r.flags]
    if conflicts:
        names = ", ".join(r.full_name for r in conflicts[:3])
        insights.append(
            f"{len(conflicts)} candidate(s) scored well on paper but poorly in interview "
            f"({names}) — verify claimed skills before advancing."
        )

    hires = [r for r in rankings if r.recommendation == "recommend_hire"]
    if hires:
        best = max(hires, key=lambda r: r.final_score)
        insights.append(
            f"{len(hires)} candidate(s) recommended for hire — strongest is {best.full_name} "
            f"at {best.final_score:.0f}% role match."
        )

    advance = [r for r in rankings if r.recommendation == "advance_to_interview"]
    if advance:
        insights.append(
            f"{len(advance)} candidate(s) clear the resume bar but have no interview yet — "
            "schedule interviews to complete their assessment."
        )

    if skill_gaps:
        skill, count = skill_gaps[0]
        insights.append(
            f"{count} candidate(s) lack {skill}, the most common gap across open "
            "requisitions — consider training, or relax the requirement."
        )

    undersold = [r for r in rankings if "outperformed_resume" in r.flags]
    if undersold:
        insights.append(
            f"{len(undersold)} candidate(s) interviewed far better than their resume "
            "suggested — their resumes are understating them."
        )

    if missing_resume_text:
        insights.append(
            f"{missing_resume_text} candidate(s) have no parseable resume text, so their "
            "skill match is unreliable. Re-upload a text-based PDF or DOCX."
        )

    return insights


@router.get("/dashboard", response_model=HrDashboardRead)
def hr_dashboard(
    db: DbSessionDep,
    hr_user: HrUserDep,
    gap_limit: int = Query(default=8, ge=1, le=50),
) -> HrDashboardRead:
    """
    Combined recruitment view: pipeline, skill gaps and recommended actions
    aggregated across every open requisition.
    """
    open_jobs = list_jobs(db, status="open", limit=500)
    all_candidates = list_candidates(db, limit=500)

    # Pipeline counts cover every candidate, not just those on open jobs, so the
    # totals reconcile with the candidate list.
    pipeline = PipelineCounts()
    for candidate in all_candidates:
        if hasattr(pipeline, candidate.stage):
            setattr(pipeline, candidate.stage, getattr(pipeline, candidate.stage) + 1)

    rankings: List[CandidateRanking] = []
    for job in open_jobs:
        job_candidates = list_candidates(db, job_requisition_id=job.id, limit=500)
        job_rankings, _ = rank_candidates_for_job(db, job, job_candidates)
        rankings.extend(job_rankings)

    recommendation_counts: Dict[str, int] = {key: 0 for key in RECOMMENDATION_LABELS}
    for ranking in rankings:
        recommendation_counts[ranking.recommendation] = (
            recommendation_counts.get(ranking.recommendation, 0) + 1
        )

    interviews_completed = sum(1 for r in rankings if r.interview_score is not None)
    awaiting_interview = sum(
        1
        for r in rankings
        if r.interview_score is None and r.stage not in {"rejected", "hired"}
    )
    missing_resume_text = sum(1 for r in rankings if "no_resume_text" in r.flags)

    skill_gaps = aggregate_skill_gaps(rankings)

    return HrDashboardRead(
        open_jobs=len(open_jobs),
        total_candidates=len(all_candidates),
        interviews_completed=interviews_completed,
        candidates_awaiting_interview=awaiting_interview,
        candidates_missing_resume_text=missing_resume_text,
        pipeline=pipeline,
        top_skill_gaps=[
            SkillGapRead(skill=skill, candidates_missing=count)
            for skill, count in skill_gaps[:gap_limit]
        ],
        recommendation_counts=recommendation_counts,
        insights=_build_insights(
            rankings=rankings,
            skill_gaps=skill_gaps,
            open_job_count=len(open_jobs),
            missing_resume_text=missing_resume_text,
        ),
    )



@router.get("/decision-dashboard", response_model=DecisionDashboardRead)
def decision_dashboard(db: DbSessionDep, hr_user: HrUserDep) -> DecisionDashboardRead:
    """
    The combined HR decision view: recruitment, attendance, performance,
    attrition and skill data in one response, plus insights derived by
    correlating those sources against each other.

    Each insight lists the sources it came from, so a reviewer can audit it.
    """
    dashboard = build_decision_dashboard(db)
    return DecisionDashboardRead.model_validate(asdict(dashboard))
