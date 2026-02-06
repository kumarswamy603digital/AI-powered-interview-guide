from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional

from app.core.config import settings
from app.schemas.live_interview import Difficulty, PersonalityMode


try:  # Optional dependency for Gemini
    import google.generativeai as genai
except Exception:  # pragma: no cover
    genai = None  # type: ignore[assignment]


@dataclass
class NextQuestion:
    question: str
    is_follow_up: bool


def _gemini_model():
    if not settings.GEMINI_API_KEY or genai is None:
        return None
    genai.configure(api_key=settings.GEMINI_API_KEY)
    return genai.GenerativeModel(settings.GEMINI_MODEL)


def _personality_instructions(mode: PersonalityMode) -> str:
    if mode == "strict":
        return "Be concise, direct, and high-standard. Challenge weak reasoning. No fluff."
    if mode == "stress":
        return "Apply pressure with fast follow-ups and tight constraints. Keep it professional, not abusive."
    # friendly
    return "Be supportive and collaborative. Give short guidance in the question if needed."


def _question_bank(target_role: str, difficulty: Difficulty) -> list[str]:
    role = target_role.lower()

    if "backend" in role or "api" in role:
        base = [
            "Walk me through an API you built end-to-end. What were the main trade-offs?",
            "How do you design pagination and filtering for a high-traffic endpoint?",
            "Explain how you would implement authentication and authorization for a new service.",
            "What are common database indexing pitfalls you've seen, and how do you diagnose them?",
            "How do you handle idempotency for write endpoints (e.g., payments, retries)?",
            "Describe a production incident you handled. What was the root cause and what did you change afterward?",
        ]
    elif "frontend" in role:
        base = [
            "Describe a complex UI you built. How did you manage state and performance?",
            "How do you structure a component library for scale and consistency?",
            "Explain strategies for optimizing bundle size and runtime performance.",
            "How do you test UI logic effectively (unit vs integration vs e2e)?",
            "Tell me about an accessibility issue you fixed and the approach you used.",
        ]
    elif "data" in role or "ml" in role:
        base = [
            "Walk through a project where you improved a model or pipeline. What changed and why?",
            "How do you detect data drift and decide when to retrain?",
            "Explain precision/recall trade-offs for an imbalanced classification problem.",
            "How do you ensure reproducibility in experiments and deployments?",
            "Describe how you'd design feature stores and offline/online parity.",
        ]
    else:
        base = [
            "Tell me about a project you're proud of. What was your specific impact?",
            "How do you approach ambiguous requirements and align stakeholders?",
            "Describe a difficult bug you fixed. How did you narrow it down?",
            "How do you prioritize tasks under tight deadlines?",
            "What does 'quality' mean to you in software delivery?",
        ]

    if difficulty == "hard":
        base.append("Design a scalable system for this role. Include data model, APIs, caching, and failure modes.")
    elif difficulty == "easy":
        base.insert(0, "Give me a quick summary of your background and why you're interested in this role.")

    return base


def _needs_follow_up(answer: str) -> bool:
    a = (answer or "").strip().lower()
    if len(a) < 60:
        return True
    if any(x in a for x in ["i don't know", "not sure", "no idea", "can't remember"]):
        return True
    return False


def next_question_mock(
    *,
    target_role: str,
    difficulty: Difficulty,
    personality_mode: PersonalityMode,
    question_index: int,
    last_answer: Optional[str],
    max_questions: int,
) -> NextQuestion:
    bank = _question_bank(target_role=target_role, difficulty=difficulty)
    # Loop bank if max_questions > bank size
    idx = min(question_index, max_questions - 1)
    q = bank[idx % len(bank)]

    if last_answer is not None and _needs_follow_up(last_answer):
        prefix = {
            "strict": "Your answer is too shallow. ",
            "friendly": "Thanks — could you expand a bit? ",
            "stress": "That's vague. ",
        }[personality_mode]
        return NextQuestion(question=f"{prefix}What exactly did you do, and what was the measurable impact?", is_follow_up=True)

    return NextQuestion(question=q, is_follow_up=False)


def next_question_gemini(
    *,
    resume_text: str,
    target_role: str,
    difficulty: Difficulty,
    personality_mode: PersonalityMode,
    transcript: list[dict[str, str]],
    question_index: int,
    max_questions: int,
) -> Optional[NextQuestion]:
    model = _gemini_model()
    if model is None:
        return None

    # Truncate resume to avoid huge prompts
    resume_snippet = resume_text[:8000]
    personality = _personality_instructions(personality_mode)

    prompt = f"""
You are conducting a live interview.
Personality mode instructions: {personality}

Target role: {target_role}
Difficulty: {difficulty}
Question number: {question_index + 1} of {max_questions}

Candidate resume (snippet):
\"\"\"{resume_snippet}\"\"\"

Conversation transcript (most recent last):
{json.dumps(transcript[-12:], ensure_ascii=False)}

Return STRICT JSON only:
{{
  "question": "string",
  "is_follow_up": true|false
}}

Guidelines:
- Ask one question only.
- If the last candidate answer is weak/short, produce a follow-up question.
- Otherwise produce the next best question for the role and difficulty.
"""

    try:
        resp = model.generate_content(prompt)
        raw = (resp.text or "").strip()
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        data: Any = json.loads(raw[start : end + 1])
        q = str(data.get("question", "")).strip()
        is_fu = bool(data.get("is_follow_up", False))
        if not q:
            return None
        return NextQuestion(question=q, is_follow_up=is_fu)
    except Exception:
        return None

