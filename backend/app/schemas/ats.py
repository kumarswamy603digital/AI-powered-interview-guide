from __future__ import annotations

from pydantic import BaseModel, Field


class AtsScoreRequest(BaseModel):
    resume_text: str = Field(..., min_length=50)
    job_role: str = Field(..., min_length=2)


class AtsScoreResponse(BaseModel):
    keyword_match_score: float
    formatting_score: float
    final_score: float

