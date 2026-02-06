from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


Difficulty = Literal["easy", "medium", "hard"]


class InterviewPlanRequest(BaseModel):
    resume_text: str = Field(..., min_length=50)
    target_role: str = Field(..., min_length=2)
    difficulty: Difficulty = "medium"


class InterviewRound(BaseModel):
    round_name: str
    duration_minutes: int = Field(..., ge=5, le=180)
    objectives: list[str] = Field(default_factory=list)
    evaluation_signals: list[str] = Field(default_factory=list)


class QuestionCategory(BaseModel):
    category: str
    percentage: int = Field(..., ge=0, le=100)
    example_questions: list[str] = Field(default_factory=list)


class TimeBlock(BaseModel):
    segment: str
    minutes: int = Field(..., ge=0, le=240)


class InterviewPlanResponse(BaseModel):
    interview_structure: list[InterviewRound]
    question_categories: list[QuestionCategory]
    time_allocation: list[TimeBlock]

