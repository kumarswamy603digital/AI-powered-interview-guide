from __future__ import annotations

"""
Service layer between the database and the workforce engines.

The engines in app.core.attrition / performance_intel / skill_graph /
onboarding_agent / policy_qa are deliberately DB-free so they can be tested
directly. This module owns the mapping from ORM rows to engine inputs, so
"which signals exist for this employee" is answered in exactly one place.
"""

from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.attrition import (
    AttritionAssessment,
    EmployeeSignals,
    assess_attrition_risk,
    assess_many,
)
from app.core.onboarding_agent import OnboardingProfile
from app.core.performance_intel import (
    FeedbackInput,
    GoalInput,
    PerformanceInsight,
    PerformanceSignals,
    ReviewInput,
    analyze_performance,
    score_sentiment,
)
from app.core.policy_qa import EmployeeContext, PolicyChunkInput
from app.core.skill_graph import (
    EmployeeSkillProfile,
    RequirementInput,
    SkillGraph,
    SkillHolding,
    build_skill_graph,
)
from app.crud.workforce import (
    department_attrition_rate,
    department_average_rating,
    list_all_employee_skills,
    list_attendance,
    list_employee_skills,
    list_employees,
    list_feedback,
    list_goals,
    list_policy_chunks,
    list_reviews,
    list_skill_requirements,
)
from app.models.workforce import Employee


# Attendance window. Long enough to smooth holidays, short enough that a pattern
# from two years ago does not drive a retention conversation today.
ATTENDANCE_WINDOW_DAYS = 180

# Statuses that represent a day the employee was expected at work.
_EXPECTED_STATUSES = {"present", "remote", "absent"}
_WORKED_STATUSES = {"present", "remote"}


def attendance_metrics(
    db: Session,
    employee_id: int,
    *,
    window_days: int = ATTENDANCE_WINDOW_DAYS,
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """
    (unplanned_absence_rate, late_arrival_rate, average_weekly_overtime).

    Approved leave and holidays are excluded from the absence rate: penalising
    someone for taking sanctioned leave would make the risk score both wrong and
    unusable in a retention conversation.
    """
    since = date.today() - timedelta(days=window_days)
    records = list_attendance(db, employee_id, since=since, limit=window_days + 10)
    if not records:
        return None, None, None

    expected = [r for r in records if r.status in _EXPECTED_STATUSES]
    worked = [r for r in records if r.status in _WORKED_STATUSES]

    absence_rate = (
        round(sum(1 for r in expected if r.status == "absent") / len(expected), 4)
        if expected
        else None
    )
    late_rate = (
        round(sum(1 for r in worked if r.late_arrival) / len(worked), 4) if worked else None
    )

    overtime_total = sum(float(r.overtime_hours or 0.0) for r in records)
    span_days = max(1, (max(r.work_date for r in records) - min(r.work_date for r in records)).days + 1)
    weekly_overtime = round(overtime_total / (span_days / 7.0), 2) if span_days else None

    return absence_rate, late_rate, weekly_overtime


def months_since_last_change(employee: Employee) -> Optional[float]:
    """
    Months since promotion, falling back to hire date.

    Someone never promoted is not "0 months since promotion"; their whole tenure
    is the stagnation window, which is exactly the signal that matters.
    """
    anchor = employee.last_promotion_date or employee.hire_date
    if not anchor:
        return None
    return round((date.today() - anchor).days / 30.44, 1)


def _feedback_sentiment_average(db: Session, employee_id: int) -> Optional[float]:
    values: List[float] = []
    for item in list_feedback(db, employee_id, limit=50):
        value = item.sentiment if item.sentiment is not None else score_sentiment(item.content)
        if value is not None:
            values.append(float(value))
    return round(sum(values) / len(values), 3) if values else None


def build_employee_signals(db: Session, employee: Employee) -> EmployeeSignals:
    """Gather every attrition signal available for one employee."""
    absence_rate, late_rate, overtime = attendance_metrics(db, employee.id)

    reviews = list_reviews(db, employee.id)
    ratings = tuple(float(r.rating) for r in reviews if r.rating is not None)

    goals = list_goals(db, employee.id)
    missed = sum(1 for g in goals if (g.status or "") == "missed")

    skills = [s.skill for s in list_employee_skills(db, employee.id)]

    return EmployeeSignals(
        employee_id=employee.id,
        full_name=employee.full_name,
        department=employee.department or "",
        job_title=employee.job_title or "",
        seniority=employee.seniority,
        tenure_years=round(employee.tenure_years, 2),
        months_since_last_promotion=months_since_last_change(employee),
        performance_ratings=ratings,
        goals_missed=missed,
        goals_total=len(goals),
        engagement_score=employee.engagement_score,
        average_feedback_sentiment=_feedback_sentiment_average(db, employee.id),
        unplanned_absence_rate=absence_rate,
        late_arrival_rate=late_rate,
        average_weekly_overtime=overtime,
        compa_ratio=employee.compa_ratio,
        department_attrition_rate_12m=department_attrition_rate(db, employee.department or ""),
        skills=tuple(skills),
    )


def assess_employee_attrition(db: Session, employee: Employee) -> AttritionAssessment:
    return assess_attrition_risk(build_employee_signals(db, employee))


def assess_workforce_attrition(
    db: Session,
    *,
    department: Optional[str] = None,
    limit: int = 500,
) -> List[AttritionAssessment]:
    """Assess every active employee, highest risk first."""
    employees = list_employees(db, department=department, status="active", limit=limit)
    return assess_many([build_employee_signals(db, e) for e in employees])


def build_performance_signals(db: Session, employee: Employee) -> PerformanceSignals:
    """Gather goals, feedback and review history for one employee."""
    reviews = [
        ReviewInput(
            period=r.period or "",
            rating=float(r.rating) if r.rating is not None else None,
            potential_rating=float(r.potential_rating) if r.potential_rating is not None else None,
            strengths=tuple(r.strengths or ()),
            improvements=tuple(r.improvements or ()),
            comments=r.comments or "",
            promotion_ready=r.promotion_ready,
        )
        for r in list_reviews(db, employee.id)
    ]
    goals = [
        GoalInput(
            title=g.title or "",
            status=g.status or "not_started",
            progress=float(g.progress or 0.0),
            weight=float(g.weight or 1.0),
            related_skills=tuple(g.related_skills or ()),
        )
        for g in list_goals(db, employee.id)
    ]
    feedback = [
        FeedbackInput(
            source=f.source or "peer",
            content=f.content or "",
            sentiment=float(f.sentiment) if f.sentiment is not None else None,
        )
        for f in list_feedback(db, employee.id)
    ]

    return PerformanceSignals(
        employee_id=employee.id,
        full_name=employee.full_name,
        department=employee.department or "",
        job_title=employee.job_title or "",
        seniority=employee.seniority,
        reviews=tuple(reviews),
        goals=tuple(goals),
        feedback=tuple(feedback),
        department_average_rating=department_average_rating(db, employee.department or ""),
    )


def analyze_employee_performance(db: Session, employee: Employee) -> PerformanceInsight:
    return analyze_performance(build_performance_signals(db, employee))


def analyze_workforce_performance(
    db: Session,
    *,
    department: Optional[str] = None,
    limit: int = 500,
) -> List[PerformanceInsight]:
    employees = list_employees(db, department=department, status="active", limit=limit)
    insights = [analyze_employee_performance(db, e) for e in employees]
    insights.sort(key=lambda i: i.overall_score, reverse=True)
    return insights


# --------------------------------------------------------------------------
# Skill graph
# --------------------------------------------------------------------------
def build_skill_profiles(db: Session, *, include_inactive: bool = False) -> List[EmployeeSkillProfile]:
    """
    Skill profiles for the whole organisation.

    Skills are fetched in one query and grouped in memory rather than per
    employee, so the graph does not issue a query per person.
    """
    employees = list_employees(db, status=None if include_inactive else "active", limit=1000)
    skills_by_employee: Dict[int, List[SkillHolding]] = {}
    for record in list_all_employee_skills(db):
        skills_by_employee.setdefault(record.employee_id, []).append(
            SkillHolding(
                skill=record.skill,
                proficiency=int(record.proficiency or 3),
                verified=bool(record.verified),
            )
        )

    return [
        EmployeeSkillProfile(
            employee_id=e.id,
            full_name=e.full_name,
            department=e.department or "",
            job_title=e.job_title or "",
            status=e.status or "active",
            skills=tuple(skills_by_employee.get(e.id, ())),
        )
        for e in employees
    ]


def build_requirement_inputs(db: Session) -> List[RequirementInput]:
    return [
        RequirementInput(
            skill=r.skill,
            department=r.department,
            role=r.role,
            importance=r.importance or "important",
            horizon=r.horizon or "current",
            required_headcount=int(r.required_headcount or 1),
            required_proficiency=int(r.required_proficiency or 3),
            target_date=r.target_date.isoformat() if r.target_date else None,
            rationale=r.rationale,
        )
        for r in list_skill_requirements(db)
    ]


def build_workforce_skill_graph(db: Session) -> SkillGraph:
    return build_skill_graph(build_skill_profiles(db), build_requirement_inputs(db))


def role_required_skills(db: Session, employee: Employee) -> List[str]:
    """
    Skills required for an employee's role.

    Prefers requirements naming their exact role, then falls back to
    department-wide requirements, so onboarding still personalises when the
    organisation has only defined requirements at department level.
    """
    requirements = list_skill_requirements(db)
    title = (employee.job_title or "").strip().lower()
    department = (employee.department or "").strip().lower()

    role_specific = [
        r.skill
        for r in requirements
        if r.role and title and (r.role.strip().lower() in title or title in r.role.strip().lower())
    ]
    if role_specific:
        return list(dict.fromkeys(role_specific))

    department_wide = [
        r.skill
        for r in requirements
        if r.department and department and r.department.strip().lower() == department
    ]
    return list(dict.fromkeys(department_wide))


# --------------------------------------------------------------------------
# Onboarding + policy inputs
# --------------------------------------------------------------------------
def build_onboarding_profile(
    db: Session,
    employee: Employee,
    *,
    buddy_name: Optional[str] = None,
) -> OnboardingProfile:
    manager = employee.manager
    return OnboardingProfile(
        employee_id=employee.id,
        full_name=employee.full_name,
        department=employee.department or "",
        job_title=employee.job_title or "",
        seniority=employee.seniority,
        work_mode=employee.work_mode,
        location=employee.location,
        employment_type=employee.employment_type,
        start_date=employee.hire_date.isoformat() if employee.hire_date else None,
        manager_name=manager.full_name if manager else None,
        buddy_name=buddy_name,
        skills=tuple(s.skill for s in list_employee_skills(db, employee.id)),
    )


def build_policy_chunk_inputs(db: Session) -> List[PolicyChunkInput]:
    chunks: List[PolicyChunkInput] = []
    for chunk in list_policy_chunks(db):
        document = chunk.document
        chunks.append(
            PolicyChunkInput(
                chunk_id=chunk.id,
                policy_id=document.id if document else None,
                policy_title=document.title if document else "",
                category=document.category if document else None,
                section=chunk.section,
                content=chunk.content,
                version=document.version if document else None,
                effective_date=(
                    document.effective_date.isoformat()
                    if document and document.effective_date
                    else None
                ),
                applies_to=document.applies_to if document else None,
            )
        )
    return chunks


def build_employee_context(db: Session, employee: Employee) -> EmployeeContext:
    return EmployeeContext(
        employee_id=employee.id,
        full_name=employee.full_name,
        location=employee.location,
        employment_type=employee.employment_type,
        department=employee.department,
        tenure_years=round(employee.tenure_years, 2),
    )


def suggest_buddy(db: Session, employee: Employee) -> Optional[Employee]:
    """
    Pick an onboarding buddy: same department, tenured, not the manager.

    Longest-tenured available colleague, because buddies need institutional
    knowledge more than they need seniority.
    """
    candidates = [
        e
        for e in list_employees(db, department=employee.department, status="active", limit=200)
        if e.id != employee.id and e.id != employee.manager_id and e.tenure_years >= 1.0
    ]
    if not candidates:
        return None
    return sorted(candidates, key=lambda e: e.tenure_years, reverse=True)[0]
