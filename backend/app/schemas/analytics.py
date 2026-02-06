from __future__ import annotations

from datetime import datetime
from typing import List

from pydantic import BaseModel, Field


class InterviewHistoryItem(BaseModel):
    id: int
    target_role: str
    difficulty: str
    personality_mode: str
    status: str
    started_at: datetime
    ended_at: datetime | None = None
    total_turns: int


class SkillProgressItem(BaseModel):
    skill_name: str
    average_score: float = Field(..., ge=0, le=100)
    latest_score: float = Field(..., ge=0, le=100)
    trend: str  # "up" | "down" | "flat"


class PerformanceTrendPoint(BaseModel):
    interview_id: int
    date: datetime
    average_skill_score: float = Field(..., ge=0, le=100)


class InterviewHistoryResponse(BaseModel):
    items: List[InterviewHistoryItem]


class SkillProgressResponse(BaseModel):
    items: List[SkillProgressItem]


class PerformanceTrendsResponse(BaseModel):
    points: List[PerformanceTrendPoint]

