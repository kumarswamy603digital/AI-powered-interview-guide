from __future__ import annotations

import json
from typing import Any, List

from app.core.config import settings
from app.schemas.report import InterviewReport, SkillScore


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


def _mock_report(
    *,
    interview_id: int,
    target_role: str,
    difficulty: str,
    personality_mode: str,
    transcript: list[dict[str, str]],
) -> InterviewReport:
    skills: List[SkillScore] = [
        SkillScore(name="Problem solving", score=75.0, comment="Shows generally structured thinking."),
        SkillScore(name="Communication", score=80.0, comment="Explains ideas clearly with some detail."),
        SkillScore(name="Technical depth", score=70.0, comment="Covers core concepts; can go deeper on trade-offs."),
        SkillScore(name="Collaboration", score=78.0, comment="Uses 'we' appropriately and mentions teamwork."),
    ]

    strengths = [
        "Explains previous projects with reasonable clarity.",
        "Shows awareness of trade-offs and constraints in past work.",
    ]
    weaknesses = [
        "Answers sometimes stay at a high level without specific metrics.",
        "Could provide more concrete examples of failure modes and mitigations.",
    ]
    tips = [
        "Prepare 2–3 STAR-style examples with clear metrics for impact.",
        "Practice summarizing complex projects in 1–2 minutes before diving into details.",
        "Anticipate follow-up questions about trade-offs, edge cases, and failure scenarios.",
    ]

    summary = (
        "Overall, the candidate presents as solid for the role but should deepen examples with "
        "more concrete details and quantified outcomes."
    )

    return InterviewReport(
        interview_id=interview_id,
        target_role=target_role,
        difficulty=difficulty,
        personality_mode=personality_mode,
        skill_breakdown=skills,
        strengths=strengths,
        weaknesses=weaknesses,
        improvement_tips=tips,
        summary=summary,
    )


def generate_report(
    *,
    interview_id: int,
    target_role: str,
    difficulty: str,
    personality_mode: str,
    transcript: list[dict[str, str]],
) -> InterviewReport:
    model = _gemini_model()
    if model is None:
        return _mock_report(
            interview_id=interview_id,
            target_role=target_role,
            difficulty=difficulty,
            personality_mode=personality_mode,
            transcript=transcript,
        )

    prompt = f"""
You are generating a detailed interview report for a candidate.

Target role: {target_role}
Difficulty: {difficulty}
Interviewer personality mode: {personality_mode}

Conversation transcript (chronological):
{json.dumps(transcript[-80:], ensure_ascii=False)}

Return STRICT JSON only (no markdown, no commentary) with this exact structure:
{{
  "skill_breakdown": [
    {{
      "name": "string",
      "score": 0,
      "comment": "string"
    }}
  ],
  "strengths": ["string"],
  "weaknesses": ["string"],
  "improvement_tips": ["string"],
  "summary": "string"
}}

Guidelines:
- Use scores between 0 and 100.
- Skill names should be concise (e.g. 'Problem solving', 'System design', 'Communication').
- Strengths/weaknesses/improvement_tips should be candidate-facing and actionable.
"""

    try:
        resp = model.generate_content(prompt)
        raw = (resp.text or "").strip()
        json_text = _extract_json(raw)
        data: Any = json.loads(json_text)

        skills = [
            SkillScore(
                name=str(s.get("name", "")).strip() or "General",
                score=float(s.get("score", 0)),
                comment=(s.get("comment") or "") or None,
            )
            for s in data.get("skill_breakdown", []) or []
        ]

        # Clamp scores
        for s in skills:
            s.score = max(0.0, min(100.0, s.score))

        strengths = [str(x) for x in data.get("strengths", []) or []]
        weaknesses = [str(x) for x in data.get("weaknesses", []) or []]
        tips = [str(x) for x in data.get("improvement_tips", []) or []]
        summary = str(data.get("summary") or "") or None

        return InterviewReport(
            interview_id=interview_id,
            target_role=target_role,
            difficulty=difficulty,
            personality_mode=personality_mode,
            skill_breakdown=skills,
            strengths=strengths,
            weaknesses=weaknesses,
            improvement_tips=tips,
            summary=summary,
        )
    except Exception:
        return _mock_report(
            interview_id=interview_id,
            target_role=target_role,
            difficulty=difficulty,
            personality_mode=personality_mode,
            transcript=transcript,
        )

