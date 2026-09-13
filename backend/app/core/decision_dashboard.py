from __future__ import annotations

"""
HR decision dashboard.

Combines recruitment, attendance, performance, attrition and skill-graph data
into one view, and - the part that matters - derives insights that no single
source can produce on its own.

Examples of cross-source reasoning implemented here:
  * an employee at high flight risk who is the only holder of a core skill
  * a critical skill gap that has no open requisition against it
  * a promotion-ready high performer with a stagnant career and low pay
  * a candidate in the pipeline whose skills would close a known gap
Each insight names its sources so a reviewer can audit where it came from.
"""

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Literal, Sequence

from sqlalchemy.orm import Session

from app.core.attrition import AttritionAssessment, attrition_overview
from app.core.hr_intelligence import rank_candidates_for_job
from app.core.onboarding_agent import journey_progress
from app.core.performance_intel import PerformanceInsight
from app.core.ranking import CandidateRanking
from app.core.skill_graph import SkillGraph
from app.core.skills import canonical_skill
from app.core.workforce_intelligence import (
    analyze_workforce_performance,
    assess_workforce_attrition,
    attendance_metrics,
    build_workforce_skill_graph,
)
from app.crud.hr import list_candidates, list_jobs
from app.crud.workforce import list_employees, list_onboarding_plans


Severity = Literal["critical", "warning", "opportunity", "info"]


@dataclass
class CrossSourceInsight:
    title: str
    severity: Severity
    detail: str
    recommended_action: str
    sources: List[str]
    entities: List[str] = field(default_factory=list)


@dataclass
class DecisionDashboard:
    headline: Dict[str, object]
    recruitment: Dict[str, object]
    workforce_risk: Dict[str, object]
    performance: Dict[str, object]
    attendance: Dict[str, object]
    skills: Dict[str, object]
    onboarding: Dict[str, object]
    insights: List[CrossSourceInsight]
    data_sources: List[str]


def _round(value: float) -> float:
    return round(float(value), 2)


# --------------------------------------------------------------------------
# Section builders
# --------------------------------------------------------------------------
def _recruitment_section(db: Session) -> tuple[Dict[str, object], List[CandidateRanking], Dict[int, str]]:
    jobs = list_jobs(db, status="open", limit=200)
    all_candidates = list_candidates(db, limit=500)

    rankings: List[CandidateRanking] = []
    job_titles: Dict[int, str] = {}
    required_by_job: Dict[int, List[str]] = {}

    for job in jobs:
        job_titles[job.id] = job.title
        required_by_job[job.id] = [canonical_skill(s) for s in (job.required_skills or [])]
        job_candidates = list_candidates(db, job_requisition_id=job.id, limit=500)
        job_rankings, _warnings = rank_candidates_for_job(db, job, job_candidates)
        rankings.extend(job_rankings)

    stage_counts: Dict[str, int] = {}
    for candidate in all_candidates:
        stage_counts[candidate.stage] = stage_counts.get(candidate.stage, 0) + 1

    recommendation_counts: Dict[str, int] = {}
    for ranking in rankings:
        recommendation_counts[ranking.recommendation] = (
            recommendation_counts.get(ranking.recommendation, 0) + 1
        )

    section: Dict[str, object] = {
        "open_requisitions": len(jobs),
        "total_candidates": len(all_candidates),
        "candidates_ranked": len(rankings),
        "pipeline_by_stage": stage_counts,
        "recommendation_counts": recommendation_counts,
        "interviews_scored": sum(1 for r in rankings if r.interview_score is not None),
        "conflicts": [
            {"candidate": r.full_name, "skill_match": r.skill_match_score, "interview": r.interview_score}
            for r in rankings
            if "resume_interview_mismatch" in r.flags
        ],
        "top_candidates": [
            {
                "name": r.full_name,
                "score": r.final_score,
                "recommendation": r.recommendation,
                "missing_skills": r.missing_skills,
            }
            for r in sorted(rankings, key=lambda r: r.final_score, reverse=True)[:5]
        ],
        "required_skills_by_job": {str(k): v for k, v in required_by_job.items()},
    }
    return section, rankings, job_titles


def _workforce_risk_section(assessments: Sequence[AttritionAssessment]) -> Dict[str, object]:
    overview = attrition_overview(assessments)
    overview["watchlist"] = [
        {
            "employee_id": a.employee_id,
            "name": a.full_name,
            "department": a.department,
            "risk_score": a.risk_score,
            "band": a.risk_band,
            "top_driver": a.factors[0].label if a.factors else None,
            "summary": a.summary,
            "actions": [asdict(action) for action in a.recommended_actions[:2]],
        }
        for a in assessments
        if a.risk_band in {"high", "critical"}
    ][:10]
    return overview


def _performance_section(insights: Sequence[PerformanceInsight]) -> Dict[str, object]:
    rated = [i for i in insights if i.latest_rating is not None]
    distribution = {"outstanding": 0, "strong": 0, "solid": 0, "needs_support": 0}
    for insight in rated:
        rating = float(insight.latest_rating or 0)
        if rating >= 4.5:
            distribution["outstanding"] += 1
        elif rating >= 3.8:
            distribution["strong"] += 1
        elif rating >= 3.0:
            distribution["solid"] += 1
        else:
            distribution["needs_support"] += 1

    declining = [i for i in insights if i.rating_trajectory == "declining"]
    promotion_ready = [i for i in insights if i.promotion_readiness == "ready"]

    theme_counts: Dict[str, int] = {}
    for insight in insights:
        for theme in insight.improvement_areas:
            theme_counts[theme.theme] = theme_counts.get(theme.theme, 0) + 1

    return {
        "employees_analyzed": len(insights),
        "average_rating": _round(sum(float(i.latest_rating or 0) for i in rated) / len(rated))
        if rated
        else None,
        "average_goal_attainment": _round(
            sum(i.goal_summary.weighted_attainment for i in insights) / len(insights)
        )
        if insights
        else None,
        "rating_distribution": distribution,
        "declining_count": len(declining),
        "declining": [
            {"employee_id": i.employee_id, "name": i.full_name, "delta": i.rating_delta}
            for i in declining
        ][:10],
        "promotion_ready": [
            {
                "employee_id": i.employee_id,
                "name": i.full_name,
                "rating": i.latest_rating,
                "attainment": i.goal_summary.weighted_attainment,
            }
            for i in promotion_ready
        ][:10],
        "common_development_themes": sorted(
            ({"theme": k, "employees": v} for k, v in theme_counts.items()),
            key=lambda d: -int(d["employees"]),
        )[:5],
        "top_performers": [
            {"employee_id": i.employee_id, "name": i.full_name, "score": i.overall_score}
            for i in insights[:5]
        ],
    }


def _attendance_section(db: Session, employees: Sequence) -> Dict[str, object]:
    absence_values: List[float] = []
    overtime_values: List[float] = []
    per_department: Dict[str, Dict[str, List[float]]] = {}
    burnout: List[Dict[str, object]] = []

    for employee in employees:
        absence, _late, overtime = attendance_metrics(db, employee.id)
        if absence is None and overtime is None:
            continue
        department = employee.department or "Unassigned"
        entry = per_department.setdefault(department, {"absence": [], "overtime": []})
        if absence is not None:
            absence_values.append(absence)
            entry["absence"].append(absence)
        if overtime is not None:
            overtime_values.append(overtime)
            entry["overtime"].append(overtime)
            # Sustained overtime is the clearest burnout signal in attendance data.
            if overtime >= 8.0:
                burnout.append(
                    {
                        "employee_id": employee.id,
                        "name": employee.full_name,
                        "department": department,
                        "weekly_overtime": overtime,
                        "absence_rate": absence,
                    }
                )

    departments = [
        {
            "department": name,
            "average_absence_rate": _round(sum(data["absence"]) / len(data["absence"]) * 100)
            if data["absence"]
            else None,
            "average_weekly_overtime": _round(sum(data["overtime"]) / len(data["overtime"]))
            if data["overtime"]
            else None,
            "employees": max(len(data["absence"]), len(data["overtime"])),
        }
        for name, data in per_department.items()
    ]
    departments.sort(key=lambda d: (d["average_weekly_overtime"] or 0), reverse=True)  # type: ignore[arg-type]

    return {
        "employees_with_records": len(absence_values) or len(overtime_values),
        "average_absence_rate": _round(sum(absence_values) / len(absence_values) * 100)
        if absence_values
        else None,
        "average_weekly_overtime": _round(sum(overtime_values) / len(overtime_values))
        if overtime_values
        else None,
        "by_department": departments,
        "overtime_watchlist": sorted(
            burnout, key=lambda b: b["weekly_overtime"], reverse=True  # type: ignore[arg-type,return-value]
        )[:10],
    }


def _skills_section(graph: SkillGraph) -> Dict[str, object]:
    section = dict(graph.summary)
    section["top_gaps"] = [
        {
            "skill": n.skill,
            "gap": max(n.gap_current, n.gap_future),
            "status": n.status,
            "importance": n.importance,
            "qualified_holders": n.qualified_holders,
            "reskilling_candidate": n.reskilling_candidates[0].full_name
            if n.reskilling_candidates
            else None,
            "action": n.recommended_action,
        }
        for n in graph.nodes
        if n.status in {"critical_gap", "at_risk"}
    ][:10]
    return section


def _onboarding_section(db: Session) -> Dict[str, object]:
    plans = list_onboarding_plans(db, status="active")
    summaries: List[Dict[str, object]] = []
    stalled: List[Dict[str, object]] = []

    for plan in plans:
        tasks = [
            {
                "title": t.title,
                "phase": t.phase,
                "status": t.status,
                "mandatory": t.mandatory,
            }
            for t in plan.tasks
        ]
        progress = journey_progress(tasks)
        record = {
            "plan_id": plan.id,
            "employee_id": plan.employee_id,
            "employee": plan.employee.full_name if plan.employee else None,
            "role": plan.role,
            "completion_percent": progress["completion_percent"],
            "mandatory_outstanding": progress["mandatory_outstanding"],
            "targeted_skill_gaps": plan.targeted_skill_gaps or [],
        }
        summaries.append(record)
        if progress["mandatory_outstanding"]:
            stalled.append(record)

    return {
        "active_plans": len(plans),
        "average_completion": _round(
            sum(float(s["completion_percent"]) for s in summaries) / len(summaries)
        )
        if summaries
        else None,
        "plans": summaries[:10],
        "with_outstanding_mandatory": stalled[:10],
    }


# --------------------------------------------------------------------------
# Cross-source reasoning
# --------------------------------------------------------------------------
def _build_insights(
    *,
    assessments: Sequence[AttritionAssessment],
    performance: Sequence[PerformanceInsight],
    graph: SkillGraph,
    rankings: Sequence[CandidateRanking],
    recruitment: Dict[str, object],
    attendance: Dict[str, object],
    onboarding: Dict[str, object],
    employee_skills: Dict[int, List[str]],
) -> List[CrossSourceInsight]:
    insights: List[CrossSourceInsight] = []

    risk_by_id = {a.employee_id: a for a in assessments if a.employee_id is not None}
    perf_by_id = {p.employee_id: p for p in performance if p.employee_id is not None}
    high_risk = [a for a in assessments if a.risk_band in {"high", "critical"}]

    # 1. Flight risk on a single point of failure: attrition x skill graph.
    spof_skills = {
        n.skill: n for n in graph.nodes if n.single_point_of_failure and n.holders
    }
    for assessment in high_risk:
        held = employee_skills.get(assessment.employee_id or -1, [])
        exposed = [s for s in held if s in spof_skills]
        if not exposed:
            continue
        insights.append(
            CrossSourceInsight(
                title=f"{assessment.full_name} is a retention risk and the only holder of {exposed[0]}",
                severity="critical",
                detail=(
                    f"{assessment.full_name} scores {assessment.risk_score:.0f}/100 flight risk "
                    f"({assessment.risk_band}) and is the only qualified holder of "
                    f"{', '.join(exposed)}, which the organisation lists as a core requirement. "
                    f"Largest risk driver: {assessment.factors[0].evidence if assessment.factors else 'n/a'}"
                ),
                recommended_action=(
                    f"Act on retention now and cross-train a second person on {exposed[0]} in parallel."
                ),
                sources=["attrition_model", "skill_graph", "employee_skills"],
                entities=[assessment.full_name, *exposed],
            )
        )

    # 2. Regretted attrition: attrition x performance.
    for assessment in high_risk:
        insight = perf_by_id.get(assessment.employee_id)
        if not insight or insight.latest_rating is None:
            continue
        if float(insight.latest_rating) < 4.0:
            continue
        insights.append(
            CrossSourceInsight(
                title=f"High performer at risk: {assessment.full_name}",
                severity="critical",
                detail=(
                    f"Rating {insight.latest_rating:.1f}/5 ({insight.rating_trajectory}) with "
                    f"{insight.goal_summary.weighted_attainment:.0f}% goal attainment, but flight risk is "
                    f"{assessment.risk_score:.0f}/100. This is regretted attrition if it happens."
                ),
                recommended_action=(
                    assessment.recommended_actions[0].action
                    if assessment.recommended_actions
                    else "Hold a retention conversation this week."
                ),
                sources=["attrition_model", "performance_reviews", "goals"],
                entities=[assessment.full_name],
            )
        )

    # 3. Promotion-ready but stagnant: performance x attrition drivers.
    for insight in performance:
        if insight.promotion_readiness != "ready":
            continue
        assessment = risk_by_id.get(insight.employee_id)
        if not assessment:
            continue
        stagnation = next((f for f in assessment.factors if f.name == "career_stagnation"), None)
        if stagnation and stagnation.risk >= 60.0:
            insights.append(
                CrossSourceInsight(
                    title=f"{insight.full_name} is promotion-ready but has stagnated",
                    severity="warning",
                    detail=(
                        f"Meets the promotion bar (rating {insight.latest_rating}, "
                        f"{insight.goal_summary.weighted_attainment:.0f}% attainment) while "
                        f"{stagnation.evidence.lower()} Flight risk is {assessment.risk_score:.0f}/100."
                    ),
                    recommended_action="Put forward at the next calibration or explain the timeline explicitly.",
                    sources=["performance_reviews", "attrition_model"],
                    entities=[insight.full_name],
                )
            )

    # 4. Critical skill gap with no requisition open: skill graph x recruitment.
    required_by_job: Dict[str, List[str]] = recruitment.get("required_skills_by_job", {})  # type: ignore[assignment]
    skills_being_hired = {s for skills in required_by_job.values() for s in skills}
    for node in graph.nodes:
        if node.status != "critical_gap":
            continue
        if node.skill in skills_being_hired:
            continue
        reskill = node.reskilling_candidates[0] if node.reskilling_candidates else None
        insights.append(
            CrossSourceInsight(
                title=f"Critical {node.skill} gap with no open requisition",
                severity="critical" if node.importance == "core" else "warning",
                detail=(
                    f"{node.skill} is a {node.importance or 'required'} skill with "
                    f"{node.qualified_holders} qualified holder(s) against demand of "
                    f"{max(node.demand_current, node.demand_future)}, and no open requisition lists it."
                    + (
                        f" {reskill.full_name} is the closest internal fit ({reskill.affinity:.0f}% affinity)."
                        if reskill
                        else " No internal bench exists."
                    )
                ),
                recommended_action=(
                    f"Start {reskill.full_name} on a {node.skill} development plan"
                    if reskill
                    else f"Open a requisition for {node.skill}"
                ),
                sources=["skill_graph", "job_requisitions"],
                entities=[node.skill] + ([reskill.full_name] if reskill else []),
            )
        )

    # 5. Pipeline candidate who would close a known gap: recruitment x skill graph.
    gap_skills = {
        n.skill for n in graph.nodes if n.status in {"critical_gap", "at_risk"}
    }
    for ranking in rankings:
        if ranking.recommendation not in {"recommend_hire", "advance_to_interview"}:
            continue
        closes = [s for s in ranking.matched_skills if s in gap_skills]
        if not closes:
            continue
        insights.append(
            CrossSourceInsight(
                title=f"{ranking.full_name} would close the {closes[0]} gap",
                severity="opportunity",
                detail=(
                    f"Candidate scores {ranking.final_score:.0f}% role match and already evidences "
                    f"{', '.join(closes)}, which the workforce currently lacks."
                ),
                recommended_action="Prioritise this candidate in the pipeline; the hire fixes a known workforce gap.",
                sources=["candidate_ranking", "skill_graph"],
                entities=[ranking.full_name, *closes],
            )
        )

    # 6. Burnout cluster: attendance x attrition.
    watchlist = attendance.get("overtime_watchlist") or []
    for row in watchlist[:5]:  # type: ignore[index]
        assessment = risk_by_id.get(int(row["employee_id"]))  # type: ignore[index,call-overload]
        if not assessment or assessment.risk_score < 55.0:
            continue
        insights.append(
            CrossSourceInsight(
                title=f"Burnout risk: {row['name']}",  # type: ignore[index]
                severity="warning",
                detail=(
                    f"{row['weekly_overtime']}h average weekly overtime alongside a "  # type: ignore[index]
                    f"{assessment.risk_score:.0f}/100 flight risk score."
                ),
                recommended_action="Rebalance workload before the next review cycle.",
                sources=["attendance", "attrition_model"],
                entities=[str(row["name"])],  # type: ignore[index]
            )
        )

    # 7. Department under double pressure: attrition x skills.
    #
    # Keyed on the count of genuinely at-risk people rather than the department's
    # average risk: an average is dragged down by a healthy majority and hides the
    # two people whose departure would actually hurt.
    department_high_risk: Dict[str, List[str]] = {}
    department_average: Dict[str, float] = {}
    for row in attrition_overview(assessments).get("by_department") or []:  # type: ignore[union-attr]
        department_average[str(row["department"])] = float(row["average_risk"])  # type: ignore[index]
    for assessment in high_risk:
        department_high_risk.setdefault(assessment.department or "Unassigned", []).append(
            assessment.full_name
        )

    gap_departments: Dict[str, set] = {}
    for node in graph.nodes:
        if node.status not in {"critical_gap", "at_risk"}:
            continue
        # Requirement departments first: a skill nobody holds still belongs to the
        # department that needs it.
        for department in (node.demand_departments or node.departments or []):
            gap_departments.setdefault(department, set()).add(node.skill)

    for department, gap_skills_in_department in gap_departments.items():
        at_risk_people = department_high_risk.get(department, [])
        if len(gap_skills_in_department) < 2 or not at_risk_people:
            continue
        average = department_average.get(department)
        insights.append(
            CrossSourceInsight(
                title=f"{department} is exposed on both attrition and skills",
                severity="warning",
                detail=(
                    f"{department} carries {len(gap_skills_in_department)} under-covered skills "
                    f"({', '.join(sorted(gap_skills_in_department)[:4])}) and has "
                    f"{len(at_risk_people)} employee(s) at high flight risk "
                    f"({', '.join(at_risk_people[:3])})"
                    + (f". Average departmental risk is {average:.0f}/100." if average is not None else ".")
                    + " Losing anyone compounds the gap."
                ),
                recommended_action=(
                    f"Treat {department} as a joint retention and hiring priority this quarter."
                ),
                sources=["attrition_model", "skill_graph"],
                entities=[department, *at_risk_people[:3]],
            )
        )

    # 8. Onboarding stalling on mandatory compliance tasks.
    outstanding = onboarding.get("with_outstanding_mandatory") or []
    if outstanding:
        names = [str(row["employee"]) for row in outstanding[:3]]  # type: ignore[index]
        insights.append(
            CrossSourceInsight(
                title=f"{len(outstanding)} new joiner(s) have outstanding mandatory onboarding tasks",  # type: ignore[arg-type]
                severity="warning",
                detail=(
                    "Mandatory compliance and setup tasks are incomplete for: "
                    + ", ".join(names)
                    + ". Early-tenure employees are already the highest-churn group."
                ),
                recommended_action="Chase the outstanding mandatory tasks with the assigned owners.",
                sources=["onboarding_plans"],
                entities=names,
            )
        )

    # 9. Recruitment conflicts (resume vs interview).
    conflicts = recruitment.get("conflicts") or []
    if conflicts:
        insights.append(
            CrossSourceInsight(
                title=f"{len(conflicts)} candidate(s) show a resume/interview conflict",  # type: ignore[arg-type]
                severity="warning",
                detail=(
                    "These candidates match the requisition on paper but interviewed poorly: "
                    + ", ".join(str(c["candidate"]) for c in conflicts[:3])  # type: ignore[index]
                    + "."
                ),
                recommended_action="Verify claimed skills with a practical assessment before advancing.",
                sources=["candidate_ranking", "interview_scores"],
                entities=[str(c["candidate"]) for c in conflicts[:3]],  # type: ignore[index]
            )
        )

    severity_order = {"critical": 0, "warning": 1, "opportunity": 2, "info": 3}
    insights.sort(key=lambda i: severity_order.get(i.severity, 9))
    return insights


def build_decision_dashboard(db: Session) -> DecisionDashboard:
    """
    Assemble the full HR decision view.

    Every section is computed from stored data, and the insight list is derived by
    correlating those sections against each other.
    """
    employees = list_employees(db, status="active", limit=1000)

    assessments = assess_workforce_attrition(db)
    performance = analyze_workforce_performance(db)
    graph = build_workforce_skill_graph(db)

    recruitment, rankings, _job_titles = _recruitment_section(db)
    workforce_risk = _workforce_risk_section(assessments)
    performance_section = _performance_section(performance)
    attendance = _attendance_section(db, employees)
    skills = _skills_section(graph)
    onboarding = _onboarding_section(db)

    employee_skills: Dict[int, List[str]] = {}
    for profile in graph.edges:
        if profile.get("type") != "holds":
            continue
        source = str(profile.get("source", ""))
        if not source.startswith("employee:"):
            continue
        try:
            employee_id = int(source.split(":", 1)[1])
        except (ValueError, IndexError):
            continue
        employee_skills.setdefault(employee_id, []).append(str(profile.get("target_label")))

    insights = _build_insights(
        assessments=assessments,
        performance=performance,
        graph=graph,
        rankings=rankings,
        recruitment=recruitment,
        attendance=attendance,
        onboarding=onboarding,
        employee_skills=employee_skills,
    )

    headline: Dict[str, object] = {
        "headcount": len(employees),
        "open_requisitions": recruitment["open_requisitions"],
        "candidates_in_pipeline": recruitment["total_candidates"],
        "high_attrition_risk": workforce_risk["high_risk_count"],
        "average_attrition_risk": workforce_risk["average_risk"],
        "average_performance_rating": performance_section["average_rating"],
        "average_absence_rate": attendance["average_absence_rate"],
        "critical_skill_gaps": len(skills.get("critical_gaps") or []),
        "active_onboarding": onboarding["active_plans"],
        "cross_source_insights": len(insights),
    }

    # Only claim a source when data for it actually exists.
    data_sources = ["employees"]
    if recruitment["total_candidates"]:
        data_sources.append("recruitment")
    if attendance["employees_with_records"]:
        data_sources.append("attendance")
    if performance_section["employees_analyzed"]:
        data_sources.append("performance")
    if graph.summary.get("skills_tracked"):
        data_sources.append("skill_graph")
    if onboarding["active_plans"]:
        data_sources.append("onboarding")

    return DecisionDashboard(
        headline=headline,
        recruitment=recruitment,
        workforce_risk=workforce_risk,
        performance=performance_section,
        attendance=attendance,
        skills=skills,
        onboarding=onboarding,
        insights=insights,
        data_sources=data_sources,
    )
