from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


PersonalityMode = Literal["strict", "friendly", "stress"]
Difficulty = Literal["easy", "medium", "hard"]


class LiveInterviewStartRequest(BaseModel):
    resume_text: str = Field(..., min_length=50)
    target_role: str = Field(..., min_length=2)
    difficulty: Difficulty = "medium"
    personality_mode: PersonalityMode = "friendly"
    max_questions: int = Field(default=8, ge=1, le=25)


class LiveInterviewStartResponse(BaseModel):
    id: int
    first_question: str
    question_index: int


class LiveInterviewSubmitRequest(BaseModel):
    answer: str = Field(..., min_length=1, max_length=20000)


class LiveInterviewSubmitResponse(BaseModel):
    id: int
    next_question: str
    question_index: int
    is_follow_up: bool


class LiveInterviewEndResponse(BaseModel):
    id: int
    status: str
    total_turns: int
    ended_at: Optional[str] = None

