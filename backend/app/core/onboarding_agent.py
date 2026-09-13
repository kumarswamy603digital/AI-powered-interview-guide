from __future__ import annotations

"""
Adaptive onboarding journey generation.

Produces a personalised 30/60/90 plan from the employee's role, department,
seniority, work mode, location and - the part that makes it adaptive rather than
a checklist - their own skill gaps against what the role requires.

Every task carries a `rationale` explaining why it is in *this* person's plan, so
a manager can see what was tailored and why.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from app.core.skills import canonical_skill, match_skills


PHASES = (
    ("pre_boarding", "Pre-boarding", -7, -1),
    ("week_1", "Week 1", 0, 7),
    ("day_30", "First 30 days", 8, 30),
    ("day_60", "Days 31-60", 31, 60),
    ("day_90", "Days 61-90", 61, 90),
)

PHASE_LABELS = {key: label for key, label, _, _ in PHASES}


@dataclass
class OnboardingProfile:
    employee_id: Optional[int] = None
    full_name: str = ""
    department: str = ""
    job_title: str = ""
    seniority: Optional[str] = None  # junior|mid|senior|lead|principal|manager
    work_mode: Optional[str] = None  # onsite|hybrid|remote
    location: Optional[str] = None
    employment_type: Optional[str] = None  # full_time|contract|intern
    start_date: Optional[str] = None
    manager_name: Optional[str] = None
    buddy_name: Optional[str] = None
    skills: Sequence[str] = field(default_factory=tuple)


@dataclass
class OnboardingTaskPlan:
    title: str
    description: str
    phase: str
    category: str
    day_offset: int
    owner: str
    mandatory: bool
    rationale: str
    resource_url: Optional[str] = None


@dataclass
class PhasePlan:
    phase: str
    label: str
    day_from: int
    day_to: int
    tasks: List[OnboardingTaskPlan]


@dataclass
class OnboardingJourney:
    employee_id: Optional[int]
    full_name: str
    role: str
    department: str
    seniority: Optional[str]
    work_mode: Optional[str]
    buddy_name: Optional[str]
    targeted_skill_gaps: List[str]
    personalization_notes: List[str]
    phases: List[PhasePlan]
    tasks: List[OnboardingTaskPlan]
    mandatory_count: int
    summary: str


# --------------------------------------------------------------------------
# Department-specific ramp content
# --------------------------------------------------------------------------
DEPARTMENT_PLAYBOOKS: Dict[str, List[tuple]] = {
    "engineering": [
        ("Set up local development environment", "week_1", "it_setup", 1, "Engineering", True,
         "Engineering hires cannot contribute until the local build and test suite run."),
        ("Walk through system architecture with a senior engineer", "week_1", "training", 4, "Manager", False,
         "Architecture context shortens the time to a first safe change."),
        ("Ship a first small change to production", "day_30", "role_ramp", 21, "Buddy", False,
         "An early end-to-end change teaches the review, CI and release path."),
        ("Learn the code review and branching conventions", "week_1", "training", 3, "Buddy", True,
         "Review conventions are the most common source of early friction."),
        ("Shadow an on-call rotation", "day_60", "role_ramp", 45, "Manager", False,
         "On-call exposure builds operational ownership before taking a shift."),
    ],
    "data": [
        ("Get warehouse and BI tool access", "week_1", "it_setup", 1, "Data Platform", True,
         "No analysis is possible without warehouse access."),
        ("Complete data governance and PII handling training", "week_1", "compliance", 2, "Compliance", True,
         "Data roles handle regulated personal data from day one."),
        ("Reproduce an existing core dashboard end to end", "day_30", "role_ramp", 18, "Buddy", False,
         "Rebuilding a known output validates understanding of the data model."),
        ("Present a first analysis to the team", "day_60", "role_ramp", 50, "Manager", False,
         "Communicating findings is the core deliverable of the role."),
    ],
    "sales": [
        ("Get CRM access and complete CRM training", "week_1", "it_setup", 1, "Sales Ops", True,
         "Pipeline hygiene depends on correct CRM use from the first call."),
        ("Complete product pitch certification", "day_30", "training", 20, "Sales Enablement", True,
         "Certification gates customer-facing conversations."),
        ("Shadow five customer calls", "week_1", "role_ramp", 5, "Buddy", False,
         "Live calls teach objection handling faster than material does."),
        ("Own a first qualified opportunity", "day_60", "role_ramp", 45, "Manager", False,
         "Ownership with support is the standard ramp for quota-carrying roles."),
    ],
    "people": [
        ("Get HRIS access with the correct permission scope", "week_1", "it_setup", 1, "HR Systems", True,
         "People roles handle employee records and need scoped access."),
        ("Complete confidentiality and data protection training", "week_1", "compliance", 1, "Compliance", True,
         "People data is the most sensitive category the company holds."),
        ("Review the full policy library", "day_30", "training", 15, "HR Lead", False,
         "Policy fluency is required before advising employees."),
    ],
    "finance": [
        ("Get access to the ledger and reporting systems", "week_1", "it_setup", 1, "Finance Systems", True,
         "Core finance systems access gates all downstream work."),
        ("Complete SOX and financial controls training", "week_1", "compliance", 3, "Compliance", True,
         "Controls training is a regulatory requirement for finance roles."),
        ("Run a close checklist alongside a colleague", "day_30", "role_ramp", 25, "Buddy", False,
         "The month-end close is the operating rhythm of the function."),
    ],
    "marketing": [
        ("Get access to analytics, CMS and campaign tools", "week_1", "it_setup", 1, "Marketing Ops", True,
         "Campaign work depends on tooling access."),
        ("Review brand guidelines and tone of voice", "week_1", "training", 2, "Brand", True,
         "Brand consistency is expected on all external output."),
        ("Own one campaign deliverable end to end", "day_60", "role_ramp", 40, "Manager", False,
         "End-to-end ownership surfaces gaps a review cycle would hide."),
    ],
    "support": [
        ("Get helpdesk and knowledge base access", "week_1", "it_setup", 1, "Support Ops", True,
         "Ticket handling requires tooling access on day one."),
        ("Shadow ticket triage", "week_1", "role_ramp", 3, "Buddy", False,
         "Triage judgement is learned by observation."),
        ("Handle tickets independently with review", "day_30", "role_ramp", 20, "Manager", False,
         "Supervised independence is the standard support ramp."),
    ],
}


SENIORITY_PLAYBOOKS: Dict[str, List[tuple]] = {
    "junior": [
        ("Agree a structured learning plan with your mentor", "week_1", "training", 4, "Mentor", False,
         "Early-career hires ramp faster with an explicit learning plan."),
        ("Weekly mentor check-in for the first 90 days", "day_30", "social", 14, "Mentor", False,
         "Frequent feedback loops matter most in a first or second role."),
    ],
    "senior": [
        ("Map key stakeholders and their priorities", "week_1", "role_ramp", 5, "Manager", False,
         "Senior hires are expected to work across teams early."),
        ("Take ownership of a scoped deliverable by day 30", "day_30", "role_ramp", 25, "Manager", False,
         "Senior scope should be real within the first month."),
        ("Complete interviewer training", "day_60", "training", 50, "Talent", False,
         "Senior staff are expected to support hiring."),
    ],
    "lead": [
        ("Hold 1:1s with every team member", "week_1", "manager", 5, "New joiner", True,
         "Leads must build individual relationships before changing anything."),
        ("Review team goals, roadmap and delivery health", "day_30", "manager", 14, "Manager", False,
         "Leads need the current commitments before setting new ones."),
        ("Complete interviewer and performance-cycle training", "day_60", "training", 40, "Talent", True,
         "Leads run hiring loops and review cycles."),
    ],
    "manager": [
        ("Hold 1:1s with every direct report", "week_1", "manager", 5, "New joiner", True,
         "Managers must establish individual trust in week one."),
        ("Get approval, budget and HRIS manager access", "week_1", "it_setup", 2, "HR Systems", True,
         "Managers need approval rights to unblock their team."),
        ("Complete people-management and performance training", "day_30", "compliance", 20, "HR", True,
         "Legal and process training is mandatory before running a review cycle."),
        ("Publish a 90-day plan for the team", "day_60", "manager", 55, "New joiner", False,
         "Teams need visible direction from a new manager."),
    ],
}

WORK_MODE_PLAYBOOKS: Dict[str, List[tuple]] = {
    "remote": [
        ("Confirm home office setup and equipment stipend", "pre_boarding", "it_setup", -3, "IT", True,
         "Remote joiners must be equipped before their first day."),
        ("Read the asynchronous communication norms", "week_1", "training", 2, "Buddy", False,
         "Remote work depends on written, async-first habits."),
        ("Schedule three virtual coffee chats outside your team", "day_30", "social", 12, "Buddy", False,
         "Remote joiners build weaker informal networks without deliberate introductions."),
    ],
    "hybrid": [
        ("Confirm office days and desk booking", "week_1", "it_setup", 0, "Facilities", False,
         "Hybrid schedules need to be agreed with the team to be useful."),
        ("Meet the team in person during your first office week", "week_1", "social", 3, "Manager", False,
         "In-person time early pays off for the rest of the ramp."),
    ],
    "onsite": [
        ("Facilities and safety walkthrough", "week_1", "compliance", 0, "Facilities", True,
         "Site safety orientation is required for onsite staff."),
        ("Team lunch introduction", "week_1", "social", 1, "Buddy", False,
         "Informal introductions accelerate onsite integration."),
    ],
}


# Tasks every joiner gets, regardless of role.
BASE_TASKS: List[tuple] = [
    ("Return signed contract and identity documents", "pre_boarding", "compliance", -5, "HR", True,
     "Required before the first working day."),
    ("Provision accounts, email and SSO", "pre_boarding", "it_setup", -2, "IT", True,
     "Access must exist on day one to avoid a wasted first week."),
    ("Assign an onboarding buddy", "pre_boarding", "social", -2, "Manager", True,
     "A named buddy is the strongest predictor of a smooth first month."),
    ("Welcome session and company orientation", "week_1", "training", 0, "HR", True,
     "Shared context on mission, structure and ways of working."),
    ("Acknowledge the employee handbook and code of conduct", "week_1", "compliance", 1, "HR", True,
     "Policy acknowledgement is a compliance requirement."),
    ("Complete information security and privacy training", "week_1", "compliance", 2, "Security", True,
     "Mandatory before handling company or customer data."),
    ("Submit payroll, tax and benefits enrolment forms", "week_1", "compliance", 2, "Payroll", True,
     "Late submission delays first payroll."),
    ("First 1:1 with your manager", "week_1", "manager", 1, "Manager", True,
     "Sets expectations for the first 30 days."),
    ("Agree 30/60/90 day goals", "week_1", "manager", 4, "Manager", True,
     "Written goals make the ramp measurable instead of impressionistic."),
    ("30-day check-in and feedback conversation", "day_30", "manager", 30, "Manager", True,
     "Catches ramp problems while they are still cheap to fix."),
    ("60-day progress review against goals", "day_60", "manager", 60, "Manager", False,
     "Mid-point correction opportunity."),
    ("90-day review and confirmation of goals for the next cycle", "day_90", "manager", 90, "Manager", True,
     "Formally closes onboarding and starts the normal performance cycle."),
    ("Onboarding experience survey", "day_90", "social", 88, "HR", False,
     "Feeds improvements back into the onboarding programme."),
]


def _phase_for_day(day_offset: int) -> str:
    for key, _label, start, end in PHASES:
        if start <= day_offset <= end:
            return key
    return "day_90" if day_offset > 90 else "pre_boarding"


def _department_key(department: str) -> Optional[str]:
    value = (department or "").strip().lower()
    if not value:
        return None
    aliases = {
        "engineering": "engineering", "technology": "engineering", "product engineering": "engineering",
        "it": "engineering", "software": "engineering",
        "data": "data", "analytics": "data", "data science": "data", "data & analytics": "data",
        "sales": "sales", "revenue": "sales", "business development": "sales",
        "people": "people", "hr": "people", "human resources": "people", "talent": "people",
        "finance": "finance", "accounting": "finance",
        "marketing": "marketing", "growth": "marketing",
        "support": "support", "customer success": "support", "customer support": "support",
    }
    if value in aliases:
        return aliases[value]
    for alias, key in aliases.items():
        if alias in value:
            return key
    return None


def _seniority_key(seniority: Optional[str]) -> Optional[str]:
    value = (seniority or "").strip().lower()
    if not value:
        return None
    if "manager" in value or "head" in value or "director" in value:
        return "manager"
    if "lead" in value or "principal" in value or "staff" in value:
        return "lead"
    if "senior" in value or "sr" in value:
        return "senior"
    if "junior" in value or "jr" in value or "associate" in value or "intern" in value or "graduate" in value:
        return "junior"
    return None


def _make_task(row: Sequence, source_note: str) -> OnboardingTaskPlan:
    title, phase, category, day_offset, owner, mandatory, rationale = row
    return OnboardingTaskPlan(
        title=title,
        description=rationale,
        phase=phase,
        category=category,
        day_offset=int(day_offset),
        owner=owner,
        mandatory=bool(mandatory),
        rationale=f"{source_note} {rationale}".strip(),
    )


def generate_onboarding_journey(
    profile: OnboardingProfile,
    *,
    role_required_skills: Sequence[str] = (),
) -> OnboardingJourney:
    """
    Build a personalised onboarding journey.

    `role_required_skills` normally comes from the skill requirements for the
    employee's role or department; whatever the employee does not already hold
    becomes a targeted training task.
    """
    tasks: List[OnboardingTaskPlan] = []
    notes: List[str] = []

    for row in BASE_TASKS:
        tasks.append(_make_task(row, "Standard for all joiners:"))

    department_key = _department_key(profile.department)
    if department_key:
        for row in DEPARTMENT_PLAYBOOKS[department_key]:
            tasks.append(_make_task(row, f"Because this is a {department_key} role:"))
        notes.append(f"Applied the {department_key} department playbook.")
    elif profile.department:
        notes.append(
            f"No department playbook for '{profile.department}', so only the standard "
            "and role-level tasks were applied."
        )

    seniority_key = _seniority_key(profile.seniority) or _seniority_key(profile.job_title)
    if seniority_key:
        for row in SENIORITY_PLAYBOOKS[seniority_key]:
            tasks.append(_make_task(row, f"Because this is a {seniority_key} hire:"))
        notes.append(f"Applied the {seniority_key} seniority playbook.")

    work_mode = (profile.work_mode or "").strip().lower()
    if work_mode in WORK_MODE_PLAYBOOKS:
        for row in WORK_MODE_PLAYBOOKS[work_mode]:
            tasks.append(_make_task(row, f"Because this is a {work_mode} role:"))
        notes.append(f"Applied {work_mode} working adjustments.")

    if profile.location:
        tasks.append(
            OnboardingTaskPlan(
                title=f"Complete local statutory paperwork for {profile.location}",
                description="Location-specific employment, tax and benefits documentation.",
                phase="week_1",
                category="compliance",
                day_offset=3,
                owner="HR",
                mandatory=True,
                rationale=f"Location-specific: {profile.location} has its own statutory requirements.",
            )
        )

    employment_type = (profile.employment_type or "").strip().lower()
    if employment_type in {"contract", "contractor"}:
        tasks.append(
            OnboardingTaskPlan(
                title="Confirm contract scope, end date and invoicing process",
                description="Contractor-specific commercial and access boundaries.",
                phase="pre_boarding",
                category="compliance",
                day_offset=-3,
                owner="HR / Procurement",
                mandatory=True,
                rationale="Contract engagement: scope and access differ from permanent staff.",
            )
        )
        notes.append("Adjusted for a contract engagement.")
    elif employment_type == "intern":
        tasks.append(
            OnboardingTaskPlan(
                title="Agree internship project scope and success criteria",
                description="A single well-scoped project with a defined outcome.",
                phase="week_1",
                category="role_ramp",
                day_offset=2,
                owner="Manager",
                mandatory=True,
                rationale="Internship: a fixed-term project needs scope agreed immediately.",
            )
        )
        notes.append("Adjusted for a fixed-term internship.")

    # --- skill-gap driven training (the adaptive part) -------------------
    held = [canonical_skill(s) for s in profile.skills if s]
    _, missing = match_skills(role_required_skills, resume_text="", known_skills=held)
    targeted = missing[:4]

    for index, skill in enumerate(targeted):
        tasks.append(
            OnboardingTaskPlan(
                title=f"Complete {skill} ramp-up training",
                description=f"Structured training to reach working proficiency in {skill}.",
                phase="day_30" if index < 2 else "day_60",
                category="skill_gap",
                day_offset=15 + index * 12,
                owner="Manager / L&D",
                mandatory=False,
                rationale=(
                    f"Personalised: {skill} is required for this role but is not evidenced "
                    f"in {profile.full_name or 'the employee'}'s skill profile."
                ),
            )
        )
    if targeted:
        notes.append(
            f"Added {len(targeted)} targeted training task(s) for missing role skills: "
            f"{', '.join(targeted)}."
        )
    elif role_required_skills:
        notes.append("No skill gaps against the role requirements, so no remedial training was added.")

    if profile.buddy_name:
        notes.append(f"Buddy assigned: {profile.buddy_name}.")

    # --- assemble phases ------------------------------------------------
    for task in tasks:
        # Keep phase and day consistent even if a playbook row disagrees.
        task.phase = _phase_for_day(task.day_offset)

    tasks.sort(key=lambda t: (t.day_offset, 0 if t.mandatory else 1, t.title))

    phases: List[PhasePlan] = []
    for key, label, start, end in PHASES:
        phase_tasks = [t for t in tasks if t.phase == key]
        if not phase_tasks:
            continue
        phases.append(
            PhasePlan(phase=key, label=label, day_from=start, day_to=end, tasks=phase_tasks)
        )

    mandatory_count = sum(1 for t in tasks if t.mandatory)
    summary = (
        f"{len(tasks)}-task journey for {profile.full_name or 'new joiner'} "
        f"({profile.job_title or 'role'}, {profile.department or 'unassigned'}), "
        f"{mandatory_count} mandatory, across {len(phases)} phases"
    )
    if targeted:
        summary += f", including targeted training for {', '.join(targeted)}"
    summary += "."

    return OnboardingJourney(
        employee_id=profile.employee_id,
        full_name=profile.full_name,
        role=profile.job_title,
        department=profile.department,
        seniority=profile.seniority,
        work_mode=profile.work_mode,
        buddy_name=profile.buddy_name,
        targeted_skill_gaps=targeted,
        personalization_notes=notes,
        phases=phases,
        tasks=tasks,
        mandatory_count=mandatory_count,
        summary=summary,
    )


def journey_progress(tasks: Sequence[Dict[str, object]]) -> Dict[str, object]:
    """
    Summarise progress over stored onboarding tasks.

    Accepts plain dicts (as read from the database) so the API layer does not need
    to rebuild dataclasses just to compute a percentage.
    """
    total = len(tasks)
    done = sum(1 for t in tasks if str(t.get("status")) == "done")
    mandatory = [t for t in tasks if t.get("mandatory")]
    mandatory_done = sum(1 for t in mandatory if str(t.get("status")) == "done")

    by_phase: Dict[str, Dict[str, int]] = {}
    for task in tasks:
        phase = str(task.get("phase") or "week_1")
        entry = by_phase.setdefault(phase, {"total": 0, "done": 0})
        entry["total"] += 1
        if str(task.get("status")) == "done":
            entry["done"] += 1

    return {
        "total_tasks": total,
        "completed_tasks": done,
        "completion_percent": round(done / total * 100.0, 2) if total else 0.0,
        "mandatory_total": len(mandatory),
        "mandatory_completed": mandatory_done,
        "mandatory_outstanding": [
            str(t.get("title")) for t in mandatory if str(t.get("status")) != "done"
        ],
        "by_phase": [
            {
                "phase": phase,
                "label": PHASE_LABELS.get(phase, phase),
                "total": data["total"],
                "completed": data["done"],
                "completion_percent": round(data["done"] / data["total"] * 100.0, 2)
                if data["total"]
                else 0.0,
            }
            for phase, data in by_phase.items()
        ],
    }
