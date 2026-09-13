from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable, List, Optional, Sequence

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.onboarding import OnboardingPlan, OnboardingTask
from app.models.performance import Feedback, Goal, PerformanceReview
from app.models.policy import PolicyChunk, PolicyDocument
from app.models.workforce import (
    AttendanceRecord,
    Employee,
    EmployeeSkill,
    SkillRequirement,
)


# --------------------------------------------------------------------------
# Employees
# --------------------------------------------------------------------------
def create_employee(db: Session, **fields) -> Employee:
    employee = Employee(**fields)
    db.add(employee)
    db.commit()
    db.refresh(employee)
    return employee


def get_employee(db: Session, employee_id: int) -> Optional[Employee]:
    return db.query(Employee).filter(Employee.id == employee_id).first()


def list_employees(
    db: Session,
    *,
    department: Optional[str] = None,
    status: Optional[str] = "active",
    manager_id: Optional[int] = None,
    limit: int = 500,
) -> List[Employee]:
    query = db.query(Employee)
    if department:
        query = query.filter(Employee.department == department)
    if status:
        query = query.filter(Employee.status == status)
    if manager_id is not None:
        query = query.filter(Employee.manager_id == manager_id)
    return query.order_by(Employee.full_name.asc()).limit(limit).all()


# Columns that must always hold a value; an explicit null for these is ignored
# rather than allowed to fail at the database level.
_EMPLOYEE_REQUIRED = {"full_name", "department", "job_title", "hire_date", "status"}


def update_employee(db: Session, employee: Employee, **fields) -> Employee:
    """
    Apply a partial update.

    Callers pass `model_dump(exclude_unset=True)`, so a key being present means the
    client actually sent it - including an explicit null. Nulls are therefore
    applied (that is how a nullable field gets cleared), except for columns that
    cannot be null.
    """
    for key, value in fields.items():
        if not hasattr(employee, key):
            continue
        if value is None and key in _EMPLOYEE_REQUIRED:
            continue
        setattr(employee, key, value)
    db.add(employee)
    db.commit()
    db.refresh(employee)
    return employee


def list_departments(db: Session) -> List[str]:
    rows = db.query(Employee.department).distinct().all()
    return sorted({row[0] for row in rows if row[0]})


def department_attrition_rate(db: Session, department: str, *, months: int = 12) -> Optional[float]:
    """
    Share of a department that left in the trailing window.

    Peer departures are a real predictor of further departures, so this feeds the
    attrition model as a team-level signal.
    """
    if not department:
        return None
    cutoff = date.today() - timedelta(days=int(30.44 * months))

    leavers = (
        db.query(func.count(Employee.id))
        .filter(
            Employee.department == department,
            Employee.status.in_(("resigned", "terminated")),
            Employee.exit_date.isnot(None),
            Employee.exit_date >= cutoff,
        )
        .scalar()
        or 0
    )
    current = (
        db.query(func.count(Employee.id))
        .filter(Employee.department == department, Employee.status == "active")
        .scalar()
        or 0
    )
    denominator = current + leavers
    if denominator == 0:
        return None
    return round(leavers / denominator, 4)


# --------------------------------------------------------------------------
# Employee skills
# --------------------------------------------------------------------------
def add_employee_skill(
    db: Session,
    *,
    employee_id: int,
    skill: str,
    proficiency: int = 3,
    source: str = "self_reported",
    verified: bool = False,
) -> EmployeeSkill:
    """Upsert: re-adding a skill keeps the highest proficiency seen."""
    existing = (
        db.query(EmployeeSkill)
        .filter(EmployeeSkill.employee_id == employee_id, EmployeeSkill.skill == skill)
        .first()
    )
    if existing:
        existing.proficiency = max(int(existing.proficiency or 0), int(proficiency))
        existing.verified = bool(existing.verified or verified)
        existing.source = source or existing.source
        db.add(existing)
        db.commit()
        db.refresh(existing)
        return existing

    record = EmployeeSkill(
        employee_id=employee_id,
        skill=skill,
        proficiency=proficiency,
        source=source,
        verified=verified,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def list_employee_skills(db: Session, employee_id: int) -> List[EmployeeSkill]:
    return (
        db.query(EmployeeSkill)
        .filter(EmployeeSkill.employee_id == employee_id)
        .order_by(EmployeeSkill.skill.asc())
        .all()
    )


def list_all_employee_skills(db: Session) -> List[EmployeeSkill]:
    return db.query(EmployeeSkill).all()


def delete_employee_skill(db: Session, employee_id: int, skill: str) -> bool:
    record = (
        db.query(EmployeeSkill)
        .filter(EmployeeSkill.employee_id == employee_id, EmployeeSkill.skill == skill)
        .first()
    )
    if not record:
        return False
    db.delete(record)
    db.commit()
    return True


# --------------------------------------------------------------------------
# Attendance
# --------------------------------------------------------------------------
def record_attendance(db: Session, **fields) -> AttendanceRecord:
    record = AttendanceRecord(**fields)
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def bulk_record_attendance(db: Session, rows: Iterable[dict]) -> int:
    """Insert many days at once; used by the seed script and imports."""
    objects = [AttendanceRecord(**row) for row in rows]
    if not objects:
        return 0
    db.add_all(objects)
    db.commit()
    return len(objects)


def list_attendance(
    db: Session,
    employee_id: int,
    *,
    since: Optional[date] = None,
    limit: int = 400,
) -> List[AttendanceRecord]:
    query = db.query(AttendanceRecord).filter(AttendanceRecord.employee_id == employee_id)
    if since:
        query = query.filter(AttendanceRecord.work_date >= since)
    return query.order_by(AttendanceRecord.work_date.desc()).limit(limit).all()


# --------------------------------------------------------------------------
# Performance
# --------------------------------------------------------------------------
def create_review(db: Session, **fields) -> PerformanceReview:
    review = PerformanceReview(**fields)
    db.add(review)
    db.commit()
    db.refresh(review)
    return review


def list_reviews(db: Session, employee_id: int) -> List[PerformanceReview]:
    """Chronological, oldest first, so trajectory reads left to right."""
    return (
        db.query(PerformanceReview)
        .filter(PerformanceReview.employee_id == employee_id)
        .order_by(PerformanceReview.period.asc())
        .all()
    )


def department_average_rating(db: Session, department: str) -> Optional[float]:
    """
    Mean latest rating for a department, used for calibration.

    Averages every review rather than only the latest per person: with small
    departments the latest-only figure swings wildly between cycles.
    """
    if not department:
        return None
    value = (
        db.query(func.avg(PerformanceReview.rating))
        .join(Employee, Employee.id == PerformanceReview.employee_id)
        .filter(Employee.department == department, Employee.status == "active")
        .scalar()
    )
    return round(float(value), 3) if value is not None else None


def create_goal(db: Session, **fields) -> Goal:
    goal = Goal(**fields)
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return goal


def list_goals(db: Session, employee_id: int, *, period: Optional[str] = None) -> List[Goal]:
    query = db.query(Goal).filter(Goal.employee_id == employee_id)
    if period:
        query = query.filter(Goal.period == period)
    return query.order_by(Goal.due_date.asc().nullslast()).all()


_GOAL_REQUIRED = {"title", "status", "progress", "weight", "employee_id"}


def update_goal(db: Session, goal: Goal, **fields) -> Goal:
    """Partial update; explicit nulls clear nullable fields such as due_date."""
    for key, value in fields.items():
        if not hasattr(goal, key):
            continue
        if value is None and key in _GOAL_REQUIRED:
            continue
        setattr(goal, key, value)
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return goal


def get_goal(db: Session, goal_id: int) -> Optional[Goal]:
    return db.query(Goal).filter(Goal.id == goal_id).first()


def create_feedback(db: Session, **fields) -> Feedback:
    item = Feedback(**fields)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def list_feedback(db: Session, employee_id: int, *, limit: int = 100) -> List[Feedback]:
    return (
        db.query(Feedback)
        .filter(Feedback.employee_id == employee_id)
        .order_by(Feedback.given_on.desc().nullslast(), Feedback.id.desc())
        .limit(limit)
        .all()
    )


# --------------------------------------------------------------------------
# Skill requirements (demand side of the skill graph)
# --------------------------------------------------------------------------
def create_skill_requirement(db: Session, **fields) -> SkillRequirement:
    requirement = SkillRequirement(**fields)
    db.add(requirement)
    db.commit()
    db.refresh(requirement)
    return requirement


def list_skill_requirements(
    db: Session,
    *,
    horizon: Optional[str] = None,
    department: Optional[str] = None,
) -> List[SkillRequirement]:
    query = db.query(SkillRequirement)
    if horizon:
        query = query.filter(SkillRequirement.horizon == horizon)
    if department:
        query = query.filter(SkillRequirement.department == department)
    return query.order_by(SkillRequirement.skill.asc()).all()


def delete_skill_requirement(db: Session, requirement_id: int) -> bool:
    requirement = (
        db.query(SkillRequirement).filter(SkillRequirement.id == requirement_id).first()
    )
    if not requirement:
        return False
    db.delete(requirement)
    db.commit()
    return True


# --------------------------------------------------------------------------
# Policies
# --------------------------------------------------------------------------
def create_policy(db: Session, *, chunks: Sequence[tuple], **fields) -> PolicyDocument:
    """Create a policy document together with its addressable sections."""
    document = PolicyDocument(**fields)
    db.add(document)
    db.flush()  # need the id before attaching chunks

    for ordinal, (section, content) in enumerate(chunks, start=1):
        db.add(
            PolicyChunk(
                policy_document_id=document.id,
                section=section,
                content=content,
                ordinal=ordinal,
            )
        )

    db.commit()
    db.refresh(document)
    return document


def get_policy(db: Session, policy_id: int) -> Optional[PolicyDocument]:
    return db.query(PolicyDocument).filter(PolicyDocument.id == policy_id).first()


def list_policies(db: Session, *, category: Optional[str] = None) -> List[PolicyDocument]:
    query = db.query(PolicyDocument)
    if category:
        query = query.filter(PolicyDocument.category == category)
    return query.order_by(PolicyDocument.title.asc()).all()


def list_policy_chunks(db: Session) -> List[PolicyChunk]:
    return db.query(PolicyChunk).order_by(PolicyChunk.policy_document_id, PolicyChunk.ordinal).all()


def delete_policy(db: Session, policy: PolicyDocument) -> None:
    db.delete(policy)
    db.commit()


# --------------------------------------------------------------------------
# Onboarding
# --------------------------------------------------------------------------
def create_onboarding_plan(db: Session, *, tasks: Sequence[dict], **fields) -> OnboardingPlan:
    plan = OnboardingPlan(**fields)
    db.add(plan)
    db.flush()

    for task in tasks:
        db.add(OnboardingTask(plan_id=plan.id, **task))

    db.commit()
    db.refresh(plan)
    return plan


def get_onboarding_plan(db: Session, plan_id: int) -> Optional[OnboardingPlan]:
    return db.query(OnboardingPlan).filter(OnboardingPlan.id == plan_id).first()


def latest_onboarding_plan(db: Session, employee_id: int) -> Optional[OnboardingPlan]:
    return (
        db.query(OnboardingPlan)
        .filter(OnboardingPlan.employee_id == employee_id)
        .order_by(OnboardingPlan.created_at.desc())
        .first()
    )


def list_onboarding_plans(db: Session, *, status: Optional[str] = None) -> List[OnboardingPlan]:
    query = db.query(OnboardingPlan)
    if status:
        query = query.filter(OnboardingPlan.status == status)
    return query.order_by(OnboardingPlan.created_at.desc()).all()


def get_onboarding_task(db: Session, task_id: int) -> Optional[OnboardingTask]:
    return db.query(OnboardingTask).filter(OnboardingTask.id == task_id).first()


_TASK_REQUIRED = {"title", "phase", "category", "day_offset", "mandatory", "status"}


def update_onboarding_task(db: Session, task: OnboardingTask, **fields) -> OnboardingTask:
    """Partial update; clearing completed_on (null) reopens a task."""
    for key, value in fields.items():
        if not hasattr(task, key):
            continue
        if value is None and key in _TASK_REQUIRED:
            continue
        setattr(task, key, value)
    db.add(task)
    db.commit()
    db.refresh(task)
    return task
