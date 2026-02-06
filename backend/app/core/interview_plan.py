from __future__ import annotations

import json
from typing import Any, Optional

from app.core.config import settings
from app.schemas.interview_plan import (
    Difficulty,
    InterviewPlanResponse,
    InterviewRound,
    QuestionCategory,
    TimeBlock,
)


try:  # Optional dependency for Gemini
    import google.generativeai as genai
except Exception:  # pragma: no cover - optional
    genai = None  # type: ignore[assignment]


def _extract_json(text: str) -> str:
    """
    Best-effort extraction of a JSON object from a model response.
    Handles common cases like code fences or leading/trailing commentary.
    """
    if not text:
        raise ValueError("Empty response")
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found")
    return text[start : end + 1]


def _gemini_model():
    if not settings.GEMINI_API_KEY or genai is None:
        return None
    genai.configure(api_key=settings.GEMINI_API_KEY)
    return genai.GenerativeModel(settings.GEMINI_MODEL)


def _mock_plan(target_role: str, difficulty: Difficulty) -> InterviewPlanResponse:
    if difficulty == "easy":
        rounds = [
            InterviewRound(
                round_name="Intro + Resume walkthrough",
                duration_minutes=10,
                objectives=["Build rapport", "Understand background alignment"],
                evaluation_signals=["Clear communication", "Relevant experience highlights"],
            ),
            InterviewRound(
                round_name="Core fundamentals",
                duration_minutes=25,
                objectives=["Assess baseline knowledge for the role"],
                evaluation_signals=["Accurate concepts", "Good trade-off reasoning"],
            ),
            InterviewRound(
                round_name="Light practical / scenario questions",
                duration_minutes=20,
                objectives=["Evaluate problem solving with guidance"],
                evaluation_signals=["Structured thinking", "Correctness over optimization"],
            ),
            InterviewRound(
                round_name="Wrap-up",
                duration_minutes=5,
                objectives=["Candidate questions", "Next steps"],
                evaluation_signals=["Curiosity", "Role understanding"],
            ),
        ]
        categories = [
            QuestionCategory(category="Role fundamentals", percentage=40),
            QuestionCategory(category="Behavioral", percentage=25),
            QuestionCategory(category="Scenario-based", percentage=25),
            QuestionCategory(category="Company/role fit", percentage=10),
        ]
    elif difficulty == "hard":
        rounds = [
            InterviewRound(
                round_name="Deep resume drill-down",
                duration_minutes=15,
                objectives=["Validate claims", "Probe impact and ownership"],
                evaluation_signals=["Specificity", "Depth", "Accountability"],
            ),
            InterviewRound(
                round_name="System design",
                duration_minutes=35,
                objectives=["Design scalable solution", "Trade-offs and constraints"],
                evaluation_signals=["Clear architecture", "Bottleneck identification", "Security & reliability thinking"],
            ),
            InterviewRound(
                round_name="Coding / debugging",
                duration_minutes=30,
                objectives=["Implement or debug under pressure"],
                evaluation_signals=["Correctness", "Testing mindset", "Edge cases"],
            ),
            InterviewRound(
                round_name="Behavioral (seniority)",
                duration_minutes=20,
                objectives=["Leadership, conflict, ownership"],
                evaluation_signals=["Decision making", "Stakeholder management"],
            ),
            InterviewRound(
                round_name="Wrap-up",
                duration_minutes=5,
                objectives=["Candidate questions", "Calibration"],
                evaluation_signals=["Strategic questions", "Clarity on expectations"],
            ),
        ]
        categories = [
            QuestionCategory(category="System design", percentage=35),
            QuestionCategory(category="Coding / debugging", percentage=30),
            QuestionCategory(category="Behavioral (leadership)", percentage=20),
            QuestionCategory(category="Role-specific fundamentals", percentage=15),
        ]
    else:  # medium
        rounds = [
            InterviewRound(
                round_name="Intro + Resume walkthrough",
                duration_minutes=10,
                objectives=["Context setting", "Relevant highlights"],
                evaluation_signals=["Concise storytelling", "Clear scope/impact"],
            ),
            InterviewRound(
                round_name="Role fundamentals",
                duration_minutes=25,
                objectives=["Validate core skills for the role"],
                evaluation_signals=["Correct concepts", "Trade-offs"],
            ),
            InterviewRound(
                round_name="Practical problem solving",
                duration_minutes=25,
                objectives=["Applied reasoning and implementation thinking"],
                evaluation_signals=["Structured approach", "Edge-case awareness"],
            ),
            InterviewRound(
                round_name="Behavioral",
                duration_minutes=15,
                objectives=["Collaboration, ownership, communication"],
                evaluation_signals=["Reflection", "Accountability", "Clarity"],
            ),
            InterviewRound(
                round_name="Wrap-up",
                duration_minutes=5,
                objectives=["Candidate questions", "Next steps"],
                evaluation_signals=["Curiosity", "Role understanding"],
            ),
        ]
        categories = [
            QuestionCategory(category="Role fundamentals", percentage=30),
            QuestionCategory(category="Practical / scenario-based", percentage=30),
            QuestionCategory(category="Behavioral", percentage=25),
            QuestionCategory(category="Role-specific depth", percentage=15),
        ]

    total = sum(r.duration_minutes for r in rounds)
    time_allocation = [TimeBlock(segment=r.round_name, minutes=r.duration_minutes) for r in rounds]
    # Include a short note-like segment label? Requirement doesn’t ask, so keep minimal.
    _ = target_role  # reserved for future tailoring in mock output

    # Ensure percentages sum to 100 by adjusting the last item if needed
    pct_sum = sum(c.percentage for c in categories)
    if categories and pct_sum != 100:
        categories[-1].percentage = max(0, min(100, categories[-1].percentage + (100 - pct_sum)))

    # If total is unexpectedly > 120, caller can change. Keep as-is for now.
    _ = total

    return InterviewPlanResponse(
        interview_structure=rounds,
        question_categories=categories,
        time_allocation=time_allocation,
    )


def generate_interview_plan(
    *,
    resume_text: str,
    target_role: str,
    difficulty: Difficulty,
) -> InterviewPlanResponse:
    """
    Generate an AI-powered interview plan. Uses Gemini if configured; otherwise returns
    a deterministic mock plan.
    """
    model = _gemini_model()
    if model is None:
        return _mock_plan(target_role=target_role, difficulty=difficulty)

    prompt = f"""
You are an interview preparation coach.

Create a structured interview plan for the target role and difficulty level.

Target role:
\"\"\"{target_role}\"\"\"

Difficulty:
\"\"\"{difficulty}\"\"\"

Candidate resume text:
\"\"\"{resume_text}\"\"\"

Return STRICT JSON only (no markdown, no explanation) with this exact schema:
{{
  "interview_structure": [
    {{
      "round_name": "string",
      "duration_minutes": 5,
      "objectives": ["string"],
      "evaluation_signals": ["string"]
    }}
  ],
  "question_categories": [
    {{
      "category": "string",
      "percentage": 0,
      "example_questions": ["string"]
    }}
  ],
  "time_allocation": [
    {{
      "segment": "string",
      "minutes": 0
    }}
  ]
}}

Constraints:
- duration_minutes and minutes must be integers.
- percentages must be integers and should sum to 100.
- Keep interview total time between 45 and 120 minutes.
"""

    try:
        response = model.generate_content(prompt)
        raw = response.text or ""
        json_text = _extract_json(raw)
        data: Any = json.loads(json_text)

        # Validate via Pydantic
        plan = InterviewPlanResponse.model_validate(data)

        # Post-validate: clamp/normalize percentages sum to 100
        pct_sum = sum(c.percentage for c in plan.question_categories)
        if plan.question_categories and pct_sum != 100:
            plan.question_categories[-1].percentage = max(
                0, min(100, plan.question_categories[-1].percentage + (100 - pct_sum))
            )

        return plan
    except Exception:
        return _mock_plan(target_role=target_role, difficulty=difficulty)

