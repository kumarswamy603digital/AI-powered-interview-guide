from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


Phase = Literal["pre_boarding", "week_1", "day_30", "day_60", "day_90"]
TaskStatus = Literal["pending", "in_progress", "done", "skipped"]


class OnboardingTaskRead(BaseModel):
    id: Optional[int] = None
    title: str
    description: Optional[str] = None
    phase: str
    category: str
    day_offset: int
    owner: Optional[str] = None
    mandatory: bool
    status: str = "pending"
    # Why this task is in this person's plan.
    rationale: Optional[str] = None
    resource_url: Optional[str] = None
    completed_on: Optional[date] = None
    due_date: Optional[date] = None

    model_config = {"from_attributes": True}


class OnboardingPhaseRead(BaseModel):
    phase: str
    label: str
    day_from: int
    day_to: int
    tasks: List[OnboardingTaskRead]


class OnboardingJourneyRead(BaseModel):
    """A generated (not yet persisted) journey."""

    employee_id: Optional[int] = None
    full_name: str
    role: str
    department: str
    seniority: Optional[str] = None
    work_mode: Optional[str] = None
    buddy_name: Optional[str] = None
    targeted_skill_gaps: List[str]
    personalization_notes: List[str]
    phases: List[OnboardingPhaseRead]
    tasks: List[OnboardingTaskRead]
    mandatory_count: int
    summary: str


class OnboardingGenerateRequest(BaseModel):
    employee_id: int
    # Defaults to the requirements for the employee's role or department.
    role_required_skills: Optional[List[str]] = None
    buddy_id: Optional[int] = None
    persist: bool = Field(
        default=True,
        description="Store the plan so progress can be tracked; false previews it only.",
    )


class OnboardingPlanRead(BaseModel):
    id: int
    employee_id: int
    employee_name: Optional[str] = None
    role: Optional[str] = None
    department: Optional[str] = None
    seniority: Optional[str] = None
    work_mode: Optional[str] = None
    buddy_id: Optional[int] = None
    buddy_name: Optional[str] = None
    start_date: Optional[date] = None
    status: str
    summary: Optional[str] = None
    targeted_skill_gaps: List[str] = Field(default_factory=list)
    tasks: List[OnboardingTaskRead] = Field(default_factory=list)
    progress: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    model_config = {"from_attributes": True}


class OnboardingTaskUpdate(BaseModel):
    status: TaskStatus
    completed_on: Optional[date] = None
