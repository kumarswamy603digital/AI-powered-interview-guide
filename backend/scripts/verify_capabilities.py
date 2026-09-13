"""
Behavioural verification of all eight Track 1 capabilities.

Executes the real engine code against fixture data and asserts the outputs.
FastAPI/SQLAlchemy/pydantic are unavailable in this sandbox, so a minimal
pydantic stand-in is provided (attribute assignment only, no validation) purely
so the interview engine's schema objects can be constructed. Everything else is
the production code path.
"""

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

RESULTS: Dict[str, List[tuple]] = {}
CURRENT = ""


def feature(name: str) -> None:
    global CURRENT
    CURRENT = name
    RESULTS.setdefault(name, [])
    print()
    print("=" * 74)
    print(name)
    print("=" * 74)


def check(label: str, ok: bool, detail: str = "") -> None:
    RESULTS[CURRENT].append((label, bool(ok), detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + ("" if ok else f"   << {detail}"))


# --------------------------------------------------------------------------
# Minimal stand-ins for the uninstallable third-party packages
# --------------------------------------------------------------------------
def _missing(module_name: str) -> bool:
    try:
        importlib.import_module(module_name)
        return False
    except ImportError:
        return True


def _passthrough(*_a, **_k):
    return None


class _FakeBase:
    """Attribute-bag stand-in for pydantic.BaseModel (no validation)."""

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

    @classmethod
    def model_validate(cls, data):
        return cls(**data) if isinstance(data, dict) else data

    def model_dump(self, **_kwargs):
        return dict(self.__dict__)


def _fake_field(default=None, **kwargs):
    if "default_factory" in kwargs:
        return kwargs["default_factory"]()
    return kwargs.get("default", default)


def _install_stubs_if_missing() -> List[str]:
    """
    Stub only the packages that are genuinely absent.

    When the real dependencies are installed these stubs are never used, so this
    script exercises the production code path as-is. Stubs exist so the engines
    can still be verified in an environment without network access.
    """
    stubbed: List[str] = []

    if _missing("sqlalchemy"):
        sa = types.ModuleType("sqlalchemy")
        for name in ("JSON", "Column", "Date", "DateTime", "Float", "ForeignKey",
                     "Integer", "String", "Text", "Boolean", "create_engine", "func",
                     "UniqueConstraint"):
            setattr(sa, name, _passthrough)
        orm = types.ModuleType("sqlalchemy.orm")
        orm.relationship = _passthrough
        orm.sessionmaker = _passthrough
        orm.declarative_base = lambda: type("Base", (), {})
        orm.Session = object
        sa.orm = orm
        exc = types.ModuleType("sqlalchemy.exc")
        exc.IntegrityError = type("IntegrityError", (Exception,), {})
        sys.modules["sqlalchemy"] = sa
        sys.modules["sqlalchemy.orm"] = orm
        sys.modules["sqlalchemy.exc"] = exc
        stubbed.append("sqlalchemy")

    if _missing("pydantic"):
        pyd = types.ModuleType("pydantic")
        pyd.BaseModel = _FakeBase
        pyd.Field = _fake_field
        pyd.EmailStr = str
        pyd.AnyHttpUrl = str
        pyd.field_validator = lambda *a, **k: (lambda fn: fn)
        pyd.model_validator = lambda *a, **k: (lambda fn: fn)
        sys.modules["pydantic"] = pyd
        stubbed.append("pydantic")

    if _missing("pydantic_settings"):
        pyds = types.ModuleType("pydantic_settings")
        pyds.BaseSettings = object
        sys.modules["pydantic_settings"] = pyds
        stubbed.append("pydantic_settings")

    return stubbed


STUBBED = _install_stubs_if_missing()
if STUBBED:
    print(f"note: stubbed missing packages {STUBBED} — engine logic is still the real code")
else:
    print("note: all dependencies present; running against the real libraries")


# ==========================================================================
# 1. AI RECRUITMENT INTELLIGENCE ENGINE
# ==========================================================================
from app.core.ranking import (  # noqa: E402
    CandidateEvidence,
    JobRequirements,
    aggregate_skill_gaps,
    rank_candidates,
)
from app.core.skills import extract_skills  # noqa: E402

feature("1. AI RECRUITMENT INTELLIGENCE ENGINE — ranks candidates on resumes, job requirements, skill relevance")

job = JobRequirements(
    id=1, title="Senior Backend Engineer",
    required_skills=["Python", "FastAPI", "PostgreSQL", "Kubernetes", "AWS"],
    preferred_skills=["Terraform"], min_years_experience=5,
)
strong_resume = ("Aisha Kapoor. 7 years of experience. SKILLS: Python, FastAPI, PostgreSQL, "
                 "Kubernetes, AWS, Terraform, Redis, Observability.")
weak_resume = "Dev Sharma. 3 years of experience with Python and Flask. SKILLS: Python, Flask, MySQL."
bluffer_resume = ("Rohan Gupta. 6 years. SKILLS: Python, FastAPI, PostgreSQL, Kubernetes, AWS, Docker.")

ranked = rank_candidates([
    CandidateEvidence(id=1, full_name="Aisha Kapoor", resume_text=strong_resume,
                      extracted_skills=extract_skills(strong_resume), years_experience=7,
                      interview_score=88.0, interview_skill_scores={"System design": 92.0,
                      "Technical depth": 88.0, "Communication": 84.0}, interviews_completed=1),
    CandidateEvidence(id=2, full_name="Rohan Gupta", resume_text=bluffer_resume,
                      extracted_skills=extract_skills(bluffer_resume), years_experience=6,
                      interview_score=43.0, interview_skill_scores={"Technical depth": 38.0},
                      interviews_completed=1),
    CandidateEvidence(id=3, full_name="Dev Sharma", resume_text=weak_resume,
                      extracted_skills=extract_skills(weak_resume), years_experience=3),
], job)
by_name = {r.full_name: r for r in ranked}

check("resume text is parsed into skills", "Kubernetes" in extract_skills(strong_resume))
check("candidates are ranked best-first", ranked[0].full_name == "Aisha Kapoor", ranked[0].full_name)
check("skill relevance scored against job requirements",
      by_name["Aisha Kapoor"].skill_match_score == 100.0 and by_name["Dev Sharma"].skill_match_score == 20.0,
      f"{by_name['Aisha Kapoor'].skill_match_score}/{by_name['Dev Sharma'].skill_match_score}")
check("missing skills are itemised",
      by_name["Dev Sharma"].missing_skills == ["FastAPI", "PostgreSQL", "Kubernetes", "AWS"],
      str(by_name["Dev Sharma"].missing_skills))
check("experience is matched against the minimum",
      by_name["Aisha Kapoor"].experience_match_score is not None)
check("hire recommendation issued for the strong candidate",
      by_name["Aisha Kapoor"].recommendation == "recommend_hire", by_name["Aisha Kapoor"].recommendation)
check("under-qualified candidate rejected by the coverage gate",
      by_name["Dev Sharma"].recommendation == "reject", by_name["Dev Sharma"].recommendation)
check("resume/interview conflict detected on the bluffer",
      "resume_interview_mismatch" in by_name["Rohan Gupta"].flags, str(by_name["Rohan Gupta"].flags))
check("conflict caps the recommendation at further assessment",
      by_name["Rohan Gupta"].recommendation == "further_assessment")
check("every ranking carries human-readable reasoning",
      all(len(r.reasoning) >= 3 for r in ranked))
check("weights renormalise to 1.0 per candidate",
      all(abs(sum(c.weight for c in r.components) - 1.0) < 0.02 for r in ranked))
check("un-interviewed candidate is not penalised for the missing signal",
      by_name["Dev Sharma"].interview_score is None and len(by_name["Dev Sharma"].components) == 2)
gaps = aggregate_skill_gaps(ranked)
check("skill gaps aggregate across the pipeline", len(gaps) >= 1 and gaps[0][1] >= 1, str(gaps[:3]))


# ==========================================================================
# 2. ADAPTIVE ONBOARDING AGENT
# ==========================================================================
from app.core.onboarding_agent import (  # noqa: E402
    OnboardingProfile,
    generate_onboarding_journey,
    journey_progress,
)

feature("2. ADAPTIVE ONBOARDING AGENT — personalised journeys by role, department, employee profile")

senior_remote = generate_onboarding_journey(
    OnboardingProfile(employee_id=10, full_name="Nisha Verma", department="Engineering",
                      job_title="Senior Backend Engineer", seniority="senior", work_mode="remote",
                      location="Bengaluru", employment_type="full_time", buddy_name="Meera Nair",
                      skills=("Python", "PostgreSQL", "Docker")),
    role_required_skills=("Python", "FastAPI", "PostgreSQL", "Kubernetes", "AWS"),
)
junior_onsite = generate_onboarding_journey(
    OnboardingProfile(employee_id=11, full_name="Tanvi D", department="Sales",
                      job_title="Sales Development Rep", seniority="junior", work_mode="onsite",
                      employment_type="intern", skills=()),
    role_required_skills=("Communication",),
)
manager = generate_onboarding_journey(
    OnboardingProfile(employee_id=12, full_name="Deepak Rao", department="Finance",
                      job_title="Finance Manager", seniority="manager", work_mode="hybrid",
                      skills=("Leadership",)),
)
s_titles = [t.title for t in senior_remote.tasks]
j_titles = [t.title for t in junior_onsite.tasks]
m_titles = [t.title for t in manager.tasks]

check("journey spans all five phases (pre-boarding to day 90)", len(senior_remote.phases) == 5)
check("role/department playbook applied (engineering dev env)",
      any("development environment" in t for t in s_titles))
check("seniority playbook applied (senior stakeholder mapping)",
      any("stakeholder" in t.lower() for t in s_titles))
check("work mode adjusts the plan (remote home-office setup)",
      any("home office" in t.lower() for t in s_titles))
check("location drives statutory paperwork", any("Bengaluru" in t for t in s_titles))
check("employee profile drives training: only their own gaps are targeted",
      set(senior_remote.targeted_skill_gaps) == {"FastAPI", "Kubernetes", "AWS"},
      str(senior_remote.targeted_skill_gaps))
check("gap tasks created for each missing skill",
      sum(1 for t in senior_remote.tasks if t.category == "skill_gap") == 3)
check("different profile produces a materially different journey",
      len(set(s_titles) ^ set(j_titles)) > 10)
check("junior gets mentoring, senior does not",
      any("mentor" in t.lower() for t in j_titles) and not any("mentor" in t.lower() for t in s_titles))
check("intern gets scoped project task", any("internship project" in t.lower() for t in j_titles))
check("manager gets direct-report 1:1s and approval access",
      any("direct report" in t.lower() for t in m_titles) and any("approval" in t.lower() for t in m_titles))
check("finance playbook applied for the manager", any("SOX" in t or "ledger" in t for t in m_titles))
check("every task explains why it is in this person's plan",
      all(t.rationale for t in senior_remote.tasks))
check("personalisation is reported to the user",
      len(senior_remote.personalization_notes) >= 4, str(len(senior_remote.personalization_notes)))
check("mandatory compliance tasks present", senior_remote.mandatory_count >= 8)
progress = journey_progress([
    {"title": "A", "phase": "week_1", "status": "done", "mandatory": True},
    {"title": "B", "phase": "week_1", "status": "pending", "mandatory": True},
    {"title": "C", "phase": "day_30", "status": "done", "mandatory": False},
])
check("progress tracking computes completion and outstanding mandatory items",
      progress["completion_percent"] == 66.67 and progress["mandatory_outstanding"] == ["B"],
      str(progress["completion_percent"]))


# ==========================================================================
# 3. HR POLICY REASONING AGENT
# ==========================================================================
from app.core.policy_qa import (  # noqa: E402
    EmployeeContext,
    PolicyChunkInput,
    answer_policy_question,
    split_policy_into_chunks,
)

feature("3. HR POLICY REASONING AGENT — contextual, source-backed answers")

leave_text = """1. Annual Leave
Full-time employees accrue 24 days of annual leave per calendar year, accrued monthly at 2 days per month. Leave must be requested at least 5 working days in advance.

2. Carry-forward
A maximum of 10 unused annual leave days may be carried forward into the next calendar year. Days beyond this limit lapse on 31 December and are not encashed.

3. Sick Leave
Employees are entitled to 12 days of paid sick leave per calendar year. A medical certificate is required for absences longer than 2 consecutive days."""

sections = split_policy_into_chunks(leave_text)
chunks = [PolicyChunkInput(chunk_id=i, policy_id=1, policy_title="Leave Policy", category="leave",
                           section=h, content=b, version="2.1", effective_date="2026-01-01",
                           applies_to="all")
          for i, (h, b) in enumerate(sections, start=1)]
chunks += [
    PolicyChunkInput(chunk_id=50, policy_id=2, policy_title="Remote Work Policy", category="working",
                     section="Eligibility", version="1.3", effective_date="2025-07-01",
                     applies_to="full_time",
                     content="Employees who have completed probation may work remotely up to 3 days per week with manager approval."),
    PolicyChunkInput(chunk_id=51, policy_id=3, policy_title="Travel and Expense Policy",
                     category="finance", section="Reimbursement", version="4.0",
                     effective_date="2025-04-01", applies_to="all",
                     content="Expense claims must be submitted within 30 days of travel with itemised receipts. Claims submitted later than 60 days will not be reimbursed."),
]

check("policy text is auto-split into citable sections", len(sections) == 3, str(len(sections)))
check("section headings are detected",
      any(h and "Carry-forward" in h for h, _ in sections))

a1 = answer_policy_question("How many annual leave days can I carry forward?", chunks, use_llm=False)
check("complex policy query answered", a1.answered)
check("answer contains the correct figure", "10" in a1.answer)
check("answer is source-backed with a citation", len(a1.citations) >= 1 and "[1]" in a1.answer)
check("citation points at the exact clause",
      a1.citations[0].section and "Carry-forward" in a1.citations[0].section, str(a1.citations[0].section))
check("citation carries version and effective date",
      bool(a1.citations[0].version and a1.citations[0].effective_date))

a2 = answer_policy_question("vacation entitlement per year", chunks, use_llm=False)
check("synonym expansion works (vacation -> annual leave)",
      a2.answered and a2.citations[0].policy_title == "Leave Policy")

a3 = answer_policy_question("How late can I submit an expense claim?", chunks, use_llm=False)
check("stemming works (submit matches submitted, claim matches claims)", a3.answered)
check("routed to the correct policy document",
      a3.citations[0].policy_title == "Travel and Expense Policy", a3.citations[0].policy_title)
check("answer cites the actual deadline", "30" in a3.answer or "60" in a3.answer)

a4 = answer_policy_question("What is the policy on cryptocurrency trading?", chunks, use_llm=False)
check("uncovered question is refused, not fabricated", not a4.answered)
check("refusal escalates to a human", "hr partner" in a4.answer.lower())
check("refusal is labelled as such", a4.generated_by == "refusal")

a5 = answer_policy_question(
    "Can I work remotely?", chunks,
    context=EmployeeContext(employee_id=9, full_name="Contract Person",
                            employment_type="contract", location="Remote"),
    use_llm=False)
check("contextual: answer scoped to the employee asking", a5.answered)
check("contextual: caveat raised when policy targets another population",
      len(a5.caveats) >= 1 and "Remote Work Policy" in a5.caveats[0], str(a5.caveats))
check("empty library handled honestly",
      not answer_policy_question("anything", [], use_llm=False).answered)


# ==========================================================================
# 4. EMPLOYEE ATTRITION PREDICTION SYSTEM
# ==========================================================================
from app.core.attrition import (  # noqa: E402
    FEATURE_WEIGHTS,
    EmployeeSignals,
    assess_attrition_risk,
    assess_many,
    attrition_overview,
)

feature("4. EMPLOYEE ATTRITION PREDICTION — workforce patterns and engagement signals")

at_risk = EmployeeSignals(
    employee_id=1, full_name="Ravi Menon", department="Engineering", job_title="Senior Engineer",
    tenure_years=3.6, months_since_last_promotion=43, performance_ratings=(4.2, 4.4, 4.6),
    goals_missed=0, goals_total=3, engagement_score=46, average_feedback_sentiment=-0.1,
    unplanned_absence_rate=0.05, late_arrival_rate=0.04, average_weekly_overtime=9.5,
    compa_ratio=0.87, department_attrition_rate_12m=0.18,
    skills=("Python", "Kubernetes", "AWS", "Terraform"))
healthy = EmployeeSignals(
    employee_id=2, full_name="Meera Nair", department="Engineering", job_title="Engineer",
    tenure_years=5.2, months_since_last_promotion=9, performance_ratings=(4.1, 4.3),
    goals_missed=0, goals_total=2, engagement_score=88, average_feedback_sentiment=0.7,
    unplanned_absence_rate=0.01, average_weekly_overtime=1.0, compa_ratio=1.05,
    department_attrition_rate_12m=0.05, skills=("React", "TypeScript"))
sparse = EmployeeSignals(employee_id=3, full_name="New Joiner", department="Sales",
                         job_title="SDR", tenure_years=0.2)

r = assess_attrition_risk(at_risk)
h = assess_attrition_risk(healthy)
s = assess_attrition_risk(sparse)

check("engagement signals consumed (survey + feedback sentiment)",
      any(f.name == "engagement" for f in r.factors))
check("workforce patterns consumed (attendance, overtime, peer attrition)",
      {"attendance", "workload", "team_attrition"} <= {f.name for f in r.factors})
check("all nine signals used when data is complete", r.signals_available == 9, str(r.signals_available))
check("at-risk employee identified as high/critical", r.risk_band in {"high", "critical"}, r.risk_band)
check("healthy employee scored low", h.risk_band == "low", h.risk_band)
check("risk ordering is correct", r.risk_score > h.risk_score)
check("weights renormalise to 1.0", abs(sum(f.weight for f in r.factors) - 1.0) < 0.02)
check("weights are documented and sum to 1.0", abs(sum(FEATURE_WEIGHTS.values()) - 1.0) < 0.001)
check("career stagnation surfaced as a top driver",
      "career_stagnation" in [f.name for f in r.factors[:2]])
check("underpaid high performer detected",
      any("High performer" in f.evidence for f in r.factors if f.name == "compensation"))
check("every factor carries evidence", all(f.evidence for f in r.factors))
check("retention actions recommended", len(r.recommended_actions) >= 3)
check("actions carry owner and estimated risk reduction",
      all(a.owner and a.expected_risk_reduction > 0 for a in r.recommended_actions))
check("healthy employee needs no intervention", len(h.recommended_actions) == 0)
check("protective factors surfaced for the healthy employee", len(h.protective_factors) >= 3)
check("sparse data lowers confidence instead of inventing risk",
      s.confidence == "low" and s.signals_available <= 2, f"{s.confidence}/{s.signals_available}")

overview = attrition_overview(assess_many([at_risk, healthy, sparse]))
check("org-level view aggregates band distribution",
      sum(overview["band_distribution"].values()) == 3)
check("org-level view ranks departments by risk", len(overview["by_department"]) == 2)
check("org-level view identifies dominant drivers", len(overview["top_drivers"]) >= 3)


# ==========================================================================
# 5. AI PERFORMANCE INTELLIGENCE
# ==========================================================================
from app.core.performance_intel import (  # noqa: E402
    FeedbackInput,
    GoalInput,
    PerformanceSignals,
    ReviewInput,
    analyze_performance,
    score_sentiment,
)

feature("5. AI PERFORMANCE INTELLIGENCE — goals, feedback and history to strengths/improvements")

rising = analyze_performance(PerformanceSignals(
    employee_id=1, full_name="Ravi Menon", department="Engineering", job_title="Senior Engineer",
    reviews=(
        ReviewInput(period="2024-H1", rating=4.2, strengths=("Strong system design work",),
                    improvements=("Documentation is often incomplete",),
                    comments="Reliable and technically strong."),
        ReviewInput(period="2024-H2", rating=4.4, strengths=("Mentored two juniors effectively",),
                    improvements=("Written communication needs work",),
                    comments="Excellent delivery with clear ownership."),
        ReviewInput(period="2025-H1", rating=4.6, strengths=("Led the platform migration",),
                    comments="Outstanding architecture contribution.", promotion_ready="yes"),
    ),
    goals=(GoalInput(title="Migrate billing", status="achieved", progress=100, weight=2.0),
           GoalInput(title="Cut latency", status="achieved", progress=100, weight=1.0),
           GoalInput(title="Test coverage", status="on_track", progress=70, weight=1.0)),
    feedback=(FeedbackInput(source="manager", content="Excellent technical depth. Drove the migration with clear ownership."),
              FeedbackInput(source="peer", content="Very helpful and collaborative. Documentation was unclear at times."),
              FeedbackInput(source="peer", content="Mentoring has been outstanding for the juniors.")),
    department_average_rating=3.9))

falling = analyze_performance(PerformanceSignals(
    employee_id=2, full_name="Sam Fields", department="Sales", job_title="AE",
    reviews=(ReviewInput(period="2024-H1", rating=3.6, comments="Good pipeline discipline."),
             ReviewInput(period="2025-H1", rating=2.5,
                         improvements=("Missed quota consistently", "Delayed client responses"),
                         comments="Struggled with follow-through.")),
    goals=(GoalInput(title="Hit quota", status="missed", progress=40, weight=2.0),
           GoalInput(title="Expand accounts", status="missed", progress=25, weight=1.0)),
    feedback=(FeedbackInput(source="manager", content="Inconsistent updates and delayed responses to clients."),),
    department_average_rating=3.5))

empty = analyze_performance(PerformanceSignals(employee_id=3, full_name="No Data"))

check("goals analysed into weighted attainment",
      90 <= rising.goal_summary.weighted_attainment <= 95, str(rising.goal_summary.weighted_attainment))
check("goal statuses counted", rising.goal_summary.achieved == 2 and falling.goal_summary.missed == 2)
check("performance history yields a trajectory",
      rising.rating_trajectory == "improving" and falling.rating_trajectory == "declining")
check("strengths identified from feedback and reviews", len(rising.strengths) >= 2)
check("strengths are themed and evidenced",
      all(t.theme and t.evidence for t in rising.strengths))
check("improvement areas identified", len(rising.improvement_areas) >= 1)
check("improvement area traced to its source",
      all(t.sources for t in rising.improvement_areas))
check("feedback sentiment computed", rising.feedback_sentiment is not None and rising.feedback_sentiment > 0)
check("sentiment lexicon handles negation",
      (score_sentiment("communication was not clear") or 0) < 0)
check("neutral text yields no false sentiment",
      score_sentiment("Attended the sprint planning meeting") is None)
check("calibrated against the department average",
      rising.calibration == "above" and falling.calibration == "below")
check("promotion readiness inferred, honouring manager judgement",
      rising.promotion_readiness == "ready" and falling.promotion_readiness == "not_yet")
check("actions recommended for the declining performer",
      any("goal" in a.action.lower() for a in falling.recommended_actions)
      and any("decline" in a.action.lower() for a in falling.recommended_actions))
check("promotion action recommended for the strong performer",
      any("promotion" in a.action.lower() for a in rising.recommended_actions))
check("data sources declared",
      set(rising.data_sources) >= {"performance_reviews", "goals", "feedback"})
check("no data is reported honestly, not guessed",
      empty.promotion_readiness == "unknown" and "not enough" in empty.summary.lower())


# ==========================================================================
# 6. WORKFORCE SKILL GRAPH
# ==========================================================================
from app.core.skill_graph import (  # noqa: E402
    EmployeeSkillProfile,
    RequirementInput,
    SkillHolding,
    build_skill_graph,
)

feature("6. WORKFORCE SKILL GRAPH — employee skills vs current and future requirements")

employees = [
    EmployeeSkillProfile(employee_id=1, full_name="Ravi Menon", department="Engineering",
                         job_title="Senior Engineer", skills=[
                             SkillHolding("Python", 5, True), SkillHolding("Kubernetes", 5, True),
                             SkillHolding("AWS", 4, True), SkillHolding("Terraform", 4, False)]),
    EmployeeSkillProfile(employee_id=2, full_name="Meera Nair", department="Engineering",
                         job_title="Engineer", skills=[
                             SkillHolding("React", 5, True), SkillHolding("TypeScript", 5, True)]),
    EmployeeSkillProfile(employee_id=3, full_name="Arjun Das", department="Data",
                         job_title="Data Engineer", skills=[
                             SkillHolding("Python", 4, True), SkillHolding("Spark", 4, True),
                             SkillHolding("Airflow", 3, True), SkillHolding("ETL", 4, True)]),
    EmployeeSkillProfile(employee_id=9, full_name="Departed Person", department="Engineering",
                         job_title="Engineer", status="resigned",
                         skills=[SkillHolding("Kubernetes", 5, True)]),
]
requirements = [
    RequirementInput(skill="Python", department="Engineering", importance="core",
                     horizon="current", required_headcount=2),
    RequirementInput(skill="Kubernetes", department="Engineering", importance="core",
                     horizon="current", required_headcount=2, required_proficiency=4),
    RequirementInput(skill="Machine Learning", department="Data", importance="core",
                     horizon="future", required_headcount=3, required_proficiency=4,
                     target_date="2026-06-30", rationale="Recommendation engine"),
    RequirementInput(skill="LLMs", department="Data", importance="core",
                     horizon="future", required_headcount=2),
]
graph = build_skill_graph(employees, requirements)
nodes = {n.skill: n for n in graph.nodes}

check("employee skills mapped into the graph", graph.summary["employees_mapped"] == 3,
      str(graph.summary["employees_mapped"]))
check("departed employees excluded from supply", nodes["Kubernetes"].qualified_holders == 1)
check("current requirements scored for coverage", nodes["Python"].coverage_current == 100.0)
check("current gap detected", nodes["Kubernetes"].gap_current == 1)
check("FUTURE requirements tracked separately",
      nodes["Machine Learning"].demand_future == 3 and nodes["Machine Learning"].demand_current == 0)
check("future gap flagged as critical with zero holders",
      nodes["Machine Learning"].status == "critical_gap"
      and nodes["Machine Learning"].qualified_holders == 0)
check("future readiness computed org-wide", graph.summary["future_readiness"] is not None)
check("single point of failure detected on a core skill",
      nodes["Kubernetes"].single_point_of_failure)
check("reskilling candidate proposed for the future gap",
      len(nodes["Machine Learning"].reskilling_candidates) >= 1)
check("reskilling candidate is the adjacent-skill employee",
      nodes["Machine Learning"].reskilling_candidates[0].full_name == "Arjun Das",
      str([c.full_name for c in nodes["Machine Learning"].reskilling_candidates]))
check("reskilling suggestion explains the adjacency",
      "adjacent" in nodes["Machine Learning"].reskilling_candidates[0].reason.lower())
check("requirement departments retained even with zero holders",
      nodes["Machine Learning"].demand_departments == ["Data"],
      str(nodes["Machine Learning"].demand_departments))
check("action recommended for every critical gap",
      all(n.recommended_action for n in graph.nodes if n.status == "critical_gap"))
check("graph emits nodes and edges for visualisation",
      len(graph.nodes) >= 6 and len(graph.edges) >= 10)
check("supply-only skills retained (surplus visible)", "React" in nodes)
check("proficiency bar respected (requires 4, holder has 4)",
      nodes["Kubernetes"].qualified_holders == 1)
check("coverage summarised by skill category",
      len(graph.summary["category_coverage"]) >= 2)


# ==========================================================================
# 7. INTELLIGENT INTERVIEW AGENT
# ==========================================================================
from app.core.interview_plan import generate_interview_plan  # noqa: E402
from app.core.live_interview import next_question_mock  # noqa: E402
from app.core.answer_evaluation import evaluate_answer  # noqa: E402
from app.core.report import generate_report  # noqa: E402

feature("7. INTELLIGENT INTERVIEW AGENT — role-specific questions, response evaluation, structured insights")

plan = generate_interview_plan(resume_text=strong_resume, target_role="Senior Backend Engineer",
                               difficulty="hard")
check("interview plan generated for the role", len(plan.interview_structure) >= 4)
check("plan includes system design for a hard backend loop",
      any("design" in r.round_name.lower() for r in plan.interview_structure))
check("question categories allocated to 100%",
      sum(c.percentage for c in plan.question_categories) == 100,
      str(sum(c.percentage for c in plan.question_categories)))
check("time allocation provided", len(plan.time_allocation) >= 4)
check("difficulty changes the plan",
      generate_interview_plan(resume_text=strong_resume, target_role="Senior Backend Engineer",
                              difficulty="easy").interview_structure[0].round_name
      != plan.interview_structure[0].round_name)

q1 = next_question_mock(target_role="Senior Backend Engineer", difficulty="medium",
                        personality_mode="friendly", question_index=0, last_answer=None,
                        max_questions=8)
q2 = next_question_mock(
    target_role="Senior Backend Engineer", difficulty="medium",
    personality_mode="friendly", question_index=1,
    last_answer=("We ran the services on Kubernetes with horizontal pod autoscaling, and moved "
                 "session state into Redis so pods could be replaced without dropping requests. "
                 "That cut p99 latency by about 40%."),
    max_questions=8)
short = next_question_mock(target_role="Senior Backend Engineer", difficulty="medium",
                           personality_mode="strict", question_index=1, last_answer="Yes.",
                           max_questions=8)
check("role-specific question generated", bool(q1.question))
check("questions advance through the interview", q1.question != q2.question)
check("short answer triggers a follow-up probe", short.is_follow_up, str(short.is_follow_up))
check("substantive answer does not trigger a follow-up", not q2.is_follow_up)

evaluation = evaluate_answer(
    question="How would you design a rate limiter?",
    answer=("I would use a token bucket in Redis with a Lua script for atomicity, "
            "size the bucket per tenant, and fall back to local counters if Redis is unavailable."),
    target_role="Senior Backend Engineer")
weak_eval = evaluate_answer(question="How would you design a rate limiter?", answer="Not sure.",
                            target_role="Senior Backend Engineer")
off_topic_eval = evaluate_answer(question="How would you design a rate limiter?",
                                 answer="I really enjoy working in teams and I am a fast learner.",
                                 target_role="Senior Backend Engineer")
echo_eval = evaluate_answer(question="How would you design a rate limiter?",
                            answer="I would design a rate limiter.",
                            target_role="Senior Backend Engineer")
shallow_eval = evaluate_answer(question="How would you design a rate limiter?",
                               answer="Use Redis for rate limiting.",
                               target_role="Senior Backend Engineer")

check("responses are evaluated across relevance/depth/clarity/confidence",
      all(v is not None for v in (evaluation.relevance, evaluation.depth,
                                  evaluation.clarity, evaluation.confidence)))
check("solid answer outscores every weak answer",
      all(evaluation.overall_score > other.overall_score + 10
          for other in (shallow_eval, off_topic_eval, echo_eval, weak_eval)),
      f"solid={evaluation.overall_score} weak={[shallow_eval.overall_score, off_topic_eval.overall_score, echo_eval.overall_score, weak_eval.overall_score]}")

quantified_eval = evaluate_answer(
    question="How would you design a rate limiter?",
    answer=("I would use a token bucket in Redis with a Lua script for atomicity, because that keeps "
            "the check atomic across pods. I sized the bucket per tenant, which cut rejected "
            "requests by 30%."),
    target_role="Senior Backend Engineer")
check("reasoning and quantified impact are rewarded over an unquantified answer",
      quantified_eval.overall_score > evaluation.overall_score + 10,
      f"quantified={quantified_eval.overall_score} vs unquantified={evaluation.overall_score}")
check("on-topic-but-shallow outscores fluent off-topic (substance over polish)",
      shallow_eval.overall_score > off_topic_eval.overall_score,
      f"{shallow_eval.overall_score} vs {off_topic_eval.overall_score}")
check("answer that only echoes the question is not credited as relevant",
      echo_eval.overall_score < shallow_eval.overall_score,
      f"{echo_eval.overall_score} vs {shallow_eval.overall_score}")
check("non-answer scores lowest of all", weak_eval.overall_score == min(
    e.overall_score for e in (evaluation, shallow_eval, off_topic_eval, echo_eval, weak_eval)))
check("non-answer is penalised on relevance and confidence",
      weak_eval.relevance <= 15 and weak_eval.confidence <= 20,
      f"{weak_eval.relevance}/{weak_eval.confidence}")
check("depth rewards quantified, reasoned answers", evaluation.depth > shallow_eval.depth + 20)
check("feedback names the weakest dimension and is specific",
      "Weakest area" in shallow_eval.feedback and len(shallow_eval.feedback) > 60)

report = generate_report(interview_id=1, target_role="Senior Backend Engineer", difficulty="hard",
                         personality_mode="friendly",
                         transcript=[{"role": "assistant", "content": q1.question},
                                     {"role": "user", "content": "Detailed answer about Kubernetes."}])
check("structured interview insight produced (skill breakdown)", len(report.skill_breakdown) >= 3)
check("insight includes strengths and improvement areas",
      len(report.strengths) >= 1 and len(report.weaknesses) >= 1)
check("skill scores are bounded 0-100",
      all(0 <= s.score <= 100 for s in report.skill_breakdown))
overall = sum(s.score for s in report.skill_breakdown) / len(report.skill_breakdown)
check("overall score derivable for persistence and ranking", 0 < overall <= 100, str(overall))


# ==========================================================================
# 8. HR DECISION DASHBOARD
# ==========================================================================
from app.core import decision_dashboard as dd  # noqa: E402

feature("8. HR DECISION DASHBOARD — recruitment + attendance + performance + workforce -> actions")

assessments = assess_many([at_risk, healthy])
performance_list = [rising]
dash_graph = build_skill_graph(employees, requirements + [
    RequirementInput(skill="Security", department="Engineering", importance="core",
                     horizon="future", required_headcount=2)])
recruitment = {"required_skills_by_job": {"1": ["Python", "Machine Learning", "PyTorch"]},
               "conflicts": [{"candidate": "Rohan Gupta", "skill_match": 100.0, "interview": 43.0}]}
attendance = {"overtime_watchlist": [
    {"employee_id": 1, "name": "Ravi Menon", "department": "Engineering",
     "weekly_overtime": 9.5, "absence_rate": 0.05}]}
onboarding = {"with_outstanding_mandatory": [
    {"plan_id": 1, "employee_id": 5, "employee": "Nisha Verma", "completion_percent": 22.0,
     "mandatory_outstanding": ["Complete security training"]}]}
ml_rankings = rank_candidates([
    CandidateEvidence(id=1, full_name="Divya Suresh",
                      resume_text="Python, Machine Learning, PyTorch, LLMs. 4 years of experience.",
                      extracted_skills=["Python", "Machine Learning", "PyTorch", "LLMs"],
                      years_experience=4.0, interview_score=85.0,
                      interview_skill_scores={"ML depth": 88.0}, interviews_completed=1)],
    JobRequirements(id=1, title="ML Engineer",
                    required_skills=["Python", "Machine Learning", "PyTorch"],
                    min_years_experience=3))

insights = dd._build_insights(
    assessments=assessments, performance=performance_list, graph=dash_graph,
    rankings=ml_rankings, recruitment=recruitment, attendance=attendance,
    onboarding=onboarding,
    employee_skills={1: ["Python", "Kubernetes", "AWS", "Terraform"],
                     2: ["React", "TypeScript"], 3: ["Python", "Spark", "Airflow", "ETL"]})
titles = " | ".join(i.title for i in insights)

check("insights produced from combined sources", len(insights) >= 6, str(len(insights)))
check("ATTRITION x SKILLS: flight risk who is the sole holder of a core skill",
      any("only holder of Kubernetes" in i.title for i in insights), titles)
check("ATTRITION x PERFORMANCE: high performer at risk (regretted attrition)",
      any("High performer at risk" in i.title for i in insights), titles)
check("PERFORMANCE x ATTRITION: promotion-ready but stagnant",
      any("promotion-ready but has stagnated" in i.title for i in insights), titles)
check("SKILLS x RECRUITMENT: critical gap with no open requisition",
      any("Security gap with no open requisition" in i.title for i in insights), titles)
check("SKILLS x RECRUITMENT: a gap already being hired for is NOT re-flagged",
      not any("Machine Learning gap with no open" in i.title for i in insights), titles)
check("RECRUITMENT x SKILLS: candidate who would close a known gap",
      any("would close the" in i.title for i in insights), titles)
check("ATTENDANCE x ATTRITION: burnout signal", any("Burnout risk" in i.title for i in insights), titles)
check("ONBOARDING: outstanding mandatory tasks surfaced",
      any("outstanding mandatory onboarding" in i.title for i in insights), titles)
check("RESUME x INTERVIEW: pipeline conflict surfaced",
      any("resume/interview conflict" in i.title for i in insights), titles)
check("every insight names the sources it reasoned over",
      all(len(i.sources) >= 1 for i in insights))
check("most insights genuinely combine two or more sources",
      sum(1 for i in insights if len(i.sources) >= 2) >= 6,
      str(sum(1 for i in insights if len(i.sources) >= 2)))
check("every insight states a recommended action",
      all(i.recommended_action for i in insights))
check("insights ordered by severity (critical first)",
      [i.severity for i in insights]
      == sorted([i.severity for i in insights],
                key=lambda s: {"critical": 0, "warning": 1, "opportunity": 2, "info": 3}[s]))
check("empty organisation produces no fabricated insights",
      len(dd._build_insights(assessments=[], performance=[], graph=build_skill_graph([], []),
                             rankings=[], recruitment={"required_skills_by_job": {}, "conflicts": []},
                             attendance={"overtime_watchlist": []},
                             onboarding={"with_outstanding_mandatory": []},
                             employee_skills={})) == 0)


# ==========================================================================
# SUMMARY
# ==========================================================================
print()
print("=" * 74)
print("PER-CAPABILITY RESULTS")
print("=" * 74)
total = failed = 0
for name, results in RESULTS.items():
    passed = sum(1 for _l, ok, _d in results if ok)
    total += len(results)
    failed += len(results) - passed
    status = "OK  " if passed == len(results) else "FAIL"
    print(f"  [{status}] {passed:>2}/{len(results):<2}  {name.split(' — ')[0]}")

print()
print(f"TOTAL: {total - failed}/{total} checks passed")
if failed:
    print("\nFAILED CHECKS:")
    for name, results in RESULTS.items():
        for label, ok, detail in results:
            if not ok:
                print(f"  - [{name.split(' — ')[0]}] {label}   << {detail}")
    sys.exit(1)
print("\nALL CAPABILITIES VERIFIED AT ENGINE LEVEL")
