from __future__ import annotations

"""
Candidate ranking and hiring recommendations.

This is the reasoning layer the platform was missing: it joins three independent
HR data sources — the parsed resume, the job requisition's stated requirements,
and persisted interview scores — into one ranked, explainable recommendation.

Deliberately deterministic (no LLM call): a hiring recommendation has to be
reproducible and auditable, and every score here can be traced back to the input
that produced it via `reasoning`.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional

from app.core.skills import extract_years_experience, match_skills


Recommendation = Literal[
    "recommend_hire",
    "advance_to_interview",
    "further_assessment",
    "reject",
]

Confidence = Literal["high", "medium", "low"]


# Relative importance of each signal when all three are present. Weights are
# renormalised over whatever is actually available for a given candidate, so a
# candidate who has not interviewed yet is not penalised for the missing score.
WEIGHT_SKILLS = 0.45
WEIGHT_EXPERIENCE = 0.20
WEIGHT_INTERVIEW = 0.35

# A candidate whose resume matches well but who interviewed poorly is the single
# most valuable thing a multi-source system can surface, so it gets its own flag.
CONFLICT_SKILL_FLOOR = 75.0
CONFLICT_INTERVIEW_CEILING = 55.0
UNDERSOLD_SKILL_CEILING = 50.0
UNDERSOLD_INTERVIEW_FLOOR = 80.0


@dataclass
class JobRequirements:
    """Job-side inputs for scoring."""

    id: Optional[int] = None
    title: str = ""
    required_skills: List[str] = field(default_factory=list)
    preferred_skills: List[str] = field(default_factory=list)
    min_years_experience: Optional[float] = None


@dataclass
class CandidateEvidence:
    """Candidate-side inputs, gathered from separate sources."""

    id: Optional[int] = None
    full_name: str = ""
    stage: str = "applied"
    resume_text: str = ""
    extracted_skills: List[str] = field(default_factory=list)
    years_experience: Optional[float] = None
    interview_score: Optional[float] = None
    interview_skill_scores: Dict[str, float] = field(default_factory=dict)
    interview_session_id: Optional[int] = None
    interviews_completed: int = 0


@dataclass
class ScoreComponent:
    name: str
    score: float
    weight: float
    detail: str


@dataclass
class CandidateRanking:
    candidate_id: Optional[int]
    full_name: str
    stage: str
    final_score: float
    skill_match_score: float
    experience_match_score: Optional[float]
    interview_score: Optional[float]
    preferred_skill_score: Optional[float]
    matched_skills: List[str]
    missing_skills: List[str]
    matched_preferred_skills: List[str]
    additional_skills: List[str]
    recommendation: Recommendation
    confidence: Confidence
    reasoning: List[str]
    flags: List[str]
    data_sources: List[str]
    components: List[ScoreComponent]
    interview_session_id: Optional[int] = None


def _round(value: float) -> float:
    return round(float(value), 2)


def _skill_score(matched: List[str], missing: List[str]) -> Optional[float]:
    total = len(matched) + len(missing)
    if total == 0:
        return None
    return (len(matched) / total) * 100.0


def _experience_score(
    years: Optional[float],
    min_years: Optional[float],
) -> tuple[Optional[float], str]:
    if years is None:
        return None, "No experience figure found on the resume."
    if not min_years:
        # No stated requirement: presence of experience is mildly positive but
        # cannot be scored against anything, so treat it as a full match.
        return 100.0, f"{years:g} years experience; job states no minimum."

    ratio = years / float(min_years)
    # Meeting the bar is 100; exceeding it adds a little, capped, because 10 years
    # against a 3-year requirement is not three times better.
    if ratio >= 1.0:
        score = min(100.0, 90.0 + min(ratio - 1.0, 1.0) * 10.0)
    else:
        score = max(0.0, ratio * 90.0)
    return score, f"{years:g} years experience vs {float(min_years):g} required."


def _recommend(
    *,
    final_score: float,
    coverage: Optional[float],
    interview_score: Optional[float],
    flags: List[str],
) -> tuple[Recommendation, List[str]]:
    notes: List[str] = []
    # Coverage of *required* skills acts as a gate independent of the blended
    # score, so a strong interview cannot mask missing mandatory skills.
    if coverage is not None and coverage < 0.5:
        if interview_score is not None and interview_score >= 80.0:
            notes.append(
                "Fewer than half the required skills are evidenced, but interview "
                "performance was strong — assess the gaps directly before deciding."
            )
            return "further_assessment", notes
        notes.append("Fewer than half of the required skills are evidenced on the resume.")
        return "reject", notes

    if interview_score is None:
        notes.append("No completed interview yet; recommendation is based on resume and job fit only.")
        if final_score >= 70.0 and (coverage is None or coverage >= 0.7):
            return "advance_to_interview", notes
        if final_score >= 50.0:
            return "further_assessment", notes
        return "reject", notes

    if "resume_interview_mismatch" in flags:
        notes.append(
            "Resume/interview signals disagree, so the recommendation is capped at "
            "further assessment rather than a hire."
        )
        return "further_assessment", notes

    if final_score >= 78.0 and (coverage is None or coverage >= 0.8):
        return "recommend_hire", notes
    if final_score >= 62.0:
        return "further_assessment", notes
    return "reject", notes


def rank_candidate(candidate: CandidateEvidence, job: JobRequirements) -> CandidateRanking:
    """Score a single candidate against a job requisition."""
    resume_text = candidate.resume_text or ""

    matched, missing = match_skills(
        job.required_skills,
        resume_text=resume_text,
        known_skills=candidate.extracted_skills,
    )
    matched_preferred, missing_preferred = match_skills(
        job.preferred_skills,
        resume_text=resume_text,
        known_skills=candidate.extracted_skills,
    )

    skill_score = _skill_score(matched, missing)
    preferred_score = _skill_score(matched_preferred, missing_preferred)
    coverage = None if skill_score is None else skill_score / 100.0

    # Preferred skills nudge the skill signal without ever dominating it.
    effective_skill_score = skill_score
    if skill_score is not None and preferred_score is not None:
        effective_skill_score = min(100.0, skill_score * 0.85 + preferred_score * 0.15)

    years = candidate.years_experience
    if years is None:
        years = extract_years_experience(resume_text)
    experience_score, experience_detail = _experience_score(years, job.min_years_experience)

    interview_score = candidate.interview_score

    # --- Blend whatever signals exist, renormalising the weights ------------
    components: List[ScoreComponent] = []
    if effective_skill_score is not None:
        components.append(
            ScoreComponent(
                name="skill_match",
                score=_round(effective_skill_score),
                weight=WEIGHT_SKILLS,
                detail=f"{len(matched)}/{len(matched) + len(missing)} required skills evidenced.",
            )
        )
    if experience_score is not None:
        components.append(
            ScoreComponent(
                name="experience_match",
                score=_round(experience_score),
                weight=WEIGHT_EXPERIENCE,
                detail=experience_detail,
            )
        )
    if interview_score is not None:
        components.append(
            ScoreComponent(
                name="interview_performance",
                score=_round(interview_score),
                weight=WEIGHT_INTERVIEW,
                detail=(
                    f"Average of {len(candidate.interview_skill_scores)} assessed skills"
                    if candidate.interview_skill_scores
                    else "Overall interview score."
                ),
            )
        )

    total_weight = sum(c.weight for c in components)
    if total_weight > 0:
        final_score = sum(c.score * c.weight for c in components) / total_weight
        # Report the renormalised weights actually used.
        for component in components:
            component.weight = _round(component.weight / total_weight)
    else:
        final_score = 0.0

    # --- Cross-source flags -------------------------------------------------
    flags: List[str] = []
    if not resume_text.strip():
        flags.append("no_resume_text")
    if (
        skill_score is not None
        and interview_score is not None
        and skill_score >= CONFLICT_SKILL_FLOOR
        and interview_score < CONFLICT_INTERVIEW_CEILING
    ):
        flags.append("resume_interview_mismatch")
    if (
        skill_score is not None
        and interview_score is not None
        and skill_score <= UNDERSOLD_SKILL_CEILING
        and interview_score >= UNDERSOLD_INTERVIEW_FLOOR
    ):
        flags.append("outperformed_resume")
    if missing and coverage is not None and coverage >= 0.5:
        flags.append("partial_skill_gap")

    recommendation, recommendation_notes = _recommend(
        final_score=final_score,
        coverage=coverage,
        interview_score=interview_score,
        flags=flags,
    )

    # --- Human-readable reasoning ------------------------------------------
    reasoning: List[str] = []
    if skill_score is None:
        reasoning.append("Job requisition lists no required skills, so skill fit could not be scored.")
    else:
        matched_text = ", ".join(matched) if matched else "none"
        reasoning.append(
            f"Matched {len(matched)} of {len(matched) + len(missing)} required skills "
            f"({skill_score:.0f}%): {matched_text}."
        )
        if missing:
            reasoning.append(f"Missing required skills: {', '.join(missing)}.")
    if matched_preferred:
        reasoning.append(f"Also brings preferred skills: {', '.join(matched_preferred)}.")
    reasoning.append(experience_detail)
    if interview_score is None:
        reasoning.append("No scored interview on record.")
    else:
        top = sorted(candidate.interview_skill_scores.items(), key=lambda kv: kv[1], reverse=True)
        if len(top) >= 3:
            best = ", ".join(f"{name} {score:.0f}" for name, score in top[:2])
            worst = ", ".join(f"{name} {score:.0f}" for name, score in top[-2:])
            reasoning.append(
                f"Interview score {interview_score:.0f}/100 — strongest: {best}; weakest: {worst}."
            )
        elif top:
            # Too few assessed skills to talk about 'strongest vs weakest'
            # without repeating the same entries, so list them all.
            breakdown = ", ".join(f"{name} {score:.0f}" for name, score in top)
            reasoning.append(f"Interview score {interview_score:.0f}/100 — {breakdown}.")
        else:
            reasoning.append(f"Interview score {interview_score:.0f}/100.")
    if "resume_interview_mismatch" in flags:
        reasoning.append(
            f"Conflict: resume evidences {skill_score:.0f}% of required skills but the interview "
            f"scored only {interview_score:.0f}/100."
        )
    if "outperformed_resume" in flags:
        reasoning.append(
            "Candidate interviewed far better than the resume suggests — the resume may "
            "understate their skills."
        )
    if "no_resume_text" in flags:
        reasoning.append(
            "No resume text available (upload a parseable file), so skill matching used no resume evidence."
        )
    reasoning.extend(recommendation_notes)

    # --- Confidence ---------------------------------------------------------
    available = len(components)
    if "no_resume_text" in flags or available <= 1:
        confidence: Confidence = "low"
    elif available == 3 and "resume_interview_mismatch" not in flags:
        confidence = "high"
    else:
        confidence = "medium"

    data_sources = ["job_requirements"]
    if resume_text.strip():
        data_sources.append("resume")
    if interview_score is not None:
        data_sources.append("interview")
    if candidate.years_experience is not None:
        data_sources.append("candidate_record")

    additional = sorted(
        {s for s in candidate.extracted_skills}
        - {*matched, *missing, *matched_preferred, *missing_preferred}
    )

    return CandidateRanking(
        candidate_id=candidate.id,
        full_name=candidate.full_name,
        stage=candidate.stage,
        final_score=_round(final_score),
        skill_match_score=_round(skill_score or 0.0),
        experience_match_score=None if experience_score is None else _round(experience_score),
        interview_score=None if interview_score is None else _round(interview_score),
        preferred_skill_score=None if preferred_score is None else _round(preferred_score),
        matched_skills=matched,
        missing_skills=missing,
        matched_preferred_skills=matched_preferred,
        additional_skills=additional,
        recommendation=recommendation,
        confidence=confidence,
        reasoning=reasoning,
        flags=flags,
        data_sources=data_sources,
        components=components,
        interview_session_id=candidate.interview_session_id,
    )


def rank_candidates(
    candidates: List[CandidateEvidence],
    job: JobRequirements,
) -> List[CandidateRanking]:
    """
    Rank candidates for a job, best first.

    Ties break on skill match, then interview score, so ordering is stable and
    explainable rather than dependent on database row order.
    """
    rankings = [rank_candidate(candidate, job) for candidate in candidates]
    rankings.sort(
        key=lambda r: (r.final_score, r.skill_match_score, r.interview_score or 0.0),
        reverse=True,
    )
    return rankings


def aggregate_skill_gaps(rankings: List[CandidateRanking]) -> List[tuple[str, int]]:
    """
    Count how many ranked candidates are missing each required skill.

    Turns individual gaps into a workforce-level signal ('12 candidates lack
    Kubernetes'), which is what makes the gap actionable for HR.
    """
    counts: Dict[str, int] = {}
    for ranking in rankings:
        for skill in ranking.missing_skills:
            counts[skill] = counts.get(skill, 0) + 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
