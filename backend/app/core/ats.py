from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from app.core.config import settings


try:  # Optional dependency for Gemini
    import google.generativeai as genai
except Exception:  # pragma: no cover - optional
    genai = None  # type: ignore[assignment]


@dataclass
class AtsScoreResult:
    keyword_match_score: float
    formatting_score: float
    final_score: float

    def to_dict(self) -> Dict[str, float]:
        return {
            "keyword_match_score": self.keyword_match_score,
            "formatting_score": self.formatting_score,
            "final_score": self.final_score,
        }


def _mock_ats_score(resume_text: str, job_role: str) -> AtsScoreResult:
    """
    Deterministic fallback ATS scoring when Gemini is not configured.
    """
    text_lower = resume_text.lower()
    role_lower = job_role.lower()

    # Very simple keyword heuristic: count occurrences of role words in resume
    role_keywords = [w for w in role_lower.replace("/", " ").replace("-", " ").split() if len(w) > 2]
    if not role_keywords:
        keyword_score = 50.0
    else:
        hits = sum(1 for kw in role_keywords if kw in text_lower)
        keyword_score = min(100.0, (hits / len(role_keywords)) * 100.0)

    # Simple formatting heuristic: presence of common resume sections + bullet points
    sections = ["experience", "education", "skills", "projects", "summary"]
    section_hits = sum(1 for s in sections if s in text_lower)
    bullets = text_lower.count("•") + text_lower.count("- ")
    formatting_score = min(100.0, section_hits * 15.0 + min(bullets, 10) * 3.0)

    final_score = round((keyword_score * 0.6) + (formatting_score * 0.4), 2)

    return AtsScoreResult(
        keyword_match_score=round(keyword_score, 2),
        formatting_score=round(formatting_score, 2),
        final_score=final_score,
    )


def _gemini_client():
    if not settings.GEMINI_API_KEY or genai is None:
        return None
    genai.configure(api_key=settings.GEMINI_API_KEY)
    return genai.GenerativeModel(settings.GEMINI_MODEL)


def score_resume(resume_text: str, job_role: str) -> AtsScoreResult:
    """
    Score a resume for a given job role.

    Uses Gemini if configured via GEMINI_API_KEY, otherwise falls back to a
    deterministic heuristic-based scorer.
    """
    model = _gemini_client()
    if model is None:
        return _mock_ats_score(resume_text, job_role)

    prompt = f"""
You are an ATS (Applicant Tracking System) scorer.

Given the following inputs:

Job Role:
\"\"\"{job_role}\"\"\"

Resume Text:
\"\"\"{resume_text}\"\"\"

Return a strict JSON object with this exact structure and numeric values between 0 and 100:
{{
  "keyword_match_score": <number>,  // how well resume keywords match the role
  "formatting_score": <number>,     // how ATS-friendly the formatting is
  "final_score": <number>           // overall ATS score (weighted)
}}

Do not include any explanation or extra keys, only the JSON object.
"""
    try:
        response = model.generate_content(prompt)
        text = response.text or ""
        import json

        data: Any = json.loads(text)
        km = float(data.get("keyword_match_score", 0))
        fm = float(data.get("formatting_score", 0))
        fs = float(data.get("final_score", 0))

        # Clamp values 0–100
        km = max(0.0, min(100.0, km))
        fm = max(0.0, min(100.0, fm))
        fs = max(0.0, min(100.0, fs))

        return AtsScoreResult(
            keyword_match_score=round(km, 2),
            formatting_score=round(fm, 2),
            final_score=round(fs, 2),
        )
    except Exception:
        # On any error, gracefully fall back to heuristic scorer
        return _mock_ats_score(resume_text, job_role)

