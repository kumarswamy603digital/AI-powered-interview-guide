from __future__ import annotations

from fastapi import APIRouter

from app.core.interview_plan import generate_interview_plan
from app.schemas.interview_plan import InterviewPlanRequest, InterviewPlanResponse


router = APIRouter(prefix="/api/interviews", tags=["interviews"])


@router.post("/plan/generate", response_model=InterviewPlanResponse)
def generate_plan(payload: InterviewPlanRequest) -> InterviewPlanResponse:
    """
    Generate an interview plan from resume text, target role, and difficulty.

    Uses Gemini when GEMINI_API_KEY is configured; otherwise falls back to a mock plan.
    """
    return generate_interview_plan(
        resume_text=payload.resume_text,
        target_role=payload.target_role,
        difficulty=payload.difficulty,
    )

