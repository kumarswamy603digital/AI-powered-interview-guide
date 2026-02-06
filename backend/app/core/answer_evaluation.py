from __future__ import annotations

import json
from typing import Any

from app.core.config import settings
from app.schemas.answer_evaluation import AnswerEvaluationMetrics, AnswerEvaluationResponse


try:  # Optional Gemini dependency
    import google.generativeai as genai
except Exception:  # pragma: no cover
    genai = None  # type: ignore[assignment]


def _gemini_model():
    if not settings.GEMINI_API_KEY or genai is None:
        return None
    genai.configure(api_key=settings.GEMINI_API_KEY)
    return genai.GenerativeModel(settings.GEMINI_MODEL)


def _extract_json(text: str) -> str:
    if not text:
        raise ValueError("Empty response")
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found")
    return text[start : end + 1]


def _heuristic_evaluate(question: str, answer: str) -> AnswerEvaluationResponse:
    a = (answer or "").strip()
    q = (question or "").strip().lower()

    length = len(a)
    sentences = max(1, a.count(".") + a.count("!") + a.count("?"))

    # Simple heuristics
    relevance = 80.0
    if len(q) > 0 and any(w in q for w in ["why", "how", "design", "explain"]):
        if "because" not in a.lower() and "so that" not in a.lower():
            relevance -= 15.0

    depth = min(100.0, (length / 400.0) * 100.0)
    if "impact" in a.lower() or "result" in a.lower():
        depth = min(100.0, depth + 10.0)

    clarity = 70.0 + min(20.0, sentences * 2.0)
    if any(x in a for x in ["uh", "idk", "don't know"]):
        clarity -= 10.0

    confidence = 70.0
    if any(x in a.lower() for x in ["i think", "maybe", "not sure"]):
        confidence -= 15.0
    if any(x in a.lower() for x in ["definitely", "confident", "certain"]):
        confidence += 5.0

    # Clamp 0–100
    def clamp(v: float) -> float:
        return max(0.0, min(100.0, v))

    relevance = clamp(relevance)
    depth = clamp(depth)
    clarity = clamp(clarity)
    confidence = clamp(confidence)

    overall = round(0.35 * relevance + 0.35 * depth + 0.15 * clarity + 0.15 * confidence, 2)

    metrics = AnswerEvaluationMetrics(
        relevance=round(relevance, 2),
        depth=round(depth, 2),
        clarity=round(clarity, 2),
        confidence=round(confidence, 2),
        overall_score=overall,
    )

    feedback = (
        "This is a heuristic evaluation. Improve depth with concrete examples, "
        "quantified impact, and clearer structure."
    )

    return AnswerEvaluationResponse(**metrics.model_dump(), feedback=feedback)


def evaluate_answer(
    *,
    question: str,
    answer: str,
    target_role: str | None = None,
) -> AnswerEvaluationResponse:
    model = _gemini_model()
    if model is None:
        return _heuristic_evaluate(question, answer)

    role_context = f" for the role '{target_role}'" if target_role else ""

    prompt = f"""
You are evaluating a candidate's interview answer{role_context}.

Question:
\"\"\"{question}\"\"\"

Answer:
\"\"\"{answer}\"\"\"

Return STRICT JSON only (no markdown, no commentary) with this exact shape:
{{
  "relevance": <number 0-100>,
  "depth": <number 0-100>,
  "clarity": <number 0-100>,
  "confidence": <number 0-100>,
  "overall_score": <number 0-100>,
  "feedback": "short coaching feedback for the candidate"
}}

Guidelines:
- Relevance: how directly the answer addresses the question.
- Depth: level of detail, examples, and reasoning.
- Clarity: structure, coherence, and ease of understanding.
- Confidence: decisiveness and lack of hedging language (without being arrogant).
- overall_score should reflect a weighted summary of the above.
"""

    try:
        resp = model.generate_content(prompt)
        raw = (resp.text or "").strip()
        json_text = _extract_json(raw)
        data: Any = json.loads(json_text)

        metrics = AnswerEvaluationMetrics(
            relevance=float(data.get("relevance", 0)),
            depth=float(data.get("depth", 0)),
            clarity=float(data.get("clarity", 0)),
            confidence=float(data.get("confidence", 0)),
            overall_score=float(data.get("overall_score", 0)),
        )

        # Clamp values
        def clamp(v: float) -> float:
            return max(0.0, min(100.0, v))

        metrics.relevance = round(clamp(metrics.relevance), 2)
        metrics.depth = round(clamp(metrics.depth), 2)
        metrics.clarity = round(clamp(metrics.clarity), 2)
        metrics.confidence = round(clamp(metrics.confidence), 2)
        metrics.overall_score = round(clamp(metrics.overall_score), 2)

        feedback = str(data.get("feedback") or "").strip() or None
        return AnswerEvaluationResponse(**metrics.model_dump(), feedback=feedback)
    except Exception:
        return _heuristic_evaluate(question, answer)

