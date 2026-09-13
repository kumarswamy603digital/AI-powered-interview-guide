from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field, model_validator


class AtsScoreRequest(BaseModel):
    """
    Score a resume against a role.

    Provide exactly one source of resume text: pasted text, a stored resume, or a
    candidate (whose latest parsed resume is used).
    """

    job_role: str = Field(..., min_length=2)
    resume_text: Optional[str] = Field(default=None, min_length=50)
    resume_id: Optional[int] = None
    candidate_id: Optional[int] = None
    # Score against a requisition's requirements rather than a free-text role.
    job_requisition_id: Optional[int] = None

    @model_validator(mode="after")
    def _require_one_source(self) -> "AtsScoreRequest":
        provided = [
            self.resume_text is not None,
            self.resume_id is not None,
            self.candidate_id is not None,
        ]
        if not any(provided):
            raise ValueError(
                "Provide resume_text, resume_id or candidate_id as the resume source."
            )
        return self


class AtsScoreResponse(BaseModel):
    keyword_match_score: float
    formatting_score: float
    final_score: float
    # Populated when scoring against a requisition.
    matched_skills: List[str] = Field(default_factory=list)
    missing_skills: List[str] = Field(default_factory=list)
    resume_id: Optional[int] = None
    candidate_id: Optional[int] = None
