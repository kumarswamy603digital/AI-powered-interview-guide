from __future__ import annotations

"""
Performance intelligence.

Analyses goals, feedback and review history to identify strengths and
improvement areas, and calibrates an employee against their department.

The analysis is lexicon and theme based rather than LLM based so that the same
review data always yields the same conclusions - a performance judgement that
changes between page loads is not usable in a review conversation. An optional
LLM narrative can be layered on top by the caller.
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional, Sequence, Tuple


Trajectory = Literal["improving", "steady", "declining", "unknown"]
PromotionReadiness = Literal["ready", "developing", "not_yet", "unknown"]


# Weights for the blended performance score; renormalised over available inputs.
WEIGHT_GOALS = 0.40
WEIGHT_RATING = 0.40
WEIGHT_FEEDBACK = 0.20


# Themes and the vocabulary that signals them. Ordered longest-first at match
# time so multi-word cues win over single words.
THEME_KEYWORDS: Dict[str, List[str]] = {
    "Communication": [
        "communication", "communicate", "articulate", "clarity", "clear explanation",
        "presented", "presentation", "explains", "written", "documentation", "writing",
    ],
    "Collaboration": [
        "collaboration", "collaborate", "collaborative", "team player", "teamwork",
        "cross-functional", "cross functional", "partnered", "supportive", "helped the team",
    ],
    "Leadership": [
        "leadership", "led the", "leads", "ownership", "took ownership", "drove",
        "initiative", "stepped up", "mentored", "mentoring", "coaching", "guided",
    ],
    "Technical depth": [
        "technical depth", "architecture", "architectural", "system design", "code quality",
        "debugging", "root cause", "optimisation", "optimization", "performance tuning",
        "technically strong", "deep understanding",
    ],
    "Delivery & execution": [
        "delivered", "delivery", "shipped", "execution", "on time", "deadline",
        "milestone", "throughput", "velocity", "follow through", "follow-through",
    ],
    "Quality": [
        "quality", "defect", "bug", "regression", "testing", "test coverage",
        "code review", "attention to detail", "rework",
    ],
    "Learning agility": [
        "learned", "learning", "picked up", "ramped up", "adaptable", "adapted",
        "new technology", "upskilled", "curious",
    ],
    "Stakeholder management": [
        "stakeholder", "client", "customer", "expectations", "escalation",
        "business partner", "product partner",
    ],
    "Reliability": [
        "reliable", "dependable", "consistent", "consistency", "trusted", "accountable",
    ],
}

POSITIVE_TERMS = {
    "excellent", "outstanding", "strong", "great", "good", "impressive", "exceeded",
    "exceptional", "consistently", "proactive", "reliable", "dependable", "clear",
    "improved", "improvement", "effective", "efficient", "thorough", "valuable",
    "positive", "praised", "champion", "best", "solid", "trusted", "helpful",
    "well", "successfully", "smooth", "accurate", "creative", "innovative",
}

NEGATIVE_TERMS = {
    "struggled", "struggles", "missed", "unclear", "lacked", "lacks", "lacking",
    "inconsistent", "delayed", "delay", "concern", "concerning", "difficulty",
    "difficult", "poor", "slow", "failed", "gap", "gaps", "weak", "weakness",
    "insufficient", "needs", "needs improvement", "behind", "confusion", "confusing",
    "rework", "escalated", "conflict", "disengaged", "resistant", "avoided",
    "incomplete", "overdue", "regression", "defects", "bugs",
}

# Words that invert the polarity of the term that follows them.
NEGATIONS = {"not", "no", "never", "without", "lack", "lacks", "lacking", "rarely", "barely"}

_TOKEN_RE = re.compile(r"[a-z']+")


@dataclass
class ReviewInput:
    period: str = ""
    rating: Optional[float] = None  # 1-5
    potential_rating: Optional[float] = None
    strengths: Sequence[str] = field(default_factory=tuple)
    improvements: Sequence[str] = field(default_factory=tuple)
    comments: str = ""
    promotion_ready: Optional[str] = None  # yes|not_yet|no


@dataclass
class GoalInput:
    title: str = ""
    status: str = "not_started"
    progress: float = 0.0
    weight: float = 1.0
    related_skills: Sequence[str] = field(default_factory=tuple)


@dataclass
class FeedbackInput:
    source: str = "peer"
    content: str = ""
    sentiment: Optional[float] = None


@dataclass
class PerformanceSignals:
    employee_id: Optional[int] = None
    full_name: str = ""
    department: str = ""
    job_title: str = ""
    seniority: Optional[str] = None
    # Chronological, oldest first.
    reviews: Sequence[ReviewInput] = field(default_factory=tuple)
    goals: Sequence[GoalInput] = field(default_factory=tuple)
    feedback: Sequence[FeedbackInput] = field(default_factory=tuple)
    department_average_rating: Optional[float] = None


@dataclass
class ThemeInsight:
    theme: str
    sentiment: float
    mentions: int
    sources: List[str]
    evidence: List[str]


@dataclass
class GoalSummary:
    total: int
    achieved: int
    on_track: int
    at_risk: int
    missed: int
    not_started: int
    weighted_attainment: float


@dataclass
class PerformanceAction:
    action: str
    rationale: str
    owner: str
    priority: Literal["high", "medium", "low"]


@dataclass
class PerformanceInsight:
    employee_id: Optional[int]
    full_name: str
    department: str
    job_title: str
    overall_score: float
    latest_rating: Optional[float]
    rating_trajectory: Trajectory
    rating_delta: Optional[float]
    goal_summary: GoalSummary
    calibration: Optional[str]
    calibration_delta: Optional[float]
    strengths: List[ThemeInsight]
    improvement_areas: List[ThemeInsight]
    feedback_sentiment: Optional[float]
    promotion_readiness: PromotionReadiness
    recommended_actions: List[PerformanceAction]
    summary: str
    data_sources: List[str]


def _round(value: float) -> float:
    return round(float(value), 2)


def _tokenize(text: str) -> List[str]:
    return _TOKEN_RE.findall((text or "").lower())


def score_sentiment(text: str) -> Optional[float]:
    """
    Lexicon sentiment for a snippet, -1.0 to 1.0, or None when no cue words appear.

    Handles simple negation ("not clear" reads as negative) but not sarcasm or
    comparatives, which is an accepted limitation of a lexicon approach.
    """
    tokens = _tokenize(text)
    if not tokens:
        return None

    positive = 0
    negative = 0
    for index, token in enumerate(tokens):
        polarity = 0
        if token in POSITIVE_TERMS:
            polarity = 1
        elif token in NEGATIVE_TERMS:
            polarity = -1
        if polarity == 0:
            continue
        window = tokens[max(0, index - 2) : index]
        if any(w in NEGATIONS for w in window):
            polarity *= -1
        if polarity > 0:
            positive += 1
        else:
            negative += 1

    if positive == 0 and negative == 0:
        return None
    return (positive - negative) / (positive + negative)


def _find_themes(text: str) -> List[str]:
    haystack = (text or "").lower()
    found: List[str] = []
    for theme, keywords in THEME_KEYWORDS.items():
        for keyword in sorted(keywords, key=len, reverse=True):
            if keyword in haystack:
                found.append(theme)
                break
    return found


def _sentence_split(text: str) -> List[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text or "")
    return [p.strip() for p in parts if p.strip()]


def _collect_themes(signals: PerformanceSignals) -> Dict[str, Dict[str, object]]:
    """
    Aggregate theme mentions across feedback and review text.

    Review `strengths`/`improvements` carry an explicit polarity, so they are
    scored as such instead of being run through the sentiment lexicon.
    """
    themes: Dict[str, Dict[str, object]] = {}

    def record(theme: str, sentiment: float, source: str, evidence: str) -> None:
        entry = themes.setdefault(
            theme, {"scores": [], "sources": set(), "evidence": [], "mentions": 0}
        )
        entry["scores"].append(sentiment)  # type: ignore[union-attr]
        entry["sources"].add(source)  # type: ignore[union-attr]
        entry["mentions"] = int(entry["mentions"]) + 1
        if len(entry["evidence"]) < 3:  # type: ignore[arg-type]
            snippet = evidence.strip()
            if len(snippet) > 180:
                snippet = snippet[:177] + "..."
            entry["evidence"].append(snippet)  # type: ignore[union-attr]

    for item in signals.feedback:
        overall = item.sentiment if item.sentiment is not None else score_sentiment(item.content)
        for sentence in _sentence_split(item.content):
            sentence_sentiment = score_sentiment(sentence)
            polarity = sentence_sentiment if sentence_sentiment is not None else overall
            if polarity is None:
                continue
            for theme in _find_themes(sentence):
                record(theme, polarity, f"{item.source} feedback", sentence)

    for review in signals.reviews:
        for strength in review.strengths or ():
            for theme in _find_themes(strength) or ["Reliability"]:
                record(theme, 1.0, f"review {review.period}".strip(), strength)
        for improvement in review.improvements or ():
            for theme in _find_themes(improvement) or ["Delivery & execution"]:
                record(theme, -1.0, f"review {review.period}".strip(), improvement)
        if review.comments:
            for sentence in _sentence_split(review.comments):
                polarity = score_sentiment(sentence)
                if polarity is None:
                    continue
                for theme in _find_themes(sentence):
                    record(theme, polarity, f"review {review.period}".strip(), sentence)

    return themes


def _goal_summary(goals: Sequence[GoalInput]) -> GoalSummary:
    counts = {"achieved": 0, "on_track": 0, "at_risk": 0, "missed": 0, "not_started": 0}
    weighted_total = 0.0
    weighted_progress = 0.0

    for goal in goals:
        status = (goal.status or "not_started").lower()
        if status in counts:
            counts[status] += 1
        weight = goal.weight if goal.weight and goal.weight > 0 else 1.0
        weighted_total += weight
        # Achieved goals count fully even if progress was recorded below 100.
        progress = 100.0 if status == "achieved" else max(0.0, min(100.0, goal.progress or 0.0))
        weighted_progress += progress * weight

    attainment = (weighted_progress / weighted_total) if weighted_total else 0.0
    return GoalSummary(
        total=len(goals),
        achieved=counts["achieved"],
        on_track=counts["on_track"],
        at_risk=counts["at_risk"],
        missed=counts["missed"],
        not_started=counts["not_started"],
        weighted_attainment=_round(attainment),
    )


def _trajectory(ratings: Sequence[float]) -> Tuple[Trajectory, Optional[float]]:
    values = [float(r) for r in ratings if r is not None]
    if not values:
        return "unknown", None
    if len(values) == 1:
        return "steady", 0.0
    delta = values[-1] - values[0]
    # On a 1-5 scale, a quarter-point move across cycles is a real signal; a
    # consistent monotonic climb counts even when the total move is smaller,
    # because sustained direction matters more than magnitude here.
    monotonic_up = len(values) >= 3 and all(b >= a for a, b in zip(values, values[1:])) and delta >= 0.2
    monotonic_down = len(values) >= 3 and all(b <= a for a, b in zip(values, values[1:])) and delta <= -0.2

    if delta >= 0.25 or monotonic_up:
        return "improving", _round(delta)
    if delta <= -0.25 or monotonic_down:
        return "declining", _round(delta)
    return "steady", _round(delta)


def _promotion_readiness(
    *,
    latest_rating: Optional[float],
    trajectory: Trajectory,
    attainment: float,
    reviews: Sequence[ReviewInput],
) -> PromotionReadiness:
    # An explicit manager judgement always wins over the inferred one.
    for review in reversed(list(reviews)):
        if review.promotion_ready:
            value = review.promotion_ready.strip().lower()
            if value in {"yes", "ready"}:
                return "ready"
            if value in {"not_yet", "not yet", "developing"}:
                return "developing"
            if value == "no":
                return "not_yet"

    if latest_rating is None:
        return "unknown"
    if latest_rating >= 4.2 and attainment >= 80.0 and trajectory != "declining":
        return "ready"
    if latest_rating >= 3.5 and attainment >= 60.0:
        return "developing"
    return "not_yet"


def _build_actions(
    *,
    goal_summary: GoalSummary,
    improvement_areas: Sequence[ThemeInsight],
    strengths: Sequence[ThemeInsight],
    trajectory: Trajectory,
    latest_rating: Optional[float],
    readiness: PromotionReadiness,
    calibration: Optional[str],
) -> List[PerformanceAction]:
    actions: List[PerformanceAction] = []

    if goal_summary.missed >= 2 or (goal_summary.total and goal_summary.weighted_attainment < 55.0):
        actions.append(
            PerformanceAction(
                action="Re-scope goals and agree weekly checkpoints",
                rationale=(
                    f"{goal_summary.missed} missed goals and "
                    f"{goal_summary.weighted_attainment:.0f}% weighted attainment."
                ),
                owner="Manager",
                priority="high",
            )
        )

    if goal_summary.at_risk >= 1 and goal_summary.missed == 0:
        actions.append(
            PerformanceAction(
                action="Unblock at-risk goals before the cycle closes",
                rationale=f"{goal_summary.at_risk} goal(s) currently at risk.",
                owner="Manager",
                priority="medium",
            )
        )

    for theme in list(improvement_areas)[:2]:
        actions.append(
            PerformanceAction(
                action=f"Targeted development on {theme.theme.lower()}",
                rationale=(
                    f"{theme.mentions} mention(s) with negative sentiment "
                    f"({theme.sentiment:+.2f}) from {', '.join(theme.sources[:2])}."
                ),
                owner="Manager",
                priority="high" if theme.sentiment <= -0.5 else "medium",
            )
        )

    if trajectory == "declining":
        actions.append(
            PerformanceAction(
                action="Investigate the cause of the performance decline",
                rationale="Rating has fallen across review cycles; check workload, role fit and engagement.",
                owner="Manager + HR",
                priority="high",
            )
        )

    if readiness == "ready":
        actions.append(
            PerformanceAction(
                action="Put forward for promotion in the next calibration",
                rationale=(
                    f"Rating {latest_rating:.1f}/5 with "
                    f"{goal_summary.weighted_attainment:.0f}% goal attainment."
                    if latest_rating is not None
                    else "Meets the promotion bar on goals and review signals."
                ),
                owner="Manager",
                priority="high",
            )
        )
    elif strengths:
        top = strengths[0]
        actions.append(
            PerformanceAction(
                action=f"Use {top.theme.lower()} strength as a stretch assignment or mentoring role",
                rationale=f"Consistently positive signal ({top.sentiment:+.2f}) across {top.mentions} mention(s).",
                owner="Manager",
                priority="low",
            )
        )

    if calibration == "below" and latest_rating is not None:
        actions.append(
            PerformanceAction(
                action="Review rating against department calibration",
                rationale="Rating sits below the department average; confirm the gap is performance, not calibration drift.",
                owner="HR",
                priority="medium",
            )
        )

    return actions


def analyze_performance(signals: PerformanceSignals) -> PerformanceInsight:
    """Produce a structured performance insight for one employee."""
    ratings = [r.rating for r in signals.reviews if r.rating is not None]
    latest_rating = float(ratings[-1]) if ratings else None
    trajectory, rating_delta = _trajectory([float(r) for r in ratings])

    goal_summary = _goal_summary(signals.goals)

    theme_data = _collect_themes(signals)
    themes: List[ThemeInsight] = []
    for theme, entry in theme_data.items():
        scores = [float(s) for s in entry["scores"]]  # type: ignore[union-attr]
        themes.append(
            ThemeInsight(
                theme=theme,
                sentiment=_round(sum(scores) / len(scores)),
                mentions=int(entry["mentions"]),
                sources=sorted(str(s) for s in entry["sources"]),  # type: ignore[union-attr]
                evidence=list(entry["evidence"]),  # type: ignore[arg-type]
            )
        )

    strengths = sorted(
        [t for t in themes if t.sentiment >= 0.25],
        key=lambda t: (t.sentiment, t.mentions),
        reverse=True,
    )
    improvement_areas = sorted(
        [t for t in themes if t.sentiment <= -0.15], key=lambda t: (t.sentiment, -t.mentions)
    )

    feedback_scores: List[float] = []
    for item in signals.feedback:
        value = item.sentiment if item.sentiment is not None else score_sentiment(item.content)
        if value is not None:
            feedback_scores.append(float(value))
    feedback_sentiment = _round(sum(feedback_scores) / len(feedback_scores)) if feedback_scores else None

    # --- blended score --------------------------------------------------
    components: List[Tuple[float, float]] = []
    if goal_summary.total:
        components.append((goal_summary.weighted_attainment, WEIGHT_GOALS))
    if latest_rating is not None:
        components.append(((latest_rating / 5.0) * 100.0, WEIGHT_RATING))
    if feedback_sentiment is not None:
        components.append(((feedback_sentiment + 1.0) * 50.0, WEIGHT_FEEDBACK))

    total_weight = sum(w for _, w in components)
    overall = sum(v * w for v, w in components) / total_weight if total_weight else 0.0

    calibration: Optional[str] = None
    calibration_delta: Optional[float] = None
    if latest_rating is not None and signals.department_average_rating is not None:
        calibration_delta = _round(latest_rating - float(signals.department_average_rating))
        if calibration_delta >= 0.3:
            calibration = "above"
        elif calibration_delta <= -0.3:
            calibration = "below"
        else:
            calibration = "at"

    readiness = _promotion_readiness(
        latest_rating=latest_rating,
        trajectory=trajectory,
        attainment=goal_summary.weighted_attainment,
        reviews=signals.reviews,
    )

    data_sources: List[str] = []
    if signals.reviews:
        data_sources.append("performance_reviews")
    if signals.goals:
        data_sources.append("goals")
    if signals.feedback:
        data_sources.append("feedback")
    if signals.department_average_rating is not None:
        data_sources.append("department_calibration")

    summary_bits: List[str] = []
    if latest_rating is not None:
        summary_bits.append(f"Latest rating {latest_rating:.1f}/5 ({trajectory})")
    if goal_summary.total:
        summary_bits.append(
            f"{goal_summary.weighted_attainment:.0f}% goal attainment "
            f"({goal_summary.achieved}/{goal_summary.total} achieved)"
        )
    if strengths:
        summary_bits.append(f"strongest in {strengths[0].theme.lower()}")
    if improvement_areas:
        summary_bits.append(f"development need in {improvement_areas[0].theme.lower()}")
    summary = ". ".join(summary_bits) + "." if summary_bits else "Not enough performance data recorded."

    return PerformanceInsight(
        employee_id=signals.employee_id,
        full_name=signals.full_name,
        department=signals.department,
        job_title=signals.job_title,
        overall_score=_round(overall),
        latest_rating=latest_rating,
        rating_trajectory=trajectory,
        rating_delta=rating_delta,
        goal_summary=goal_summary,
        calibration=calibration,
        calibration_delta=calibration_delta,
        strengths=strengths[:5],
        improvement_areas=improvement_areas[:5],
        feedback_sentiment=feedback_sentiment,
        promotion_readiness=readiness,
        recommended_actions=_build_actions(
            goal_summary=goal_summary,
            improvement_areas=improvement_areas,
            strengths=strengths,
            trajectory=trajectory,
            latest_rating=latest_rating,
            readiness=readiness,
            calibration=calibration,
        ),
        summary=summary,
        data_sources=data_sources,
    )
