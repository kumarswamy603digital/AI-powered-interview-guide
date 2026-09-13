from __future__ import annotations

"""
Workforce skill graph.

Maps the skills the organisation *has* (employees) against the skills it *needs*
now and in the future (requirements), and turns the difference into decisions:
which gaps to hire for, which to train for, and which single points of failure
to de-risk.

The graph is emitted as nodes and edges as well as summary rows, so the same
computation drives both a table and a visualisation.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional, Sequence

from app.core.skills import (
    SKILL_CATEGORIES,
    adjacent_skills,
    canonical_skill,
    category_of,
    is_hot_market_skill,
)


CoverageStatus = Literal["surplus", "covered", "at_risk", "critical_gap", "no_demand"]

IMPORTANCE_ORDER = {"core": 3, "important": 2, "nice_to_have": 1}

# Proficiency at or above this counts as production-capable when a requirement
# does not state its own bar.
DEFAULT_REQUIRED_PROFICIENCY = 3


@dataclass
class SkillHolding:
    skill: str
    proficiency: int = 3
    verified: bool = False


@dataclass
class EmployeeSkillProfile:
    employee_id: Optional[int] = None
    full_name: str = ""
    department: str = ""
    job_title: str = ""
    status: str = "active"
    skills: Sequence[SkillHolding] = field(default_factory=tuple)


@dataclass
class RequirementInput:
    skill: str
    department: Optional[str] = None
    role: Optional[str] = None
    importance: str = "important"
    horizon: str = "current"
    required_headcount: int = 1
    required_proficiency: int = DEFAULT_REQUIRED_PROFICIENCY
    target_date: Optional[str] = None
    rationale: Optional[str] = None


@dataclass
class ReskillCandidate:
    employee_id: Optional[int]
    full_name: str
    department: str
    affinity: float
    adjacent_skills_held: List[str]
    reason: str


@dataclass
class SkillNode:
    skill: str
    category: Optional[str]
    total_holders: int
    qualified_holders: int
    average_proficiency: Optional[float]
    verified_holders: int
    demand_current: int
    demand_future: int
    importance: Optional[str]
    coverage_current: Optional[float]
    coverage_future: Optional[float]
    gap_current: int
    gap_future: int
    status: CoverageStatus
    single_point_of_failure: bool
    hot_market_skill: bool
    holders: List[str]
    # Departments of the people who hold the skill.
    departments: List[str]
    # Departments that *require* the skill. Tracked separately because a skill
    # nobody holds has no holder departments, which would otherwise make the
    # worst gaps invisible to any department-level analysis.
    demand_departments: List[str]
    reskilling_candidates: List[ReskillCandidate]
    recommended_action: Optional[str]
    rationale: Optional[str]


@dataclass
class SkillGraph:
    nodes: List[SkillNode]
    edges: List[Dict[str, object]]
    summary: Dict[str, object]


def _round(value: float) -> float:
    return round(float(value), 2)


def _qualified(holding: SkillHolding, required_proficiency: int) -> bool:
    return int(holding.proficiency or 0) >= int(required_proficiency)


def _find_reskill_candidates(
    skill: str,
    *,
    employees: Sequence[EmployeeSkillProfile],
    holder_ids: set,
    limit: int = 3,
) -> List[ReskillCandidate]:
    """
    Employees who could plausibly be trained into a skill they do not hold.

    Affinity is the share of the skill's category the employee already covers.
    Adjacency is a training heuristic, not equivalence - these are candidates for
    development, not substitutes for the skill.
    """
    canonical = canonical_skill(skill)
    category = category_of(canonical)
    if not category:
        return []

    siblings = set(adjacent_skills(canonical))
    if not siblings:
        return []

    candidates: List[ReskillCandidate] = []
    for employee in employees:
        if employee.employee_id in holder_ids or employee.status != "active":
            continue
        held = {canonical_skill(h.skill) for h in employee.skills}
        overlap = sorted(held & siblings)
        if len(overlap) < 2:
            continue
        affinity = _round(len(overlap) / len(siblings) * 100.0)
        candidates.append(
            ReskillCandidate(
                employee_id=employee.employee_id,
                full_name=employee.full_name,
                department=employee.department,
                affinity=affinity,
                adjacent_skills_held=overlap[:5],
                reason=(
                    f"Already works in {category.replace('_', ' ')} "
                    f"({', '.join(overlap[:3])}), so {canonical} is an adjacent step."
                ),
            )
        )

    candidates.sort(key=lambda c: (c.affinity, len(c.adjacent_skills_held)), reverse=True)
    return candidates[:limit]


def _status_for(
    *,
    demand_current: int,
    demand_future: int,
    qualified: int,
    importance: Optional[str],
) -> CoverageStatus:
    total_demand = max(demand_current, demand_future)
    if total_demand == 0:
        return "no_demand"
    if qualified >= total_demand:
        return "surplus" if qualified > total_demand * 1.5 else "covered"

    shortfall_ratio = (total_demand - qualified) / total_demand
    if importance == "core" and (qualified == 0 or shortfall_ratio >= 0.5):
        return "critical_gap"
    if shortfall_ratio >= 0.5:
        return "critical_gap"
    return "at_risk"


def _action_for(node_status: CoverageStatus, *, gap_current: int, gap_future: int,
                reskill: Sequence[ReskillCandidate], spof: bool, skill: str) -> Optional[str]:
    if node_status == "critical_gap":
        if reskill:
            return (
                f"Hire {gap_current or gap_future} for {skill}, and start "
                f"{reskill[0].full_name} on a {skill} development plan in parallel."
            )
        return f"Open a requisition for {skill}: no internal bench exists."
    if node_status == "at_risk":
        if reskill:
            return f"Close the {skill} gap internally: {reskill[0].full_name} is the closest fit."
        return f"Plan recruitment for {skill} before the gap becomes blocking."
    if spof:
        return f"De-risk {skill}: only one qualified person. Cross-train a second."
    if node_status == "surplus" and gap_future == 0:
        return None
    return None


def build_skill_graph(
    employees: Sequence[EmployeeSkillProfile],
    requirements: Sequence[RequirementInput],
) -> SkillGraph:
    """
    Build the supply/demand skill graph for the organisation.

    Includes skills that only appear on the supply side (so surplus capability is
    visible) and skills that only appear on the demand side (so a requirement
    nobody meets cannot hide).
    """
    active = [e for e in employees if e.status == "active"]

    # --- demand side ----------------------------------------------------
    demand_current: Dict[str, int] = {}
    demand_future: Dict[str, int] = {}
    importance: Dict[str, str] = {}
    required_proficiency: Dict[str, int] = {}
    rationales: Dict[str, str] = {}
    target_dates: Dict[str, str] = {}
    demand_departments: Dict[str, set] = {}

    for requirement in requirements:
        skill = canonical_skill(requirement.skill)
        if not skill:
            continue
        if requirement.department:
            demand_departments.setdefault(skill, set()).add(requirement.department)
        headcount = max(1, int(requirement.required_headcount or 1))
        if (requirement.horizon or "current") == "future":
            demand_future[skill] = demand_future.get(skill, 0) + headcount
        else:
            demand_current[skill] = demand_current.get(skill, 0) + headcount

        existing = importance.get(skill)
        candidate_importance = requirement.importance or "important"
        if not existing or IMPORTANCE_ORDER.get(candidate_importance, 0) > IMPORTANCE_ORDER.get(existing, 0):
            importance[skill] = candidate_importance

        required_proficiency[skill] = max(
            required_proficiency.get(skill, DEFAULT_REQUIRED_PROFICIENCY),
            int(requirement.required_proficiency or DEFAULT_REQUIRED_PROFICIENCY),
        )
        if requirement.rationale and skill not in rationales:
            rationales[skill] = requirement.rationale
        if requirement.target_date and skill not in target_dates:
            target_dates[skill] = requirement.target_date

    # --- supply side ----------------------------------------------------
    holdings: Dict[str, List[tuple[EmployeeSkillProfile, SkillHolding]]] = {}
    for employee in active:
        for holding in employee.skills:
            skill = canonical_skill(holding.skill)
            if not skill:
                continue
            holdings.setdefault(skill, []).append((employee, holding))

    all_skills = sorted(set(holdings) | set(demand_current) | set(demand_future))

    nodes: List[SkillNode] = []
    edges: List[Dict[str, object]] = []

    for skill in all_skills:
        entries = holdings.get(skill, [])
        bar = required_proficiency.get(skill, DEFAULT_REQUIRED_PROFICIENCY)
        qualified_entries = [(e, h) for e, h in entries if _qualified(h, bar)]

        current = demand_current.get(skill, 0)
        future = demand_future.get(skill, 0)
        qualified_count = len(qualified_entries)

        coverage_current = (
            _round(min(100.0, qualified_count / current * 100.0)) if current else None
        )
        coverage_future = (
            _round(min(100.0, qualified_count / future * 100.0)) if future else None
        )

        holder_ids = {e.employee_id for e, _ in entries}
        reskill = (
            _find_reskill_candidates(skill, employees=active, holder_ids=holder_ids)
            if (current or future) and qualified_count < max(current, future)
            else []
        )

        skill_importance = importance.get(skill)
        status = _status_for(
            demand_current=current,
            demand_future=future,
            qualified=qualified_count,
            importance=skill_importance,
        )
        spof = qualified_count == 1 and (current + future) > 0 and skill_importance == "core"

        proficiencies = [int(h.proficiency or 0) for _, h in entries if h.proficiency]
        node = SkillNode(
            skill=skill,
            category=category_of(skill),
            total_holders=len(entries),
            qualified_holders=qualified_count,
            average_proficiency=_round(sum(proficiencies) / len(proficiencies)) if proficiencies else None,
            verified_holders=sum(1 for _, h in entries if h.verified),
            demand_current=current,
            demand_future=future,
            importance=skill_importance,
            coverage_current=coverage_current,
            coverage_future=coverage_future,
            gap_current=max(0, current - qualified_count),
            gap_future=max(0, future - qualified_count),
            status=status,
            single_point_of_failure=spof,
            hot_market_skill=is_hot_market_skill(skill),
            holders=[e.full_name for e, _ in entries][:8],
            departments=sorted({e.department for e, _ in entries if e.department}),
            demand_departments=sorted(demand_departments.get(skill, set())),
            reskilling_candidates=reskill,
            recommended_action=_action_for(
                status,
                gap_current=max(0, current - qualified_count),
                gap_future=max(0, future - qualified_count),
                reskill=reskill,
                spof=spof,
                skill=skill,
            ),
            rationale=rationales.get(skill),
        )
        nodes.append(node)

        for employee, holding in entries:
            edges.append(
                {
                    "source": f"employee:{employee.employee_id}",
                    "source_label": employee.full_name,
                    "target": f"skill:{skill}",
                    "target_label": skill,
                    "type": "holds",
                    "proficiency": int(holding.proficiency or 0),
                    "verified": bool(holding.verified),
                }
            )
        if current or future:
            edges.append(
                {
                    "source": f"skill:{skill}",
                    "source_label": skill,
                    "target": "org:requirements",
                    "target_label": "Organisational demand",
                    "type": "required_by",
                    "demand_current": current,
                    "demand_future": future,
                    "importance": skill_importance,
                }
            )

    # --- summary --------------------------------------------------------
    demanded = [n for n in nodes if n.demand_current or n.demand_future]
    critical = [n for n in demanded if n.status == "critical_gap"]
    at_risk = [n for n in demanded if n.status == "at_risk"]
    spofs = [n for n in nodes if n.single_point_of_failure]

    total_current_demand = sum(n.demand_current for n in nodes)
    total_current_met = sum(min(n.qualified_holders, n.demand_current) for n in nodes)
    total_future_demand = sum(n.demand_future for n in nodes)
    total_future_met = sum(min(n.qualified_holders, n.demand_future) for n in nodes)

    category_coverage: Dict[str, Dict[str, int]] = {}
    for node in demanded:
        key = node.category or "uncategorised"
        entry = category_coverage.setdefault(key, {"demand": 0, "qualified": 0, "gap": 0})
        entry["demand"] += max(node.demand_current, node.demand_future)
        entry["qualified"] += node.qualified_holders
        entry["gap"] += max(node.gap_current, node.gap_future)

    summary: Dict[str, object] = {
        "employees_mapped": len(active),
        "skills_tracked": len(nodes),
        "skills_in_demand": len(demanded),
        "current_coverage": _round(total_current_met / total_current_demand * 100.0)
        if total_current_demand
        else None,
        "future_readiness": _round(total_future_met / total_future_demand * 100.0)
        if total_future_demand
        else None,
        "critical_gaps": [
            {
                "skill": n.skill,
                "gap": max(n.gap_current, n.gap_future),
                "importance": n.importance,
                "horizon": "future" if n.gap_future > n.gap_current else "current",
                "action": n.recommended_action,
            }
            for n in sorted(critical, key=lambda n: max(n.gap_current, n.gap_future), reverse=True)
        ][:10],
        "at_risk_skills": [n.skill for n in at_risk][:10],
        "single_points_of_failure": [
            {"skill": n.skill, "holder": n.holders[0] if n.holders else None}
            for n in spofs
        ],
        "category_coverage": [
            {
                "category": name.replace("_", " "),
                "demand": data["demand"],
                "qualified": data["qualified"],
                "gap": data["gap"],
            }
            for name, data in sorted(category_coverage.items(), key=lambda kv: -kv[1]["gap"])
        ],
        "surplus_skills": [n.skill for n in nodes if n.status == "surplus"][:10],
        "untracked_categories": [
            category
            for category in SKILL_CATEGORIES
            if not any((n.category == category) and (n.demand_current or n.demand_future) for n in nodes)
        ],
    }

    nodes.sort(
        key=lambda n: (
            max(n.gap_current, n.gap_future),
            IMPORTANCE_ORDER.get(n.importance or "", 0),
        ),
        reverse=True,
    )

    return SkillGraph(nodes=nodes, edges=edges, summary=summary)
