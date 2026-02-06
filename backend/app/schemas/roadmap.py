from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class RoadmapSkill(BaseModel):
    name: str
    current_level: str = Field(default="unknown")
    target_level: str = Field(default="proficient")
    resources: List[str] = Field(default_factory=list)
    estimated_weeks: int = Field(..., ge=1, le=104)


class RoadmapPhase(BaseModel):
    name: str
    duration_weeks: int = Field(..., ge=1, le=104)
    focus_areas: List[str] = Field(default_factory=list)


class CareerRoadmap(BaseModel):
    interview_id: int
    target_role: str
    skills_to_learn: List[RoadmapSkill]
    timeline: List[RoadmapPhase]

