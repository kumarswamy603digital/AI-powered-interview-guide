from __future__ import annotations

from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import require_hr_user
from app.core.onboarding_agent import (
    PHASE_LABELS,
    generate_onboarding_journey,
    journey_progress,
)
from app.core.workforce_intelligence import (
    build_onboarding_profile,
    role_required_skills,
    suggest_buddy,
)
from app.crud.workforce import (
    create_onboarding_plan,
    get_employee,
    get_onboarding_plan,
    get_onboarding_task,
    latest_onboarding_plan,
    list_onboarding_plans,
    update_onboarding_task,
)
from app.db.session import get_db
from app.models.onboarding import OnboardingPlan
from app.models.user import User
from app.schemas.onboarding import (
    OnboardingGenerateRequest,
    OnboardingJourneyRead,
    OnboardingPhaseRead,
    OnboardingPlanRead,
    OnboardingTaskRead,
    OnboardingTaskUpdate,
)


router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])

DbSessionDep = Annotated[Session, Depends(get_db)]
HrUserDep = Annotated[User, Depends(require_hr_user)]


def _plan_to_read(plan: OnboardingPlan) -> OnboardingPlanRead:
    tasks = [OnboardingTaskRead.model_validate(t) for t in plan.tasks]

    # Absolute due dates are more useful to a manager than day offsets.
    if plan.start_date:
        from datetime import timedelta

        for task, model in zip(tasks, plan.tasks):
            task.due_date = plan.start_date + timedelta(days=int(model.day_offset or 0))

    return OnboardingPlanRead(
        id=plan.id,
        employee_id=plan.employee_id,
        employee_name=plan.employee.full_name if plan.employee else None,
        role=plan.role,
        department=plan.department,
        seniority=plan.seniority,
        work_mode=plan.work_mode,
        buddy_id=plan.buddy_id,
        buddy_name=plan.buddy.full_name if plan.buddy else None,
        start_date=plan.start_date,
        status=plan.status,
        summary=plan.summary,
        targeted_skill_gaps=list(plan.targeted_skill_gaps or []),
        tasks=tasks,
        progress=journey_progress(
            [
                {"title": t.title, "phase": t.phase, "status": t.status, "mandatory": t.mandatory}
                for t in plan.tasks
            ]
        ),
        created_at=plan.created_at,
    )


@router.post("/generate", response_model=OnboardingJourneyRead)
def generate_journey(
    payload: OnboardingGenerateRequest,
    db: DbSessionDep,
    hr_user: HrUserDep,
) -> OnboardingJourneyRead:
    """
    Generate a personalised onboarding journey.

    Tailored by department, seniority, work mode, location, employment type and the
    employee's own skill gaps against the role's requirements. Every task carries
    the reason it is in this particular plan.
    """
    employee = get_employee(db, payload.employee_id)
    if employee is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")

    buddy = None
    if payload.buddy_id is not None:
        buddy = get_employee(db, payload.buddy_id)
        if buddy is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Buddy not found")
    else:
        buddy = suggest_buddy(db, employee)

    required = (
        payload.role_required_skills
        if payload.role_required_skills is not None
        else role_required_skills(db, employee)
    )

    profile = build_onboarding_profile(db, employee, buddy_name=buddy.full_name if buddy else None)
    journey = generate_onboarding_journey(profile, role_required_skills=required)

    if payload.persist:
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

    return OnboardingJourneyRead(
        employee_id=journey.employee_id,
        full_name=journey.full_name,
        role=journey.role,
        department=journey.department,
        seniority=journey.seniority,
        work_mode=journey.work_mode,
        buddy_name=journey.buddy_name,
        targeted_skill_gaps=journey.targeted_skill_gaps,
        personalization_notes=journey.personalization_notes,
        phases=[
            OnboardingPhaseRead(
                phase=phase.phase,
                label=phase.label,
                day_from=phase.day_from,
                day_to=phase.day_to,
                tasks=[
                    OnboardingTaskRead(
                        title=t.title,
                        description=t.description,
                        phase=t.phase,
                        category=t.category,
                        day_offset=t.day_offset,
                        owner=t.owner,
                        mandatory=t.mandatory,
                        rationale=t.rationale,
                    )
                    for t in phase.tasks
                ],
            )
            for phase in journey.phases
        ],
        tasks=[
            OnboardingTaskRead(
                title=t.title,
                description=t.description,
                phase=t.phase,
                category=t.category,
                day_offset=t.day_offset,
                owner=t.owner,
                mandatory=t.mandatory,
                rationale=t.rationale,
            )
            for t in journey.tasks
        ],
        mandatory_count=journey.mandatory_count,
        summary=journey.summary,
    )


@router.get("/plans", response_model=List[OnboardingPlanRead])
def list_plans(
    db: DbSessionDep,
    hr_user: HrUserDep,
    plan_status: Optional[str] = Query(default="active", alias="status"),
) -> List[OnboardingPlanRead]:
    return [_plan_to_read(p) for p in list_onboarding_plans(db, status=plan_status)]


@router.get("/plans/{plan_id}", response_model=OnboardingPlanRead)
def read_plan(plan_id: int, db: DbSessionDep, hr_user: HrUserDep) -> OnboardingPlanRead:
    plan = get_onboarding_plan(db, plan_id)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Onboarding plan not found")
    return _plan_to_read(plan)


@router.get("/employees/{employee_id}", response_model=OnboardingPlanRead)
def read_employee_plan(
    employee_id: int, db: DbSessionDep, hr_user: HrUserDep
) -> OnboardingPlanRead:
    if get_employee(db, employee_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    plan = latest_onboarding_plan(db, employee_id)
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No onboarding plan for this employee. Generate one first.",
        )
    return _plan_to_read(plan)


@router.patch("/tasks/{task_id}", response_model=OnboardingTaskRead)
def update_task(
    task_id: int,
    payload: OnboardingTaskUpdate,
    db: DbSessionDep,
    hr_user: HrUserDep,
) -> OnboardingTaskRead:
    task = get_onboarding_task(db, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    fields = payload.model_dump(exclude_unset=True)
    if fields.get("status") == "done" and not fields.get("completed_on"):
        from datetime import date

        fields["completed_on"] = date.today()

    task = update_onboarding_task(db, task, **fields)
    return OnboardingTaskRead.model_validate(task)


@router.get("/phases", response_model=dict)
def read_phases(hr_user: HrUserDep) -> dict:
    return {"phases": [{"phase": key, "label": label} for key, label in PHASE_LABELS.items()]}
