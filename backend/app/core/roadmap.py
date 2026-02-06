from __future__ import annotations

import json
from typing import Any, List

from app.core.config import settings
from app.schemas.report import InterviewReport
from app.schemas.roadmap import CareerRoadmap, RoadmapPhase, RoadmapSkill


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


def _mock_roadmap(report: InterviewReport) -> CareerRoadmap:
    # Use weaknesses and improvement tips to infer skills
    base_weeks = 4
    skills: List[RoadmapSkill] = []

    for s in report.skill_breakdown:
        if s.score >= 80:
            continue
        weeks = base_weeks
        if s.score < 60:
            weeks = 8
        skills.append(
            RoadmapSkill(
                name=s.name,
                current_level="developing" if s.score < 70 else "solid",
                target_level="strong",
                resources=[
                    f"Deep-dive articles or books on {s.name.lower()} in the context of {report.target_role}",
                    f"Hands-on practice: design or implement 2–3 projects focusing on {s.name.lower()}.",
                ],
                estimated_weeks=weeks,
            )
        )

    if not skills:
        skills.append(
            RoadmapSkill(
                name="Advanced role-specific skills",
                current_level="solid",
                target_level="expert",
                resources=[
                    f"Identify advanced topics for {report.target_role} and complete one course.",
                    "Mentor or teach others to solidify knowledge.",
                ],
                estimated_weeks=6,
            )
        )

    timeline = [
        RoadmapPhase(
            name="Foundation (Weeks 1–4)",
            duration_weeks=4,
            focus_areas=[skills[0].name],
        )
    ]
    if len(skills) > 1:
        timeline.append(
            RoadmapPhase(
                name="Deepening (Weeks 5–8)",
                duration_weeks=4,
                focus_areas=[s.name for s in skills[1:3]],
            )
        )
    if len(skills) > 3:
        timeline.append(
            RoadmapPhase(
                name="Polish & interview practice (Weeks 9–12)",
                duration_weeks=4,
                focus_areas=[s.name for s in skills[3:]],
            )
        )

    return CareerRoadmap(
        interview_id=report.interview_id,
        target_role=report.target_role,
        skills_to_learn=skills,
        timeline=timeline,
    )


def generate_roadmap(report: InterviewReport) -> CareerRoadmap:
    model = _gemini_model()
    if model is None:
        return _mock_roadmap(report)

    summary = report.summary or ""
    weaknesses_text = "; ".join(report.weaknesses)
    tips_text = "; ".join(report.improvement_tips)
    skills_json = json.dumps(
        [{"name": s.name, "score": s.score, "comment": s.comment} for s in report.skill_breakdown],
        ensure_ascii=False,
    )

    prompt = f"""
You are a career coach creating a personalized roadmap.

Target role: {report.target_role}
Difficulty: {report.difficulty}

Skill breakdown:
{skills_json}

Strengths:
{json.dumps(report.strengths, ensure_ascii=False)}

Weaknesses:
{weaknesses_text}

Improvement tips from interview report:
{tips_text}

Report summary:
\"\"\"{summary}\"\"\"

Return STRICT JSON only (no markdown, no commentary) with this exact structure:
{{
  "skills_to_learn": [
    {{
      "name": "string",
      "current_level": "string",
      "target_level": "string",
      "resources": ["string"],
      "estimated_weeks": 4
    }}
  ],
  "timeline": [
    {{
      "name": "string",
      "duration_weeks": 4,
      "focus_areas": ["string"]
    }}
  ]
}}

Constraints:
- estimated_weeks and duration_weeks should be positive integers.
- Focus areas should reference skills by name where possible.
"""

    try:
        resp = model.generate_content(prompt)
        raw = (resp.text or "").strip()
        json_text = _extract_json(raw)
        data: Any = json.loads(json_text)

        skills = [
            RoadmapSkill(
                name=str(s.get("name", "")).strip() or "General",
                current_level=str(s.get("current_level", "unknown")),
                target_level=str(s.get("target_level", "proficient")),
                resources=[str(r) for r in s.get("resources", []) or []],
                estimated_weeks=int(s.get("estimated_weeks", 4)),
            )
            for s in data.get("skills_to_learn", []) or []
        ]

        if not skills:
            return _mock_roadmap(report)

        timeline = [
            RoadmapPhase(
                name=str(p.get("name", "")).strip() or "Phase",
                duration_weeks=int(p.get("duration_weeks", 4)),
                focus_areas=[str(f) for f in p.get("focus_areas", []) or []],
            )
            for p in data.get("timeline", []) or []
        ]

        if not timeline:
            timeline = _mock_roadmap(report).timeline

        return CareerRoadmap(
            interview_id=report.interview_id,
            target_role=report.target_role,
            skills_to_learn=skills,
            timeline=timeline,
        )
    except Exception:
        return _mock_roadmap(report)

