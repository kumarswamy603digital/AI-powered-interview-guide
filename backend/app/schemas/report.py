from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class SkillScore(BaseModel):
    name: str
    score: float = Field(..., ge=0, le=100)
    comment: Optional[str] = None


class ReportSection(BaseModel):
    title: str
    content: str


class InterviewReport(BaseModel):
    interview_id: int
    target_role: str
    difficulty: str
    personality_mode: str
    skill_breakdown: List[SkillScore]
    strengths: List[str]
    weaknesses: List[str]
    improvement_tips: List[str]
    summary: Optional[str] = None

