from __future__ import annotations

from dataclasses import asdict
from datetime import date, timedelta
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import require_hr_user
from app.core.onboarding_agent import generate_onboarding_journey, journey_progress
from app.core.performance_intel import score_sentiment
from app.core.skills import canonical_skill, match_skills
from app.core.workforce_intelligence import (
    analyze_employee_performance,
    assess_employee_attrition,
    attendance_metrics,
    build_onboarding_profile,
    role_required_skills,
    suggest_buddy,
)
from app.crud.hr import get_candidate, latest_resume_for_candidate, set_candidate_stage
from app.crud.workforce import (
    add_employee_skill,
    create_employee,
    create_onboarding_plan,
    delete_employee_skill,
    get_employee,
    latest_onboarding_plan,
    list_attendance,
    list_departments,
    list_employee_skills,
    list_employees,
    list_feedback,
    list_goals,
    list_reviews,
    update_employee,
)
from app.db.session import get_db
from app.models.user import User
from app.models.workforce import Employee
from app.schemas.workforce import (
    AttendanceSummaryRead,
    AttritionAssessmentRead,
    Employee360Read,
    EmployeeCreate,
    EmployeeFromCandidate,
    EmployeeRead,
    EmployeeSkillCreate,
    EmployeeSkillRead,
    EmployeeStatus,
    EmployeeUpdate,
    FeedbackRead,
    GoalRead,
    PerformanceInsightRead,
    ReviewRead,
)
from app.core.workforce_intelligence import ATTENDANCE_WINDOW_DAYS


router = APIRouter(prefix="/api/employees", tags=["employees"])

DbSessionDep = Annotated[Session, Depends(get_db)]
HrUserDep = Annotated[User, Depends(require_hr_user)]


def _to_read(db: Session, employee: Employee) -> EmployeeRead:
    payload = EmployeeRead.model_validate(employee)
    payload.tenure_years = round(employee.tenure_years, 2)
    payload.manager_name = employee.manager.full_name if employee.manager else None
    payload.skills = [s.skill for s in list_employee_skills(db, employee.id)]
    payload.direct_report_count = len(
        [r for r in (employee.direct_reports or []) if r.status == "active"]
    )
    return payload


def _attendance_summary(db: Session, employee_id: int) -> AttendanceSummaryRead:
    absence, late, overtime = attendance_metrics(db, employee_id)
    # Actual number of recorded days in the window; this previously reported 0/1,
    # which read like a day count but was really "any data at all".
    window_start = date.today() - timedelta(days=ATTENDANCE_WINDOW_DAYS)
    recorded = len(
        list_attendance(db, employee_id, since=window_start, limit=ATTENDANCE_WINDOW_DAYS + 10)
    )
    return AttendanceSummaryRead(
        employee_id=employee_id,
        window_days=ATTENDANCE_WINDOW_DAYS,
        days_recorded=recorded,
        unplanned_absence_rate=absence,
        late_arrival_rate=late,
        average_weekly_overtime=overtime,
        note=(
            "Approved leave and holidays are excluded from the absence rate."
            if recorded
            else "No attendance records in the window."
        ),
    )


@router.post("", response_model=EmployeeRead, status_code=status.HTTP_201_CREATED)
def add_employee(
    payload: EmployeeCreate,
    db: DbSessionDep,
    hr_user: HrUserDep,
) -> EmployeeRead:
    if payload.manager_id is not None and get_employee(db, payload.manager_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Manager {payload.manager_id} not found.",
        )

    fields = payload.model_dump()
    if fields.get("email"):
        fields["email"] = str(fields["email"])
    employee = create_employee(db, **fields)
    return _to_read(db, employee)


@router.get("", response_model=List[EmployeeRead])
def list_all_employees(
    db: DbSessionDep,
    hr_user: HrUserDep,
    department: Optional[str] = Query(default=None),
    employee_status: Optional[EmployeeStatus] = Query(default="active", alias="status"),
    manager_id: Optional[int] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
) -> List[EmployeeRead]:
    employees = list_employees(
        db,
        department=department,
        status=employee_status,
        manager_id=manager_id,
        limit=limit,
    )
    return [_to_read(db, e) for e in employees]


@router.get("/departments", response_model=List[str])
def get_departments(db: DbSessionDep, hr_user: HrUserDep) -> List[str]:
    return list_departments(db)


@router.post("/from-candidate", response_model=EmployeeRead, status_code=status.HTTP_201_CREATED)
def convert_candidate_to_employee(
    payload: EmployeeFromCandidate,
    db: DbSessionDep,
    hr_user: HrUserDep,
) -> EmployeeRead:
    """
    Hire a candidate: create the employee record and carry their assessed skills
    across, so recruitment intelligence feeds the workforce skill graph instead of
    being discarded at offer stage.
    """
    candidate = get_candidate(db, payload.candidate_id)
    if candidate is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")
    if payload.manager_id is not None and get_employee(db, payload.manager_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Manager {payload.manager_id} not found."
        )

    employee = create_employee(
        db,
        full_name=candidate.full_name,
        email=candidate.email,
        department=payload.department,
        job_title=payload.job_title,
        seniority=payload.seniority,
        location=payload.location,
        employment_type=payload.employment_type,
        work_mode=payload.work_mode,
        manager_id=payload.manager_id,
        hire_date=payload.hire_date,
        compa_ratio=payload.compa_ratio,
        source_candidate_id=candidate.id,
        status="active",
    )

    # Skills evidenced during hiring become verified employee skills.
    resume = latest_resume_for_candidate(db, candidate.id)
    for skill in (resume.extracted_skills or []) if resume else []:
        canonical = canonical_skill(skill)
        if canonical:
            add_employee_skill(
                db,
                employee_id=employee.id,
                skill=canonical,
                proficiency=3,
                source="resume",
                verified=True,
            )

    set_candidate_stage(db, candidate, "hired")

    if payload.generate_onboarding_plan:
        buddy = suggest_buddy(db, employee)
        profile = build_onboarding_profile(
            db, employee, buddy_name=buddy.full_name if buddy else None
        )
        journey = generate_onboarding_journey(
            profile, role_required_skills=role_required_skills(db, employee)
        )
        create_onboarding_plan(
            db,
            employee_id=employee.id,
            role=employee.job_title,
            department=employee.department,
            seniority=employee.seniority,
            work_mode=employee.work_mode,
            buddy_id=buddy.id if buddy else None,
            start_date=employee.hire_date,
            status="active",
            summary=journey.summary,
            targeted_skill_gaps=journey.targeted_skill_gaps,
            tasks=[
                {
                    "title": t.title,
                    "description": t.description,
                    "phase": t.phase,
                    "category": t.category,
                    "day_offset": t.day_offset,
                    "owner": t.owner,
                    "mandatory": t.mandatory,
                    "rationale": t.rationale,
                    "status": "pending",
                }
                for t in journey.tasks
            ],
        )

    db.refresh(employee)
    return _to_read(db, employee)


@router.get("/{employee_id}", response_model=EmployeeRead)
def read_employee(employee_id: int, db: DbSessionDep, hr_user: HrUserDep) -> EmployeeRead:
    employee = get_employee(db, employee_id)
    if employee is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    return _to_read(db, employee)


@router.patch("/{employee_id}", response_model=EmployeeRead)
def patch_employee(
    employee_id: int,
    payload: EmployeeUpdate,
    db: DbSessionDep,
    hr_user: HrUserDep,
) -> EmployeeRead:
    employee = get_employee(db, employee_id)
    if employee is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")

    fields = payload.model_dump(exclude_unset=True)
    if fields.get("email"):
        fields["email"] = str(fields["email"])
    employee = update_employee(db, employee, **fields)
    return _to_read(db, employee)


@router.get("/{employee_id}/skills", response_model=List[EmployeeSkillRead])
def read_employee_skills(
    employee_id: int, db: DbSessionDep, hr_user: HrUserDep
) -> List[EmployeeSkillRead]:
    if get_employee(db, employee_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    return [EmployeeSkillRead.model_validate(s) for s in list_employee_skills(db, employee_id)]


@router.post(
    "/{employee_id}/skills", response_model=EmployeeSkillRead, status_code=status.HTTP_201_CREATED
)
def add_skill(
    employee_id: int,
    payload: EmployeeSkillCreate,
    db: DbSessionDep,
    hr_user: HrUserDep,
) -> EmployeeSkillRead:
    if get_employee(db, employee_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    record = add_employee_skill(
        db,
        employee_id=employee_id,
        skill=payload.skill,
        proficiency=payload.proficiency,
        source=payload.source,
        verified=payload.verified,
    )
    return EmployeeSkillRead.model_validate(record)


@router.delete("/{employee_id}/skills/{skill}", status_code=status.HTTP_204_NO_CONTENT)
def remove_skill(
    employee_id: int,
    skill: str,
    db: DbSessionDep,
    hr_user: HrUserDep,
) -> None:
    if not delete_employee_skill(db, employee_id, canonical_skill(skill)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill not found")


@router.get("/{employee_id}/attendance-summary", response_model=AttendanceSummaryRead)
def read_attendance_summary(
    employee_id: int, db: DbSessionDep, hr_user: HrUserDep
) -> AttendanceSummaryRead:
    if get_employee(db, employee_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    return _attendance_summary(db, employee_id)


@router.get("/{employee_id}/360", response_model=Employee360Read)
def read_employee_360(employee_id: int, db: DbSessionDep, hr_user: HrUserDep) -> Employee360Read:
    """
    Everything known about one employee: skills, attendance, performance,
    attrition risk, review history and onboarding progress in one response.
    """
    employee = get_employee(db, employee_id)
    if employee is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")

    performance = analyze_employee_performance(db, employee)
    attrition = assess_employee_attrition(db, employee)

    feedback_items: List[FeedbackRead] = []
    for item in list_feedback(db, employee_id):
        payload = FeedbackRead.model_validate(item)
        if item.sentiment is None:
            payload.inferred_sentiment = score_sentiment(item.content or "")
        feedback_items.append(payload)

    plan = latest_onboarding_plan(db, employee_id)
    progress = None
    if plan:
        progress = journey_progress(
            [
                {"title": t.title, "phase": t.phase, "status": t.status, "mandatory": t.mandatory}
                for t in plan.tasks
            ]
        )

    held = [s.skill for s in list_employee_skills(db, employee_id)]
    _matched, missing = match_skills(
        role_required_skills(db, employee), resume_text="", known_skills=held
    )

    return Employee360Read(
        employee=_to_read(db, employee),
        skills=[EmployeeSkillRead.model_validate(s) for s in list_employee_skills(db, employee_id)],
        attendance=_attendance_summary(db, employee_id),
        performance=PerformanceInsightRead.model_validate(asdict(performance)),
        attrition=AttritionAssessmentRead.model_validate(asdict(attrition)),
        reviews=[ReviewRead.model_validate(r) for r in list_reviews(db, employee_id)],
        goals=[GoalRead.model_validate(g) for g in list_goals(db, employee_id)],
        feedback=feedback_items,
        onboarding_progress=progress,
        skill_gaps_for_role=missing,
    )
