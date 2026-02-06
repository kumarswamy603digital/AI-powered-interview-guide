from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class AnswerEvaluationRequest(BaseModel):
    question: str = Field(..., min_length=5)
    answer: str = Field(..., min_length=1)
    target_role: Optional[str] = None


class AnswerEvaluationMetrics(BaseModel):
    relevance: float = Field(..., ge=0, le=100)
    depth: float = Field(..., ge=0, le=100)
    clarity: float = Field(..., ge=0, le=100)
    confidence: float = Field(..., ge=0, le=100)
    overall_score: float = Field(..., ge=0, le=100)


class AnswerEvaluationResponse(AnswerEvaluationMetrics):
    feedback: Optional[str] = None

