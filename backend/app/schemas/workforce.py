from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.skills import canonical_skill


def _as_str_list(value: Any) -> List[str]:
    """
    Coerce a value read off an ORM row into a list of strings.

    Two cases this has to survive:
      * a nullable JSON column that is NULL (rows created without the field) -
        pydantic rejects None for List[str];
      * an ORM *relationship* whose attribute name matches the schema field, so
        the raw value is a list of model instances rather than strings.
    """
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    result: List[str] = []
    for item in value:
        if isinstance(item, str):
            result.append(item)
            continue
        # EmployeeSkill -> its skill name; anything else falls back to str().
        name = getattr(item, "skill", None) or getattr(item, "name", None)
        result.append(str(name) if name is not None else str(item))
    return result


EmployeeStatus = Literal["active", "on_leave", "notice_period", "resigned", "terminated"]
AttendanceStatus = Literal["present", "remote", "leave", "absent", "holiday"]
GoalStatus = Literal["not_started", "on_track", "at_risk", "missed", "achieved"]
FeedbackSource = Literal["manager", "peer", "self", "skip_level", "customer"]
SkillImportance = Literal["core", "important", "nice_to_have"]
SkillHorizon = Literal["current", "future"]
RiskBand = Literal["low", "moderate", "high", "critical"]
Confidence = Literal["high", "medium", "low"]


# --------------------------------------------------------------------------
# Employees
# --------------------------------------------------------------------------
class EmployeeBase(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=255)
    email: Optional[EmailStr] = None
    department: str = Field(..., min_length=1, max_length=128)
    job_title: str = Field(..., min_length=2, max_length=255)
    seniority: Optional[str] = Field(default=None, max_length=64)
    location: Optional[str] = Field(default=None, max_length=128)
    employment_type: Optional[str] = Field(default=None, max_length=64)
    work_mode: Optional[str] = Field(default=None, max_length=32)
    manager_id: Optional[int] = None
    hire_date: date
    last_promotion_date: Optional[date] = None
    compa_ratio: Optional[float] = Field(default=None, ge=0.3, le=2.5)
    engagement_score: Optional[float] = Field(default=None, ge=0, le=100)
    employee_code: Optional[str] = Field(default=None, max_length=32)
    notes: Optional[str] = None


class EmployeeCreate(EmployeeBase):
    pass


class EmployeeUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    email: Optional[EmailStr] = None
    department: Optional[str] = None
    job_title: Optional[str] = None
    seniority: Optional[str] = None
    location: Optional[str] = None
    employment_type: Optional[str] = None
    work_mode: Optional[str] = None
    manager_id: Optional[int] = None
    last_promotion_date: Optional[date] = None
    exit_date: Optional[date] = None
    compa_ratio: Optional[float] = Field(default=None, ge=0.3, le=2.5)
    engagement_score: Optional[float] = Field(default=None, ge=0, le=100)
    status: Optional[EmployeeStatus] = None
    notes: Optional[str] = None


class EmployeeRead(EmployeeBase):
    id: int
    status: EmployeeStatus
    exit_date: Optional[date] = None
    source_candidate_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    # Derived, not stored.
    tenure_years: Optional[float] = None
    manager_name: Optional[str] = None
    # NOTE: this name matches the Employee.skills relationship, so validating
    # straight off an ORM row yields EmployeeSkill instances. The validator below
    # flattens them to names; without it every employee read raised a
    # ValidationError.
    skills: List[str] = Field(default_factory=list)
    direct_report_count: int = 0

    model_config = {"from_attributes": True}

    @field_validator("skills", mode="before")
    @classmethod
    def _flatten_skills(cls, value: Any) -> List[str]:
        return _as_str_list(value)


class EmployeeFromCandidate(BaseModel):
    """Convert a hired candidate into an employee, carrying their skills over."""

    candidate_id: int
    department: str = Field(..., min_length=1)
    job_title: str = Field(..., min_length=2)
    hire_date: date
    seniority: Optional[str] = None
    manager_id: Optional[int] = None
    location: Optional[str] = None
    work_mode: Optional[str] = None
    employment_type: Optional[str] = "full_time"
    compa_ratio: Optional[float] = Field(default=None, ge=0.3, le=2.5)
    generate_onboarding_plan: bool = True


# --------------------------------------------------------------------------
# Employee skills
# --------------------------------------------------------------------------
class EmployeeSkillCreate(BaseModel):
    skill: str = Field(..., min_length=1, max_length=128)
    proficiency: int = Field(default=3, ge=1, le=5)
    source: str = Field(default="self_reported", max_length=32)
    verified: bool = False

    @field_validator("skill", mode="after")
    @classmethod
    def _canonicalise(cls, value: str) -> str:
        return canonical_skill(value) or value


class EmployeeSkillRead(BaseModel):
    id: int
    employee_id: int
    skill: str
    proficiency: int
    source: str
    verified: bool
    last_used_on: Optional[date] = None

    model_config = {"from_attributes": True}


# --------------------------------------------------------------------------
# Attendance
# --------------------------------------------------------------------------
class AttendanceCreate(BaseModel):
    employee_id: int
    work_date: date
    status: AttendanceStatus = "present"
    hours_worked: Optional[float] = Field(default=None, ge=0, le=24)
    overtime_hours: float = Field(default=0.0, ge=0, le=16)
    late_arrival: bool = False


class AttendanceBulkCreate(BaseModel):
    records: List[AttendanceCreate] = Field(..., min_length=1, max_length=5000)


class AttendanceRead(AttendanceCreate):
    id: int

    model_config = {"from_attributes": True}


class AttendanceSummaryRead(BaseModel):
    employee_id: int
    window_days: int
    days_recorded: int
    unplanned_absence_rate: Optional[float] = None
    late_arrival_rate: Optional[float] = None
    average_weekly_overtime: Optional[float] = None
    note: str


# --------------------------------------------------------------------------
# Performance
# --------------------------------------------------------------------------
class ReviewCreate(BaseModel):
    employee_id: int
    period: str = Field(..., min_length=2, max_length=32)
    rating: float = Field(..., ge=1, le=5)
    potential_rating: Optional[float] = Field(default=None, ge=1, le=5)
    reviewer_id: Optional[int] = None
    review_date: Optional[date] = None
    strengths: List[str] = Field(default_factory=list)
    improvements: List[str] = Field(default_factory=list)
    comments: Optional[str] = None
    promotion_ready: Optional[Literal["yes", "not_yet", "no"]] = None

    @field_validator("strengths", "improvements", mode="before")
    @classmethod
    def _null_json_to_list(cls, value: Any) -> List[str]:
        # These are nullable JSON columns; NULL must read as an empty list.
        return _as_str_list(value)


class ReviewRead(ReviewCreate):
    id: int

    model_config = {"from_attributes": True}


class GoalCreate(BaseModel):
    employee_id: int
    title: str = Field(..., min_length=2, max_length=255)
    description: Optional[str] = None
    period: Optional[str] = Field(default=None, max_length=32)
    status: GoalStatus = "not_started"
    progress: float = Field(default=0.0, ge=0, le=100)
    weight: float = Field(default=1.0, gt=0, le=10)
    due_date: Optional[date] = None
    related_skills: List[str] = Field(default_factory=list)

    @field_validator("related_skills", mode="before")
    @classmethod
    def _null_related_skills_to_list(cls, value: Any) -> List[str]:
        # Nullable JSON column: goals created without related skills read as NULL.
        return _as_str_list(value)


class GoalUpdate(BaseModel):
    title: Optional[str] = None
    status: Optional[GoalStatus] = None
    progress: Optional[float] = Field(default=None, ge=0, le=100)
    weight: Optional[float] = Field(default=None, gt=0, le=10)
    due_date: Optional[date] = None


class GoalRead(GoalCreate):
    id: int

    model_config = {"from_attributes": True}


class FeedbackCreate(BaseModel):
    employee_id: int
    source: FeedbackSource = "peer"
    content: str = Field(..., min_length=3)
    author_id: Optional[int] = None
    sentiment: Optional[float] = Field(default=None, ge=-1, le=1)
    given_on: Optional[date] = None


class FeedbackRead(FeedbackCreate):
    id: int
    # Inferred by the lexicon when the payload did not supply one.
    inferred_sentiment: Optional[float] = None

    model_config = {"from_attributes": True}


# --------------------------------------------------------------------------
# Skill requirements
# --------------------------------------------------------------------------
class SkillRequirementCreate(BaseModel):
    skill: str = Field(..., min_length=1, max_length=128)
    department: Optional[str] = Field(default=None, max_length=128)
    role: Optional[str] = Field(default=None, max_length=255)
    importance: SkillImportance = "important"
    horizon: SkillHorizon = "current"
    required_headcount: int = Field(default=1, ge=1, le=1000)
    required_proficiency: int = Field(default=3, ge=1, le=5)
    target_date: Optional[date] = None
    rationale: Optional[str] = None

    @field_validator("skill", mode="after")
    @classmethod
    def _canonicalise(cls, value: str) -> str:
        return canonical_skill(value) or value


class SkillRequirementRead(SkillRequirementCreate):
    id: int

    model_config = {"from_attributes": True}


# --------------------------------------------------------------------------
# Attrition
# --------------------------------------------------------------------------
class RiskFactorRead(BaseModel):
    name: str
    label: str
    risk: float
    weight: float
    contribution: float
    evidence: str


class RetentionActionRead(BaseModel):
    action: str
    rationale: str
    expected_risk_reduction: float
    priority: Literal["high", "medium", "low"]
    owner: str


class AttritionAssessmentRead(BaseModel):
    employee_id: Optional[int] = None
    full_name: str
    department: str
    job_title: str
    risk_score: float
    risk_band: RiskBand
    confidence: Confidence
    factors: List[RiskFactorRead]
    protective_factors: List[RiskFactorRead]
    recommended_actions: List[RetentionActionRead]
    signals_available: int
    signals_total: int
    summary: str


class AttritionOverviewRead(BaseModel):
    employees_assessed: int
    average_risk: float
    band_distribution: Dict[str, int]
    high_risk_count: int
    by_department: List[Dict[str, Any]]
    top_drivers: List[Dict[str, Any]]
    assessments: List[AttritionAssessmentRead] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Performance intelligence
# --------------------------------------------------------------------------
class ThemeInsightRead(BaseModel):
    theme: str
    sentiment: float
    mentions: int
    sources: List[str]
    evidence: List[str]


class GoalSummaryRead(BaseModel):
    total: int
    achieved: int
    on_track: int
    at_risk: int
    missed: int
    not_started: int
    weighted_attainment: float


class PerformanceActionRead(BaseModel):
    action: str
    rationale: str
    owner: str
    priority: Literal["high", "medium", "low"]


class PerformanceInsightRead(BaseModel):
    employee_id: Optional[int] = None
    full_name: str
    department: str
    job_title: str
    overall_score: float
    latest_rating: Optional[float] = None
    rating_trajectory: Literal["improving", "steady", "declining", "unknown"]
    rating_delta: Optional[float] = None
    goal_summary: GoalSummaryRead
    calibration: Optional[str] = None
    calibration_delta: Optional[float] = None
    strengths: List[ThemeInsightRead]
    improvement_areas: List[ThemeInsightRead]
    feedback_sentiment: Optional[float] = None
    promotion_readiness: Literal["ready", "developing", "not_yet", "unknown"]
    recommended_actions: List[PerformanceActionRead]
    summary: str
    data_sources: List[str]


# --------------------------------------------------------------------------
# Skill graph
# --------------------------------------------------------------------------
class ReskillCandidateRead(BaseModel):
    employee_id: Optional[int] = None
    full_name: str
    department: str
    affinity: float
    adjacent_skills_held: List[str]
    reason: str


class SkillNodeRead(BaseModel):
    skill: str
    category: Optional[str] = None
    total_holders: int
    qualified_holders: int
    average_proficiency: Optional[float] = None
    verified_holders: int
    demand_current: int
    demand_future: int
    importance: Optional[str] = None
    coverage_current: Optional[float] = None
    coverage_future: Optional[float] = None
    gap_current: int
    gap_future: int
    status: str
    single_point_of_failure: bool
    hot_market_skill: bool
    holders: List[str]
    departments: List[str]
    demand_departments: List[str] = Field(default_factory=list)
    reskilling_candidates: List[ReskillCandidateRead]
    recommended_action: Optional[str] = None
    rationale: Optional[str] = None


class SkillGraphRead(BaseModel):
    nodes: List[SkillNodeRead]
    edges: List[Dict[str, Any]]
    summary: Dict[str, Any]


# --------------------------------------------------------------------------
# Employee 360
# --------------------------------------------------------------------------
class Employee360Read(BaseModel):
    """Everything known about one employee, from every source."""

    employee: EmployeeRead
    skills: List[EmployeeSkillRead]
    attendance: AttendanceSummaryRead
    performance: PerformanceInsightRead
    attrition: AttritionAssessmentRead
    reviews: List[ReviewRead]
    goals: List[GoalRead]
    feedback: List[FeedbackRead]
    onboarding_progress: Optional[Dict[str, Any]] = None
    skill_gaps_for_role: List[str] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Decision dashboard
# --------------------------------------------------------------------------
class CrossSourceInsightRead(BaseModel):
    title: str
    severity: Literal["critical", "warning", "opportunity", "info"]
    detail: str
    recommended_action: str
    sources: List[str]
    entities: List[str] = Field(default_factory=list)


class DecisionDashboardRead(BaseModel):
    headline: Dict[str, Any]
    recruitment: Dict[str, Any]
    workforce_risk: Dict[str, Any]
    performance: Dict[str, Any]
    attendance: Dict[str, Any]
    skills: Dict[str, Any]
    onboarding: Dict[str, Any]
    insights: List[CrossSourceInsightRead]
    data_sources: List[str]
