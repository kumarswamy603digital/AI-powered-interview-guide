from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.skills import canonical_skill


CandidateStage = Literal["applied", "screened", "interviewed", "recommended", "rejected", "hired"]
JobStatus = Literal["open", "on_hold", "closed"]
RecommendationLiteral = Literal[
    "recommend_hire",
    "advance_to_interview",
    "further_assessment",
    "reject",
]


def _clean_skills(value: Optional[List[str]]) -> List[str]:
    """Canonicalise and de-duplicate a skill list, preserving order."""
    result: List[str] = []
    for raw in value or []:
        skill = canonical_skill(raw)
        if skill and skill not in result:
            result.append(skill)
    return result


# --------------------------------------------------------------------------
# Job requisitions
# --------------------------------------------------------------------------
class JobRequisitionBase(BaseModel):
    title: str = Field(..., min_length=2, max_length=255)
    department: Optional[str] = Field(default=None, max_length=128)
    seniority: Optional[str] = Field(default=None, max_length=64)
    location: Optional[str] = Field(default=None, max_length=128)
    employment_type: Optional[str] = Field(default=None, max_length=64)
    description: Optional[str] = None
    required_skills: List[str] = Field(default_factory=list)
    preferred_skills: List[str] = Field(default_factory=list)
    min_years_experience: Optional[float] = Field(default=None, ge=0, le=50)
    headcount: int = Field(default=1, ge=1, le=1000)

    @field_validator("required_skills", "preferred_skills", mode="after")
    @classmethod
    def _canonicalise(cls, value: List[str]) -> List[str]:
        return _clean_skills(value)


class JobRequisitionCreate(JobRequisitionBase):
    pass


class JobRequisitionUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=2, max_length=255)
    department: Optional[str] = None
    seniority: Optional[str] = None
    location: Optional[str] = None
    employment_type: Optional[str] = None
    description: Optional[str] = None
    required_skills: Optional[List[str]] = None
    preferred_skills: Optional[List[str]] = None
    min_years_experience: Optional[float] = Field(default=None, ge=0, le=50)
    headcount: Optional[int] = Field(default=None, ge=1, le=1000)
    status: Optional[JobStatus] = None

    @field_validator("required_skills", "preferred_skills", mode="after")
    @classmethod
    def _canonicalise(cls, value: Optional[List[str]]) -> Optional[List[str]]:
        return None if value is None else _clean_skills(value)


class JobRequisitionRead(JobRequisitionBase):
    id: int
    status: JobStatus
    created_by_user_id: Optional[int] = None
    candidate_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# --------------------------------------------------------------------------
# Candidates
# --------------------------------------------------------------------------
class CandidateBase(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=255)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(default=None, max_length=64)
    current_title: Optional[str] = Field(default=None, max_length=255)
    years_experience: Optional[float] = Field(default=None, ge=0, le=60)
    source: Optional[str] = Field(default=None, max_length=128)
    job_requisition_id: Optional[int] = None
    notes: Optional[str] = None


class CandidateCreate(CandidateBase):
    pass


class CandidateUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    current_title: Optional[str] = None
    years_experience: Optional[float] = Field(default=None, ge=0, le=60)
    source: Optional[str] = None
    job_requisition_id: Optional[int] = None
    stage: Optional[CandidateStage] = None
    notes: Optional[str] = None


class CandidateRead(CandidateBase):
    id: int
    stage: CandidateStage
    created_by_user_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    # Derived, not stored.
    has_resume_text: bool = False
    extracted_skills: List[str] = Field(default_factory=list)
    interviews_completed: int = 0
    latest_interview_score: Optional[float] = None

    model_config = {"from_attributes": True}


# --------------------------------------------------------------------------
# Ranking / candidate intelligence
# --------------------------------------------------------------------------
class ScoreComponentRead(BaseModel):
    name: str
    score: float
    weight: float
    detail: str


class CandidateRankingRead(BaseModel):
    candidate_id: Optional[int]
    full_name: str
    stage: str
    final_score: float
    skill_match_score: float
    experience_match_score: Optional[float] = None
    interview_score: Optional[float] = None
    preferred_skill_score: Optional[float] = None
    matched_skills: List[str]
    missing_skills: List[str]
    matched_preferred_skills: List[str]
    additional_skills: List[str]
    recommendation: RecommendationLiteral
    confidence: Literal["high", "medium", "low"]
    reasoning: List[str]
    flags: List[str]
    data_sources: List[str]
    components: List[ScoreComponentRead]
    interview_session_id: Optional[int] = None


class RankRequest(BaseModel):
    job_requisition_id: int
    # Restrict to specific candidates; defaults to everyone attached to the job.
    candidate_ids: Optional[List[int]] = None
    include_unassigned: bool = Field(
        default=False,
        description="Also rank candidates not yet attached to any requisition.",
    )
    limit: int = Field(default=50, ge=1, le=500)


class SkillGapRead(BaseModel):
    skill: str
    candidates_missing: int


class RankResponse(BaseModel):
    job_requisition_id: int
    job_title: str
    required_skills: List[str]
    candidates_evaluated: int
    rankings: List[CandidateRankingRead]
    skill_gaps: List[SkillGapRead]
    warnings: List[str] = Field(default_factory=list)


class InterviewSummaryRead(BaseModel):
    id: int
    target_role: str
    status: str
    overall_score: Optional[float] = None
    skill_scores: Dict[str, float] = Field(default_factory=dict)
    summary: Optional[str] = None
    started_at: datetime
    ended_at: Optional[datetime] = None


class CandidateProfileRead(BaseModel):
    """Everything known about one candidate, from every source."""

    candidate: CandidateRead
    resume_skills: List[str]
    resume_extraction_status: Optional[str] = None
    resume_extraction_detail: Optional[str] = None
    interviews: List[InterviewSummaryRead]
    ranking: Optional[CandidateRankingRead] = None


# --------------------------------------------------------------------------
# HR dashboard
# --------------------------------------------------------------------------
class PipelineCounts(BaseModel):
    applied: int = 0
    screened: int = 0
    interviewed: int = 0
    recommended: int = 0
    rejected: int = 0
    hired: int = 0


class HrDashboardRead(BaseModel):
    open_jobs: int
    total_candidates: int
    interviews_completed: int
    candidates_awaiting_interview: int
    candidates_missing_resume_text: int
    pipeline: PipelineCounts
    top_skill_gaps: List[SkillGapRead]
    recommendation_counts: Dict[str, int]
    insights: List[str]
