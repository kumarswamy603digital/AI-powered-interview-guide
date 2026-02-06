from __future__ import annotations

from fastapi import APIRouter

from app.core.ats import score_resume
from app.schemas.ats import AtsScoreRequest, AtsScoreResponse


router = APIRouter(prefix="/api/ats", tags=["ats"])


@router.post("/score", response_model=AtsScoreResponse)
def score_ats(payload: AtsScoreRequest) -> AtsScoreResponse:
    """
    Compute ATS scores for a resume against a job role.

    Uses Gemini when GEMINI_API_KEY is configured; otherwise falls back
    to a deterministic heuristic-based scorer.
    """
    result = score_resume(resume_text=payload.resume_text, job_role=payload.job_role)
    return AtsScoreResponse(
        keyword_match_score=result.keyword_match_score,
        formatting_score=result.formatting_score,
        final_score=result.final_score,
    )

