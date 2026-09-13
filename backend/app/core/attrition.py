from __future__ import annotations

"""
Employee attrition risk prediction.

Deterministic and feature-based rather than a trained model, for three reasons:
there is no historical exit dataset to train on, a retention decision has to be
explainable to the employee's manager, and every factor here maps to an action
somebody can actually take.

Each signal scores 0-100 (higher = more flight risk) and carries the evidence
that produced it. Weights renormalise over the signals that have data, so an
employee with no engagement survey is not scored as if they were disengaged.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional, Sequence

from app.core.skills import HOT_MARKET_SKILLS, canonical_skill


RiskBand = Literal["low", "moderate", "high", "critical"]


# Relative importance of each signal. Career stagnation and engagement dominate
# because they are the most actionable and the most predictive in practice.
FEATURE_WEIGHTS: Dict[str, float] = {
    "career_stagnation": 0.20,
    "engagement": 0.16,
    "compensation": 0.14,
    "performance_trend": 0.12,
    "tenure_stage": 0.10,
    "workload": 0.10,
    "attendance": 0.08,
    "team_attrition": 0.05,
    "market_pull": 0.05,
}

FEATURE_LABELS: Dict[str, str] = {
    "career_stagnation": "Career stagnation",
    "engagement": "Engagement",
    "compensation": "Compensation position",
    "performance_trend": "Performance trend",
    "tenure_stage": "Tenure stage",
    "workload": "Workload",
    "attendance": "Attendance pattern",
    "team_attrition": "Team attrition",
    "market_pull": "External market pull",
}

BAND_THRESHOLDS = ((72.0, "critical"), (55.0, "high"), (35.0, "moderate"))


@dataclass
class EmployeeSignals:
    """
    Everything the model reads about one employee.

    All fields are optional: the model degrades gracefully and reports lower
    confidence instead of inventing values.
    """

    employee_id: Optional[int] = None
    full_name: str = ""
    department: str = ""
    job_title: str = ""
    seniority: Optional[str] = None

    tenure_years: Optional[float] = None
    months_since_last_promotion: Optional[float] = None

    # Chronological ratings, oldest first, on a 1-5 scale.
    performance_ratings: Sequence[float] = field(default_factory=tuple)
    goals_missed: int = 0
    goals_total: int = 0

    engagement_score: Optional[float] = None  # 0-100
    average_feedback_sentiment: Optional[float] = None  # -1.0 .. 1.0

    unplanned_absence_rate: Optional[float] = None  # 0.0 .. 1.0
    late_arrival_rate: Optional[float] = None  # 0.0 .. 1.0
    average_weekly_overtime: Optional[float] = None  # hours

    compa_ratio: Optional[float] = None  # 1.0 == band midpoint

    department_attrition_rate_12m: Optional[float] = None  # 0.0 .. 1.0
    skills: Sequence[str] = field(default_factory=tuple)


@dataclass
class RiskFactor:
    name: str
    label: str
    risk: float
    weight: float
    contribution: float
    evidence: str


@dataclass
class RetentionAction:
    action: str
    rationale: str
    expected_risk_reduction: float
    priority: Literal["high", "medium", "low"]
    owner: str


@dataclass
class AttritionAssessment:
    employee_id: Optional[int]
    full_name: str
    department: str
    job_title: str
    risk_score: float
    risk_band: RiskBand
    confidence: Literal["high", "medium", "low"]
    factors: List[RiskFactor]
    protective_factors: List[RiskFactor]
    recommended_actions: List[RetentionAction]
    signals_available: int
    signals_total: int
    summary: str


def _round(value: float) -> float:
    return round(float(value), 2)


def _interpolate(value: float, points: Sequence[tuple[float, float]]) -> float:
    """
    Piecewise-linear lookup over (threshold, risk) points sorted ascending.

    Linear interpolation avoids the cliff edges a pure banding would create,
    where one extra day of tenure could move someone a whole risk band.
    """
    if value <= points[0][0]:
        return points[0][1]
    if value >= points[-1][0]:
        return points[-1][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x0 <= value <= x1:
            if x1 == x0:
                return y1
            ratio = (value - x0) / (x1 - x0)
            return y0 + ratio * (y1 - y0)
    return points[-1][1]


# --------------------------------------------------------------------------
# Individual signals. Each returns (risk, evidence) or None when there is no data.
# --------------------------------------------------------------------------
def _tenure_stage(signals: EmployeeSignals):
    if signals.tenure_years is None:
        return None
    years = signals.tenure_years
    # Risk peaks between 1 and 2 years: long enough to be fully productive and
    # marketable, early enough that leaving costs little.
    risk = _interpolate(
        years,
        ((0.0, 45.0), (0.5, 58.0), (1.5, 72.0), (2.5, 55.0), (5.0, 38.0), (10.0, 25.0)),
    )
    return risk, f"{years:.1f} years tenure."


def _career_stagnation(signals: EmployeeSignals):
    months = signals.months_since_last_promotion
    if months is None:
        return None
    risk = _interpolate(
        months,
        ((0.0, 12.0), (12.0, 28.0), (24.0, 52.0), (36.0, 74.0), (48.0, 88.0), (72.0, 95.0)),
    )
    return risk, f"{months:.0f} months since last promotion or role change."


def _performance_trend(signals: EmployeeSignals):
    ratings = [float(r) for r in signals.performance_ratings if r is not None]
    if not ratings:
        return None

    latest = ratings[-1]
    if len(ratings) >= 2:
        delta = latest - ratings[0]
    else:
        delta = 0.0

    if delta <= -0.5:
        # Declining performance often follows disengagement rather than causing it.
        risk = 78.0
        evidence = f"Rating declined from {ratings[0]:.1f} to {latest:.1f}."
    elif latest < 2.5:
        risk = 70.0
        evidence = f"Sustained low rating ({latest:.1f}/5)."
    elif delta >= 0.5:
        risk = 24.0
        evidence = f"Rating improved from {ratings[0]:.1f} to {latest:.1f}."
    else:
        risk = 34.0
        evidence = f"Stable rating around {latest:.1f}/5."

    if signals.goals_total:
        miss_rate = signals.goals_missed / signals.goals_total
        if miss_rate >= 0.34:
            risk = min(100.0, risk + 12.0)
            evidence += f" {signals.goals_missed}/{signals.goals_total} goals missed."
    return risk, evidence


def _engagement(signals: EmployeeSignals):
    parts: List[float] = []
    evidence_bits: List[str] = []

    if signals.engagement_score is not None:
        parts.append(100.0 - max(0.0, min(100.0, signals.engagement_score)))
        evidence_bits.append(f"engagement survey {signals.engagement_score:.0f}/100")

    if signals.average_feedback_sentiment is not None:
        # Map -1..1 onto 100..0.
        sentiment_risk = (1.0 - max(-1.0, min(1.0, signals.average_feedback_sentiment))) * 50.0
        parts.append(sentiment_risk)
        evidence_bits.append(f"feedback sentiment {signals.average_feedback_sentiment:+.2f}")

    if not parts:
        return None
    return sum(parts) / len(parts), "Based on " + " and ".join(evidence_bits) + "."


def _attendance(signals: EmployeeSignals):
    if signals.unplanned_absence_rate is None:
        return None
    rate = signals.unplanned_absence_rate
    risk = _interpolate(
        rate, ((0.0, 10.0), (0.03, 32.0), (0.07, 55.0), (0.12, 78.0), (0.20, 92.0))
    )
    evidence = f"{rate * 100:.1f}% unplanned absence."
    if signals.late_arrival_rate is not None and signals.late_arrival_rate > 0.15:
        risk = min(100.0, risk + 10.0)
        evidence += f" Late on {signals.late_arrival_rate * 100:.0f}% of days."
    return risk, evidence


def _workload(signals: EmployeeSignals):
    overtime = signals.average_weekly_overtime
    if overtime is None:
        return None
    risk = _interpolate(
        overtime, ((0.0, 15.0), (3.0, 35.0), (6.0, 58.0), (10.0, 80.0), (15.0, 93.0))
    )
    return risk, f"{overtime:.1f}h average weekly overtime."


def _compensation(signals: EmployeeSignals):
    ratio = signals.compa_ratio
    if ratio is None:
        return None
    risk = _interpolate(
        ratio, ((0.80, 88.0), (0.90, 66.0), (0.95, 48.0), (1.00, 28.0), (1.10, 14.0))
    )
    evidence = f"Compa-ratio {ratio:.2f} ({'below' if ratio < 1 else 'at or above'} band midpoint)."

    ratings = [float(r) for r in signals.performance_ratings if r is not None]
    if ratings and ratings[-1] >= 4.0 and ratio < 0.97:
        # The classic under-paid high performer: highest-value, most winnable save.
        risk = min(100.0, risk + 15.0)
        evidence += f" High performer ({ratings[-1]:.1f}/5) paid below midpoint."
    return risk, evidence


def _team_attrition(signals: EmployeeSignals):
    rate = signals.department_attrition_rate_12m
    if rate is None:
        return None
    risk = _interpolate(
        rate, ((0.0, 10.0), (0.08, 38.0), (0.16, 62.0), (0.25, 82.0), (0.40, 94.0))
    )
    return risk, f"{rate * 100:.0f}% of the department left in the last 12 months."


def _market_pull(signals: EmployeeSignals):
    skills = [canonical_skill(s) for s in signals.skills if s]
    if not skills:
        return None
    hot = [s for s in skills if s in HOT_MARKET_SKILLS]
    share = len(hot) / len(skills)
    risk = _interpolate(share, ((0.0, 20.0), (0.25, 42.0), (0.5, 62.0), (0.75, 78.0), (1.0, 85.0)))

    # A share computed from two recorded skills is not evidence of high market
    # pull, it is evidence of a thin skill profile. Damp towards neutral when the
    # sample is small so sparse data cannot manufacture risk.
    evidence_weight = min(1.0, len(skills) / 4.0)
    risk = 30.0 + (risk - 30.0) * evidence_weight

    if hot:
        evidence = f"Holds in-demand skills: {', '.join(hot[:4])}"
        if evidence_weight < 1.0:
            evidence += f" (only {len(skills)} skills on record, so this signal is damped)"
        evidence += "."
    else:
        evidence = "No high-demand skills recorded."
    return risk, evidence


_SIGNAL_FUNCTIONS = {
    "tenure_stage": _tenure_stage,
    "career_stagnation": _career_stagnation,
    "performance_trend": _performance_trend,
    "engagement": _engagement,
    "attendance": _attendance,
    "workload": _workload,
    "compensation": _compensation,
    "team_attrition": _team_attrition,
    "market_pull": _market_pull,
}


# --------------------------------------------------------------------------
# Retention actions
# --------------------------------------------------------------------------
_ACTION_TEMPLATES: Dict[str, tuple[str, str]] = {
    "career_stagnation": (
        "Run a career and promotion review",
        "Manager",
    ),
    "compensation": (
        "Run an off-cycle compensation review",
        "HR / Compensation",
    ),
    "workload": (
        "Rebalance workload and audit on-call load",
        "Manager",
    ),
    "engagement": (
        "Hold a structured retention 1:1",
        "Manager",
    ),
    "performance_trend": (
        "Agree a performance support plan and re-scope goals",
        "Manager",
    ),
    "attendance": (
        "Wellbeing check-in with HR partner",
        "HR",
    ),
    "team_attrition": (
        "Stabilise the team: backfill plan and workload redistribution",
        "Department head",
    ),
    "market_pull": (
        "Retention conversation covering growth path and recognition",
        "Manager",
    ),
    "tenure_stage": (
        "Structured early-tenure check-in",
        "Manager / Buddy",
    ),
}


def _build_actions(factors: List[RiskFactor], risk_score: float) -> List[RetentionAction]:
    """
    Turn the highest-contributing factors into concrete actions.

    `expected_risk_reduction` estimates what the overall score would fall by if
    the factor were brought down to a healthy level (risk 25), so HR can
    prioritise by impact rather than by raw factor size.

    Employees in the `low` band get no actions: generating retention work for
    somebody who is not at risk buries the people who are.
    """
    if risk_score < BAND_THRESHOLDS[-1][0]:
        return []

    actions: List[RetentionAction] = []
    for factor in factors[:4]:
        if factor.risk < 40.0:
            continue
        template = _ACTION_TEMPLATES.get(factor.name)
        if not template:
            continue
        action_text, owner = template

        healthy_risk = 25.0
        reduction = max(0.0, (factor.risk - healthy_risk) * factor.weight)
        if reduction < 1.0:
            continue

        if factor.contribution >= 12.0 or risk_score >= 72.0:
            priority: Literal["high", "medium", "low"] = "high"
        elif factor.contribution >= 6.0:
            priority = "medium"
        else:
            priority = "low"

        actions.append(
            RetentionAction(
                action=action_text,
                rationale=factor.evidence,
                expected_risk_reduction=_round(reduction),
                priority=priority,
                owner=owner,
            )
        )
    return actions


def _band_for(risk_score: float) -> RiskBand:
    for threshold, band in BAND_THRESHOLDS:
        if risk_score >= threshold:
            return band  # type: ignore[return-value]
    return "low"


def assess_attrition_risk(signals: EmployeeSignals) -> AttritionAssessment:
    """Score one employee's flight risk and recommend retention actions."""
    factors: List[RiskFactor] = []

    for name, function in _SIGNAL_FUNCTIONS.items():
        result = function(signals)
        if result is None:
            continue
        risk, evidence = result
        factors.append(
            RiskFactor(
                name=name,
                label=FEATURE_LABELS[name],
                risk=_round(max(0.0, min(100.0, risk))),
                weight=FEATURE_WEIGHTS[name],
                contribution=0.0,
                evidence=evidence,
            )
        )

    total_weight = sum(f.weight for f in factors)
    if total_weight > 0:
        risk_score = sum(f.risk * f.weight for f in factors) / total_weight
        for factor in factors:
            # Renormalised weight, and the points this factor adds to the score.
            factor.weight = _round(factor.weight / total_weight)
            factor.contribution = _round(factor.risk * factor.weight)
    else:
        risk_score = 0.0

    risk_score = _round(max(0.0, min(100.0, risk_score)))
    band = _band_for(risk_score)

    factors.sort(key=lambda f: f.contribution, reverse=True)
    drivers = [f for f in factors if f.risk >= 40.0]
    protective = sorted([f for f in factors if f.risk < 30.0], key=lambda f: f.risk)

    available = len(factors)
    total_signals = len(FEATURE_WEIGHTS)
    if available >= 7:
        confidence: Literal["high", "medium", "low"] = "high"
    elif available >= 5:
        confidence = "medium"
    else:
        confidence = "low"

    if drivers:
        top = drivers[0]
        summary = (
            f"{band.capitalize()} risk ({risk_score:.0f}/100). "
            f"Largest driver: {top.label.lower()} — {top.evidence}"
        )
    else:
        summary = f"{band.capitalize()} risk ({risk_score:.0f}/100). No individual signal is elevated."

    return AttritionAssessment(
        employee_id=signals.employee_id,
        full_name=signals.full_name,
        department=signals.department,
        job_title=signals.job_title,
        risk_score=risk_score,
        risk_band=band,
        confidence=confidence,
        factors=factors,
        protective_factors=protective,
        recommended_actions=_build_actions(drivers, risk_score),
        signals_available=available,
        signals_total=total_signals,
        summary=summary,
    )


def assess_many(signals: Sequence[EmployeeSignals]) -> List[AttritionAssessment]:
    """Assess a population, highest risk first."""
    assessments = [assess_attrition_risk(s) for s in signals]
    assessments.sort(key=lambda a: a.risk_score, reverse=True)
    return assessments


def attrition_overview(assessments: Sequence[AttritionAssessment]) -> Dict[str, object]:
    """
    Aggregate a population into the numbers an HR lead acts on: band
    distribution, worst departments, and which drivers dominate org-wide.
    """
    bands: Dict[str, int] = {"low": 0, "moderate": 0, "high": 0, "critical": 0}
    department_scores: Dict[str, List[float]] = {}
    driver_totals: Dict[str, List[float]] = {}

    for assessment in assessments:
        bands[assessment.risk_band] = bands.get(assessment.risk_band, 0) + 1
        department_scores.setdefault(assessment.department or "Unassigned", []).append(
            assessment.risk_score
        )
        for factor in assessment.factors:
            driver_totals.setdefault(factor.name, []).append(factor.contribution)

    departments = [
        {
            "department": name,
            "employees": len(scores),
            "average_risk": _round(sum(scores) / len(scores)),
            "at_risk": sum(1 for s in scores if s >= 55.0),
        }
        for name, scores in department_scores.items()
    ]
    departments.sort(key=lambda d: d["average_risk"], reverse=True)  # type: ignore[arg-type,return-value]

    drivers = [
        {
            "factor": name,
            "label": FEATURE_LABELS.get(name, name),
            "average_contribution": _round(sum(values) / len(values)),
            "employees_affected": sum(1 for v in values if v > 0),
        }
        for name, values in driver_totals.items()
    ]
    drivers.sort(key=lambda d: d["average_contribution"], reverse=True)  # type: ignore[arg-type,return-value]

    scores = [a.risk_score for a in assessments]
    return {
        "employees_assessed": len(assessments),
        "average_risk": _round(sum(scores) / len(scores)) if scores else 0.0,
        "band_distribution": bands,
        "high_risk_count": bands["high"] + bands["critical"],
        "by_department": departments,
        "top_drivers": drivers[:5],
    }
