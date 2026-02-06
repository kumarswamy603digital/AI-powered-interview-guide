from __future__ import annotations

from fastapi import APIRouter

from app.core.answer_evaluation import evaluate_answer
from app.schemas.answer_evaluation import (
    AnswerEvaluationRequest,
    AnswerEvaluationResponse,
)


router = APIRouter(prefix="/api/answers", tags=["answers"])


@router.post("/evaluate", response_model=AnswerEvaluationResponse)
def evaluate(payload: AnswerEvaluationRequest) -> AnswerEvaluationResponse:
    """
    Evaluate an interview answer for relevance, depth, clarity, and confidence.

    Uses Gemini when configured; otherwise falls back to a heuristic scorer.
    """
    return evaluate_answer(
        question=payload.question,
        answer=payload.answer,
        target_role=payload.target_role,
    )

