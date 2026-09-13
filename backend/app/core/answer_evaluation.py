from __future__ import annotations

import json
import re
from typing import Any, List

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


_QUESTION_STOPWORDS = {
    "a", "about", "an", "and", "are", "as", "at", "be", "but", "by", "can", "could",
    "did", "do", "does", "for", "from", "give", "had", "has", "have", "how", "i",
    "in", "is", "it", "its", "me", "my", "of", "on", "or", "our", "please", "should",
    "so", "tell", "than", "that", "the", "their", "them", "then", "there", "these",
    "they", "this", "to", "us", "was", "we", "were", "what", "when", "where", "which",
    "who", "why", "will", "with", "would", "you", "your", "example", "describe",
    "explain", "walk", "through", "time", "situation",
}

# Phrases that mean the question was not answered at all.
_NON_ANSWERS = (
    "i don't know", "i dont know", "not sure", "no idea", "can't remember",
    "cant remember", "no clue", "pass", "skip", "don't know", "dont know",
)

_HEDGES = ("i think", "maybe", "probably", "i guess", "sort of", "kind of", "might be")
_ASSERTIVE = ("definitely", "confident", "certain", "clearly", "specifically", "measured")
_CAUSAL = ("because", "so that", "therefore", "which meant", "as a result", "in order to",
           "the reason", "trade-off", "tradeoff", "instead of")
_IMPACT = ("impact", "result", "reduced", "increased", "improved", "saved", "cut",
           "grew", "latency", "throughput", "conversion", "revenue")

_WORD_RE = re.compile(r"[a-z0-9'+#.]+")
_NUMBER_RE = re.compile(r"\d")


def _words(text: str) -> List[str]:
    # '.' and '+'/'#' are allowed inside a token so 'node.js' and 'c++' survive,
    # then stripped from the edges so 'limiting.' does not become its own word.
    return [
        token
        for token in (t.strip(".'") for t in _WORD_RE.findall((text or "").lower()))
        if token
    ]


def _question_keywords(question: str) -> List[str]:
    seen: List[str] = []
    for word in _words(question):
        if word in _QUESTION_STOPWORDS or len(word) < 3:
            continue
        if word not in seen:
            seen.append(word)
    return seen


def _stem(word: str) -> str:
    """Crude suffix trim so 'scaling' matches 'scale' and 'services' matches 'service'."""
    for suffix in ("ing", "ers", "er", "ed", "es", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            return word[: -len(suffix)]
    return word


def _count_sentences(text: str) -> int:
    parts = [p for p in re.split(r"[.!?]+|\n+", text or "") if p.strip()]
    return max(1, len(parts))


def _heuristic_evaluate(question: str, answer: str) -> AnswerEvaluationResponse:
    """
    Deterministic answer scoring used when Gemini is not configured.

    Relevance is measured as overlap between the question's keywords and the
    answer, plus credit for naming real technical skills. The previous version
    returned a near-constant relevance (80, or 65 for any how/why/design
    question) regardless of what the candidate said, which made the relevance
    shown during a live interview meaningless.
    """
    text = (answer or "").strip()
    lowered = text.lower()
    length = len(text)
    words = _words(text)

    keywords = _question_keywords(question)
    answer_stems = {_stem(w) for w in words}
    matched = [k for k in keywords if _stem(k) in answer_stems]
    coverage = (len(matched) / len(keywords)) if keywords else 0.0

    # Naming concrete technologies is evidence of a substantive answer.
    try:
        from app.core.skills import extract_skills

        skills_mentioned = extract_skills(text)
    except Exception:  # pragma: no cover - defensive
        skills_mentioned = []

    is_non_answer = any(phrase in lowered for phrase in _NON_ANSWERS)

    # --- relevance -------------------------------------------------------
    # Keyword overlap alone is a poor judge: a strong answer often uses domain
    # synonyms ("token bucket") instead of the question's nouns ("rate limiter"),
    # while a one-liner that parrots the question scores full overlap. So overlap
    # is only part of the score, naming real technologies earns credit, and a
    # high-overlap/no-content answer is capped as an echo rather than an answer.
    if is_non_answer or len(words) < 4:
        relevance = 8.0 if is_non_answer else 15.0
    else:
        relevance = 25.0
        relevance += 35.0 * coverage
        relevance += min(20.0, 7.0 * len(skills_mentioned))
        relevance += min(15.0, len(words) / 4.0)
        if len(words) < 12:
            relevance -= 12.0  # too short to have actually addressed the question
        if coverage >= 0.6 and len(words) < 15:
            relevance = min(relevance, 35.0)  # echoes the question without answering it

    # --- depth -----------------------------------------------------------
    depth = min(60.0, (length / 500.0) * 100.0)
    depth += min(15.0, 5.0 * len(skills_mentioned))
    if any(marker in lowered for marker in _CAUSAL):
        depth += 12.0  # explains reasoning, not just what
    if any(marker in lowered for marker in _IMPACT):
        depth += 8.0
    if _NUMBER_RE.search(text):
        depth += 7.0  # quantified
    if is_non_answer:
        depth = min(depth, 10.0)

    # --- clarity ---------------------------------------------------------
    sentences = _count_sentences(text)
    words_per_sentence = len(words) / sentences if sentences else len(words)
    clarity = 72.0
    if 6 <= words_per_sentence <= 28:
        clarity += 12.0  # readable sentence length
    elif words_per_sentence > 45:
        clarity -= 15.0  # rambling
    if sentences >= 3:
        clarity += 4.0  # structured
    if any(filler in lowered for filler in ("uh", "um", "idk")):
        clarity -= 10.0
    if len(words) < 10:
        # There is nothing to be clear about in a one-liner; without this a
        # 6-word answer scored better on clarity than a 5-word one.
        clarity = min(clarity, 65.0)
    if is_non_answer:
        clarity = min(clarity, 40.0)

    # --- confidence ------------------------------------------------------
    confidence = 70.0
    if any(hedge in lowered for hedge in _HEDGES):
        confidence -= 15.0
    if any(word in lowered for word in _ASSERTIVE):
        confidence += 8.0
    if is_non_answer:
        confidence = 15.0

    def clamp(value: float) -> float:
        return max(0.0, min(100.0, value))

    relevance = clamp(relevance)
    depth = clamp(depth)
    clarity = clamp(clarity)
    confidence = clamp(confidence)

    # Relevance and depth dominate: a fluent, confident answer to the wrong
    # question is not a good interview answer. The previous weighting (0.35 /
    # 0.35 / 0.15 / 0.15) let polish outrank substance.
    overall = round(0.45 * relevance + 0.35 * depth + 0.10 * clarity + 0.10 * confidence, 2)

    metrics = AnswerEvaluationMetrics(
        relevance=round(relevance, 2),
        depth=round(depth, 2),
        clarity=round(clarity, 2),
        confidence=round(confidence, 2),
        overall_score=overall,
    )

    # Targeted feedback on the weakest dimension rather than a fixed string.
    scores = {"relevance": relevance, "depth": depth, "clarity": clarity, "confidence": confidence}
    weakest = min(scores, key=lambda key: scores[key])
    advice = {
        "relevance": (
            "The answer did not address the question directly."
            if not matched
            else f"Address more of what was asked — untouched: {', '.join(k for k in keywords if k not in matched)[:120]}."
        ),
        "depth": "Add specifics: the approach you chose, the trade-off you accepted, and a number that shows the outcome.",
        "clarity": "Tighten the structure — situation, what you did, then the result.",
        "confidence": "State decisions directly; hedging reads as uncertainty about your own work.",
    }[weakest]
    feedback = f"Heuristic evaluation (no AI key configured). Weakest area: {weakest}. {advice}"

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

