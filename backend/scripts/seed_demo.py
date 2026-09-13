"""
Seed a realistic demo organisation.

Run from the backend directory:

    python -m scripts.seed_demo            # seed (fails if data already exists)
    python -m scripts.seed_demo --reset    # wipe the tables it owns, then seed

The data is shaped to exercise the cross-source reasoning rather than to look
tidy. It deliberately contains:

  * a high performer who is underpaid, stagnant and the only holder of a core
    skill  -> critical cross-source insight
  * an engineer with sustained overtime      -> burnout signal in attendance
  * an employee with a declining rating      -> performance intelligence
  * a future ML/LLM requirement nobody meets -> future skill gap with an
    internal reskilling candidate
  * a candidate whose skills close a real gap
  * a candidate who matches on paper but interviewed badly -> conflict flag
"""

from __future__ import annotations

import argparse
import random
import sys
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from app.core.onboarding_agent import generate_onboarding_journey
from app.core.skills import canonical_skill
from app.core.workforce_intelligence import (
    build_onboarding_profile,
    role_required_skills,
    suggest_buddy,
)
from app.crud.workforce import (
    add_employee_skill,
    bulk_record_attendance,
    create_employee,
    create_feedback,
    create_goal,
    create_onboarding_plan,
    create_policy,
    create_review,
    create_skill_requirement,
)
from app.db.base import Base, init_db
from app.db.session import SessionLocal, engine
from app.models.hr import Candidate, JobRequisition
from app.models.interview import InterviewSession, InterviewTurn
from app.models.onboarding import OnboardingPlan, OnboardingTask
from app.models.performance import Feedback, Goal, PerformanceReview
from app.models.policy import PolicyChunk, PolicyDocument
from app.models.resume import Resume
from app.models.user import User
from app.models.workforce import (
    AttendanceRecord,
    Employee,
    EmployeeSkill,
    SkillRequirement,
)
from app.schemas.user import UserCreate
from app.crud.user import create_user, get_user_by_email


TODAY = date.today()
HR_EMAIL = "hr@demo.local"
HR_PASSWORD = "DemoHr!2026"

# Deterministic so two demo runs produce identical numbers.
RANDOM_SEED = 20260913


def _years_ago(years: float) -> date:
    return TODAY - timedelta(days=int(years * 365.25))


def _months_ago(months: float) -> date:
    return TODAY - timedelta(days=int(months * 30.44))


# --------------------------------------------------------------------------
# Employee definitions
# --------------------------------------------------------------------------
# (name, dept, title, seniority, tenure_yrs, months_since_promo, compa, engagement,
#  work_mode, location, skills[(skill, proficiency, verified)])
EMPLOYEES: List[dict] = [
    # --- Engineering leadership
    dict(name="Ananya Krishnan", dept="Engineering", title="Engineering Manager", seniority="manager",
         tenure=6.5, promo=14, compa=1.08, engagement=82, mode="hybrid", location="Bengaluru",
         skills=[("Leadership", 5, True), ("System Design", 4, True), ("Python", 3, True),
                 ("Project Management", 4, True)]),
    # --- THE headline case: high performer, underpaid, stagnant, sole Kubernetes owner
    dict(name="Ravi Menon", dept="Engineering", title="Senior Backend Engineer", seniority="senior",
         tenure=3.6, promo=43, compa=0.87, engagement=46, mode="remote", location="Kochi",
         skills=[("Python", 5, True), ("Kubernetes", 5, True), ("AWS", 4, True),
                 ("Terraform", 4, True), ("FastAPI", 4, True), ("PostgreSQL", 4, True),
                 ("Observability", 3, False)]),
    # --- burnout case: heavy overtime
    dict(name="Priya Raghavan", dept="Engineering", title="Backend Engineer", seniority="mid",
         tenure=2.1, promo=25, compa=0.95, engagement=58, mode="hybrid", location="Bengaluru",
         skills=[("Python", 4, True), ("FastAPI", 3, True), ("PostgreSQL", 3, True),
                 ("Docker", 3, False), ("Testing", 3, True)]),
    dict(name="Meera Nair", dept="Engineering", title="Senior Frontend Engineer", seniority="senior",
         tenure=5.2, promo=9, compa=1.05, engagement=88, mode="hybrid", location="Bengaluru",
         skills=[("TypeScript", 5, True), ("React", 5, True), ("HTML/CSS", 4, True),
                 ("Testing", 4, True), ("Communication", 4, True)]),
    dict(name="Karthik Iyer", dept="Engineering", title="Frontend Engineer", seniority="mid",
         tenure=1.6, promo=19, compa=0.97, engagement=74, mode="remote", location="Chennai",
         skills=[("JavaScript", 4, True), ("React", 4, True), ("HTML/CSS", 4, True),
                 ("Redux", 3, False)]),
    dict(name="Tanvi Deshpande", dept="Engineering", title="Junior Backend Engineer", seniority="junior",
         tenure=0.7, promo=8, compa=0.93, engagement=79, mode="onsite", location="Pune",
         skills=[("Python", 3, True), ("SQL", 3, True), ("Git", 3, True)]),
    dict(name="Imran Sheikh", dept="Engineering", title="DevOps Engineer", seniority="mid",
         tenure=2.8, promo=33, compa=0.92, engagement=61, mode="remote", location="Hyderabad",
         skills=[("Docker", 4, True), ("CI/CD", 4, True), ("Linux", 4, True),
                 ("AWS", 3, True), ("Terraform", 3, False)]),
    # --- declining performer
    dict(name="Vikram Shetty", dept="Engineering", title="Backend Engineer", seniority="mid",
         tenure=4.0, promo=29, compa=0.99, engagement=52, mode="hybrid", location="Bengaluru",
         skills=[("Java", 4, True), ("Spring Boot", 3, True), ("SQL", 3, True),
                 ("REST APIs", 3, False)]),

    # --- Data
    dict(name="Arjun Das", dept="Data", title="Senior Data Engineer", seniority="senior",
         tenure=4.4, promo=16, compa=1.02, engagement=84, mode="hybrid", location="Bengaluru",
         skills=[("Python", 4, True), ("Spark", 4, True), ("Airflow", 4, True),
                 ("SQL", 5, True), ("ETL", 4, True), ("Snowflake", 3, True)]),
    dict(name="Sneha Kulkarni", dept="Data", title="Data Analyst", seniority="mid",
         tenure=2.3, promo=27, compa=0.94, engagement=71, mode="remote", location="Mumbai",
         skills=[("SQL", 4, True), ("Data Analysis", 4, True), ("Power BI", 3, True),
                 ("Pandas", 3, False)]),
    dict(name="Rohit Bansal", dept="Data", title="Data Scientist", seniority="mid",
         tenure=1.2, promo=14, compa=1.0, engagement=80, mode="hybrid", location="Bengaluru",
         skills=[("Python", 4, True), ("Pandas", 4, True), ("NumPy", 3, True),
                 ("scikit-learn", 3, False), ("Data Analysis", 3, True)]),
    dict(name="Lakshmi Pillai", dept="Data", title="Data Team Lead", seniority="lead",
         tenure=7.1, promo=20, compa=1.11, engagement=86, mode="hybrid", location="Bengaluru",
         skills=[("Leadership", 4, True), ("SQL", 5, True), ("ETL", 4, True),
                 ("Project Management", 4, True), ("Communication", 4, True)]),

    # --- Sales
    dict(name="Deepak Rao", dept="Sales", title="Sales Manager", seniority="manager",
         tenure=5.8, promo=18, compa=1.06, engagement=77, mode="onsite", location="Delhi",
         skills=[("Leadership", 4, True), ("Communication", 5, True),
                 ("Project Management", 3, False)]),
    dict(name="Sam Fields", dept="Sales", title="Account Executive", seniority="mid",
         tenure=2.6, promo=31, compa=0.9, engagement=44, mode="onsite", location="Delhi",
         skills=[("Communication", 3, True)]),
    dict(name="Nikita Joshi", dept="Sales", title="Account Executive", seniority="mid",
         tenure=1.9, promo=22, compa=1.01, engagement=81, mode="hybrid", location="Mumbai",
         skills=[("Communication", 4, True), ("Recruitment", 2, False)]),
    dict(name="Aditya Verma", dept="Sales", title="Sales Development Rep", seniority="junior",
         tenure=0.9, promo=10, compa=0.96, engagement=76, mode="onsite", location="Delhi",
         skills=[("Communication", 3, True)]),

    # --- People / HR
    dict(name="Fatima Ali", dept="People", title="Head of People", seniority="manager",
         tenure=8.2, promo=24, compa=1.12, engagement=89, mode="hybrid", location="Bengaluru",
         skills=[("Leadership", 5, True), ("Recruitment", 5, True), ("HRIS", 4, True),
                 ("Onboarding", 5, True), ("Payroll", 3, True), ("Communication", 5, True)]),
    dict(name="Gaurav Malhotra", dept="People", title="Talent Acquisition Partner", seniority="mid",
         tenure=2.0, promo=24, compa=0.98, engagement=72, mode="remote", location="Gurugram",
         skills=[("Recruitment", 4, True), ("Communication", 4, True), ("HRIS", 3, False)]),
    dict(name="Divya Menon", dept="People", title="HR Operations Specialist", seniority="mid",
         tenure=3.3, promo=38, compa=0.91, engagement=63, mode="onsite", location="Bengaluru",
         skills=[("HRIS", 4, True), ("Payroll", 4, True), ("Onboarding", 3, True)]),

    # --- Finance
    dict(name="Suresh Kumar", dept="Finance", title="Finance Manager", seniority="manager",
         tenure=9.0, promo=30, compa=1.04, engagement=78, mode="onsite", location="Bengaluru",
         skills=[("Leadership", 4, True), ("Project Management", 3, True)]),
    dict(name="Anita Bose", dept="Finance", title="Financial Analyst", seniority="mid",
         tenure=3.1, promo=36, compa=0.93, engagement=66, mode="hybrid", location="Bengaluru",
         skills=[("Data Analysis", 4, True), ("SQL", 3, False), ("Power BI", 3, True)]),

    # --- recent joiner, gets an onboarding plan
    dict(name="Nisha Verma", dept="Engineering", title="Senior Backend Engineer", seniority="senior",
         tenure=0.08, promo=1, compa=1.0, engagement=None, mode="remote", location="Bengaluru",
         skills=[("Python", 4, True), ("PostgreSQL", 4, True), ("Docker", 3, True)]),
]

# Employees who already left; they drive the department attrition-rate signal.
LEAVERS: List[dict] = [
    dict(name="Former Engineer A", dept="Engineering", title="Backend Engineer",
         tenure=2.0, exit_months_ago=3),
    dict(name="Former Engineer B", dept="Engineering", title="DevOps Engineer",
         tenure=1.5, exit_months_ago=7),
    dict(name="Former AE", dept="Sales", title="Account Executive",
         tenure=1.2, exit_months_ago=5),
]

MANAGER_OF = {
    "Engineering": "Ananya Krishnan",
    "Data": "Lakshmi Pillai",
    "Sales": "Deepak Rao",
    "People": "Fatima Ali",
    "Finance": "Suresh Kumar",
}

# Attendance shape per employee: (absence_probability, overtime_hours_per_day, late_probability)
ATTENDANCE_PROFILE: Dict[str, tuple] = {
    "Priya Raghavan": (0.02, 2.1, 0.06),   # burnout: sustained overtime
    "Ravi Menon": (0.05, 1.6, 0.04),       # elevated absence + overtime
    "Sam Fields": (0.11, 0.1, 0.22),       # disengagement pattern
    "Vikram Shetty": (0.07, 0.2, 0.12),
    "Imran Sheikh": (0.03, 1.4, 0.05),
    "Divya Menon": (0.05, 0.3, 0.08),
}
DEFAULT_ATTENDANCE = (0.015, 0.25, 0.03)

# (employee, [(period, rating, strengths, improvements, comments, promotion_ready)])
REVIEWS: Dict[str, List[tuple]] = {
    "Ravi Menon": [
        ("2024-H1", 4.2, ["Strong system design work"], ["Documentation is often incomplete"],
         "Reliable and technically strong across the platform.", "not_yet"),
        ("2024-H2", 4.4, ["Mentored two junior engineers effectively"],
         ["Written communication needs work"],
         "Excellent delivery with clear ownership of the migration.", "not_yet"),
        ("2025-H1", 4.6, ["Led the platform migration end to end"], [],
         "Outstanding architecture contribution and consistent execution.", "yes"),
    ],
    "Meera Nair": [
        ("2024-H2", 4.1, ["Clear communication with product partners"], ["Test coverage could improve"],
         "Consistent and dependable delivery.", "not_yet"),
        ("2025-H1", 4.3, ["Excellent collaboration across teams"], [],
         "Strong quality focus and helpful in code review.", "yes"),
    ],
    "Vikram Shetty": [
        ("2024-H1", 3.7, ["Good knowledge of the legacy stack"], ["Needs to pick up newer tooling"],
         "Solid contributor on maintenance work.", "not_yet"),
        ("2025-H1", 2.7, [], ["Missed several delivery commitments", "Quality issues in recent releases"],
         "Struggled with follow-through and unclear status updates.", "no"),
    ],
    "Arjun Das": [
        ("2024-H2", 4.2, ["Rebuilt the ingestion pipeline"], ["Could delegate more"],
         "Technically excellent and reliable.", "not_yet"),
        ("2025-H1", 4.4, ["Strong ownership of data quality"], [],
         "Outstanding technical depth in the data platform.", "yes"),
    ],
    "Sam Fields": [
        ("2024-H1", 3.6, ["Good pipeline discipline"], ["Needs stronger discovery calls"],
         "Reasonable first full year.", "not_yet"),
        ("2025-H1", 2.5, [], ["Missed quota consistently", "Delayed responses to clients"],
         "Struggled with follow-through and stakeholder updates.", "no"),
    ],
    "Priya Raghavan": [
        ("2024-H2", 3.8, ["Reliable delivery under pressure"], ["Takes on too much personally"],
         "Dependable and thorough.", "not_yet"),
        ("2025-H1", 3.9, ["Improved test discipline"], ["Needs to delegate and protect focus time"],
         "Consistently strong but visibly stretched.", "not_yet"),
    ],
    "Sneha Kulkarni": [
        ("2025-H1", 3.6, ["Clear dashboards and analysis"], ["Deeper statistical grounding needed"],
         "Good analytical work with clear presentation.", "not_yet"),
    ],
    "Rohit Bansal": [
        ("2025-H1", 3.9, ["Learned the stack quickly", "Curious and proactive"], [],
         "Ramped up fast and picked up new technology well.", "not_yet"),
    ],
    "Imran Sheikh": [
        ("2024-H2", 3.7, ["Kept the pipelines stable"], ["Documentation gaps"],
         "Dependable operational work.", "not_yet"),
        ("2025-H1", 3.8, ["Strong incident response"], ["Needs to automate more"],
         "Reliable and improving steadily.", "not_yet"),
    ],
    "Divya Menon": [
        ("2025-H1", 3.4, ["Accurate payroll processing"], ["Slow response on employee queries"],
         "Solid operational delivery with some service delays.", "not_yet"),
    ],
    "Karthik Iyer": [
        ("2025-H1", 3.8, ["Good component quality"], ["Needs more ownership of scope"],
         "Effective and improving.", "not_yet"),
    ],
    "Nikita Joshi": [
        ("2025-H1", 4.2, ["Excellent client relationships", "Exceeded quota"], [],
         "Outstanding stakeholder management and consistent results.", "yes"),
    ],
    "Anita Bose": [
        ("2025-H1", 3.5, ["Accurate reporting"], ["Could automate manual steps"],
         "Reliable analysis with room to modernise the process.", "not_yet"),
    ],
    "Gaurav Malhotra": [
        ("2025-H1", 3.9, ["Strong candidate pipeline"], ["Interview feedback often late"],
         "Good sourcing results and clear communication.", "not_yet"),
    ],
}

# (employee, [(title, status, progress, weight)])
GOALS: Dict[str, List[tuple]] = {
    "Ravi Menon": [
        ("Complete billing service migration", "achieved", 100, 2.0),
        ("Reduce p99 latency by 30%", "achieved", 100, 1.5),
        ("Improve platform test coverage to 80%", "on_track", 70, 1.0),
    ],
    "Priya Raghavan": [
        ("Ship notifications service", "achieved", 100, 2.0),
        ("Reduce on-call pages by 40%", "at_risk", 45, 1.0),
    ],
    "Vikram Shetty": [
        ("Migrate legacy reporting module", "missed", 35, 2.0),
        ("Close top 10 tech-debt items", "missed", 20, 1.0),
        ("Improve release quality", "at_risk", 40, 1.0),
    ],
    "Meera Nair": [
        ("Rebuild the design system", "achieved", 100, 2.0),
        ("Improve Lighthouse score to 95", "achieved", 100, 1.0),
    ],
    "Arjun Das": [
        ("Deliver the streaming ingestion pipeline", "achieved", 100, 2.0),
        ("Cut warehouse cost by 20%", "on_track", 75, 1.0),
    ],
    "Sam Fields": [
        ("Hit Q1 quota", "missed", 40, 2.0),
        ("Expand two enterprise accounts", "missed", 25, 1.5),
    ],
    "Rohit Bansal": [
        ("Deliver churn prediction prototype", "on_track", 65, 1.5),
        ("Complete ML fundamentals training", "achieved", 100, 1.0),
    ],
    "Nikita Joshi": [
        ("Exceed annual quota", "achieved", 100, 2.0),
        ("Launch partner referral motion", "on_track", 80, 1.0),
    ],
    "Imran Sheikh": [
        ("Migrate CI to self-hosted runners", "achieved", 100, 1.5),
        ("Introduce infrastructure-as-code for staging", "on_track", 60, 1.0),
    ],
    "Sneha Kulkarni": [
        ("Automate the weekly revenue report", "achieved", 100, 1.0),
        ("Build the retention dashboard", "on_track", 70, 1.0),
    ],
    "Divya Menon": [
        ("Zero payroll errors for the year", "achieved", 100, 2.0),
        ("Reduce query response time to 24h", "at_risk", 40, 1.0),
    ],
}

# (employee, [(source, content)])
FEEDBACK: Dict[str, List[tuple]] = {
    "Ravi Menon": [
        ("manager", "Excellent technical depth. Drove the platform migration with clear ownership and no drama."),
        ("peer", "Very helpful and collaborative in reviews. Documentation was unclear at times."),
        ("peer", "Mentoring has been outstanding for the junior engineers on the team."),
        ("skip_level", "Consistently reliable. Has raised compensation and progression concerns twice this year."),
    ],
    "Priya Raghavan": [
        ("manager", "Reliable and thorough, but visibly stretched across too many workstreams."),
        ("peer", "Always helpful even when overloaded. Response times have slowed recently."),
    ],
    "Vikram Shetty": [
        ("manager", "Inconsistent updates and delayed delivery on the reporting migration."),
        ("peer", "Knowledge of the legacy system is valuable, but quality issues caused rework."),
    ],
    "Meera Nair": [
        ("manager", "Excellent communication and consistently high quality work."),
        ("peer", "Great collaboration and clear code review feedback. Very dependable."),
    ],
    "Arjun Das": [
        ("manager", "Outstanding technical depth on the data platform. Trusted with the hardest problems."),
        ("peer", "Strong architecture instincts and thorough testing. Documentation could be clearer."),
    ],
    "Sam Fields": [
        ("manager", "Missed forecast repeatedly and client updates have been delayed."),
        ("peer", "Disengaged in team calls recently; avoided taking on the new territory."),
    ],
    "Rohit Bansal": [
        ("manager", "Learned the stack impressively fast and is proactive about new technology."),
        ("peer", "Curious and helpful. Picked up the modelling work quickly."),
    ],
    "Nikita Joshi": [
        ("manager", "Exceptional client relationships and consistently exceeded targets."),
        ("customer", "Clear communication and reliable follow-through on every commitment."),
    ],
    "Divya Menon": [
        ("peer", "Accurate and dependable on payroll. Slow to respond to employee queries."),
    ],
    "Imran Sheikh": [
        ("manager", "Strong incident response and dependable operational ownership."),
    ],
}

# Skill requirements: the demand side of the graph.
REQUIREMENTS: List[dict] = [
    # Current, Engineering
    dict(skill="Python", department="Engineering", role="Backend Engineer", importance="core",
         horizon="current", headcount=4, proficiency=3),
    dict(skill="FastAPI", department="Engineering", role="Backend Engineer", importance="important",
         horizon="current", headcount=3, proficiency=3),
    dict(skill="PostgreSQL", department="Engineering", role="Backend Engineer", importance="core",
         horizon="current", headcount=3, proficiency=3),
    dict(skill="Kubernetes", department="Engineering", importance="core",
         horizon="current", headcount=2, proficiency=4,
         rationale="Production workloads run on Kubernetes"),
    dict(skill="AWS", department="Engineering", importance="core", horizon="current",
         headcount=3, proficiency=3),
    dict(skill="Terraform", department="Engineering", importance="important", horizon="current",
         headcount=2, proficiency=3),
    dict(skill="React", department="Engineering", role="Frontend Engineer", importance="core",
         horizon="current", headcount=2, proficiency=3),
    dict(skill="TypeScript", department="Engineering", role="Frontend Engineer", importance="core",
         horizon="current", headcount=2, proficiency=3),
    dict(skill="Testing", department="Engineering", importance="important", horizon="current",
         headcount=4, proficiency=3),
    dict(skill="Observability", department="Engineering", importance="important", horizon="current",
         headcount=2, proficiency=3),
    # Current, Data
    dict(skill="SQL", department="Data", importance="core", horizon="current", headcount=3, proficiency=4),
    dict(skill="Spark", department="Data", importance="important", horizon="current", headcount=2, proficiency=3),
    dict(skill="Airflow", department="Data", importance="important", horizon="current", headcount=2, proficiency=3),
    # Current, People / Sales / Finance
    dict(skill="Recruitment", department="People", importance="core", horizon="current", headcount=2, proficiency=3),
    dict(skill="HRIS", department="People", importance="important", horizon="current", headcount=2, proficiency=3),
    dict(skill="Communication", department="Sales", importance="core", horizon="current", headcount=4, proficiency=3),
    dict(skill="Data Analysis", department="Finance", importance="important", horizon="current",
         headcount=2, proficiency=3),
    # FUTURE: the strategic gaps
    dict(skill="Machine Learning", department="Data", importance="core", horizon="future",
         headcount=3, proficiency=4, target_months=9,
         rationale="Recommendation engine on the FY27 roadmap"),
    dict(skill="LLMs", department="Data", importance="core", horizon="future",
         headcount=2, proficiency=3, target_months=6,
         rationale="Customer support copilot programme"),
    dict(skill="RAG", department="Engineering", importance="important", horizon="future",
         headcount=2, proficiency=3, target_months=6,
         rationale="Knowledge assistant for the support team"),
    dict(skill="Kafka", department="Data", importance="important", horizon="future",
         headcount=2, proficiency=3, target_months=12,
         rationale="Event-driven architecture migration"),
    dict(skill="Security", department="Engineering", importance="core", horizon="future",
         headcount=2, proficiency=3, target_months=12,
         rationale="SOC 2 readiness programme"),
]

POLICIES: List[dict] = [
    dict(
        title="Leave Policy",
        category="leave",
        version="2.1",
        applies_to="all",
        effective=date(2026, 1, 1),
        content="""1. Annual Leave
Full-time employees accrue 24 days of annual leave per calendar year, accrued monthly at 2 days per month. Leave must be requested at least 5 working days in advance through the HRIS, except in an emergency.

2. Carry-forward
A maximum of 10 unused annual leave days may be carried forward into the next calendar year. Days beyond this limit lapse on 31 December and are not encashed.

3. Sick Leave
Employees are entitled to 12 days of paid sick leave per calendar year. A medical certificate is required for any absence longer than 2 consecutive days.

4. Parental Leave
Primary caregivers are entitled to 26 weeks of paid parental leave. Secondary caregivers are entitled to 6 weeks of paid leave, to be taken within 12 months of birth or adoption.

5. Unpaid Leave
Unpaid leave of up to 3 months may be granted at the discretion of the department head and requires People team approval.""",
    ),
    dict(
        title="Remote Work Policy",
        category="working",
        version="1.3",
        applies_to="full_time",
        effective=date(2025, 7, 1),
        content="""1. Eligibility
Employees who have completed probation may work remotely up to 3 days per week with manager approval. Fully remote arrangements require director approval and are reviewed every 6 months.

2. Equipment
The company provides a laptop and a one-time home office stipend of 25,000 INR for fully remote employees. Equipment remains company property and must be returned on exit.

3. Working Hours
Remote employees must maintain 4 hours of overlap with their team's core hours and keep their calendar current.

4. Location Changes
Any change of work location across a state or national border must be approved in advance because it affects tax and payroll.""",
    ),
    dict(
        title="Travel and Expense Policy",
        category="finance",
        version="4.0",
        applies_to="all",
        effective=date(2025, 4, 1),
        content="""1. Reimbursement
Expense claims must be submitted within 30 days of travel with itemised receipts. Claims submitted later than 60 days will not be reimbursed.

2. Approval Limits
Expenses up to 20,000 INR require manager approval. Anything above requires department head approval before the spend is committed.

3. Travel Class
Domestic flights are economy class. International flights longer than 8 hours may be premium economy with director approval.

4. Accommodation
Hotel spend is capped at 8,000 INR per night in metro cities and 5,000 INR elsewhere.""",
    ),
    dict(
        title="Performance and Promotion Policy",
        category="performance",
        version="3.2",
        applies_to="all",
        effective=date(2026, 1, 1),
        content="""1. Review Cycle
Formal performance reviews run twice a year, in H1 and H2. Every employee receives a rating from 1 to 5 and written feedback from their manager.

2. Promotion Eligibility
Employees must have spent at least 12 months in their current band and hold a rating of 4 or above in the most recent cycle to be considered for promotion.

3. Calibration
Ratings are calibrated across each department to keep standards consistent. Managers must justify any rating that sits more than one point away from the department average.

4. Performance Support
Employees rated below 2.5 enter a documented performance support plan lasting 90 days, with fortnightly checkpoints.""",
    ),
    dict(
        title="Code of Conduct and Grievance Policy",
        category="conduct",
        version="2.0",
        applies_to="all",
        effective=date(2025, 1, 1),
        content="""1. Expected Conduct
All employees are expected to treat colleagues, candidates and customers with respect. Harassment, discrimination and retaliation are grounds for disciplinary action up to termination.

2. Raising a Concern
Concerns may be raised with a manager, the People team, or through the anonymous ethics line. Every report is acknowledged within 2 working days.

3. Investigation
Investigations are conducted by the People team and completed within 30 days where practicable. The complainant and respondent are both informed of the outcome.

4. Confidentiality
Information related to a grievance is shared strictly on a need-to-know basis.""",
    ),
    dict(
        title="Employee Referral Policy",
        category="recruitment",
        version="1.1",
        applies_to="all",
        effective=date(2025, 10, 1),
        content="""1. Eligibility
All employees except the People team and the hiring manager for the role may refer candidates.

2. Referral Bonus
A bonus of 50,000 INR is paid for engineering referrals and 30,000 INR for other roles, once the referred employee completes 90 days of service.

3. Process
Referrals must be submitted through the recruitment system before the candidate applies directly. Duplicate referrals are credited to the earliest submission.""",
    ),
]


# --------------------------------------------------------------------------
# Recruitment demo data
# --------------------------------------------------------------------------
JOBS: List[dict] = [
    dict(
        title="Senior Backend Engineer",
        department="Engineering",
        seniority="Senior",
        location="Bengaluru",
        employment_type="full_time",
        required=["Python", "FastAPI", "PostgreSQL", "Kubernetes", "AWS"],
        preferred=["Terraform", "Observability"],
        min_years=5,
        headcount=2,
        description="Own backend services end to end, from design through production operation.",
    ),
    dict(
        title="Machine Learning Engineer",
        department="Data",
        seniority="Mid",
        location="Bengaluru",
        employment_type="full_time",
        required=["Python", "Machine Learning", "PyTorch", "Pandas"],
        preferred=["LLMs", "RAG"],
        min_years=3,
        headcount=1,
        description="Build and ship models for the recommendation and support-copilot programmes.",
    ),
]

CANDIDATES: List[dict] = [
    dict(
        name="Aisha Kapoor", email="aisha.kapoor@example.com", job=0, years=7.0,
        title="Staff Backend Engineer", source="Referral", stage="interviewed",
        resume="""Aisha Kapoor — Staff Backend Engineer
7 years of experience building distributed backend systems.
SKILLS: Python, FastAPI, PostgreSQL, Kubernetes, AWS, Terraform, Redis, Observability, System Design
EXPERIENCE
Scaleworks — Staff Engineer (2021-2026): Led migration of a monolith to microservices on Kubernetes, cut p99 latency 45%.
Owned Terraform-managed infrastructure and the observability stack (Prometheus, Grafana).
Northwind — Senior Engineer (2019-2021): Built billing services with FastAPI and PostgreSQL.""",
        interview=(88.0, [
            ("System design", 92.0, "Strong architecture reasoning with clear trade-offs"),
            ("Technical depth", 88.0, "Deep Kubernetes and AWS knowledge"),
            ("Communication", 84.0, "Clear and concise"),
            ("Problem solving", 88.0, "Structured approach"),
        ]),
    ),
    dict(
        # Matches on paper, interviews badly -> resume/interview conflict flag.
        name="Rohan Gupta", email="rohan.gupta@example.com", job=0, years=6.0,
        title="Senior Engineer", source="Job board", stage="interviewed",
        resume="""Rohan Gupta — Senior Backend Engineer
6 years of experience.
SKILLS: Python, FastAPI, PostgreSQL, Kubernetes, AWS, Docker, Git
EXPERIENCE
Techlane — Senior Engineer (2020-2026): Worked on microservices deployed with Kubernetes on AWS.
Contributed to FastAPI services backed by PostgreSQL.""",
        interview=(43.0, [
            ("Technical depth", 38.0, "Could not explain the Kubernetes work claimed on the resume"),
            ("System design", 42.0, "Vague on trade-offs and failure modes"),
            ("Communication", 52.0, "Answers lacked specifics"),
        ]),
    ),
    dict(
        # Closes the future ML/LLM gap -> opportunity insight.
        name="Divya Suresh", email="divya.suresh@example.com", job=1, years=4.0,
        title="Machine Learning Engineer", source="Referral", stage="interviewed",
        resume="""Divya Suresh — Machine Learning Engineer
4 years of experience delivering production ML.
SKILLS: Python, Machine Learning, PyTorch, scikit-learn, Pandas, NumPy, LLMs, RAG, AWS
EXPERIENCE
Datacore — ML Engineer (2022-2026): Shipped a recommendation model serving 2M users.
Built a retrieval-augmented generation assistant over internal documentation using LLMs.""",
        interview=(85.0, [
            ("Machine learning depth", 88.0, "Strong grounding in model evaluation"),
            ("Technical depth", 84.0, "Good production ML experience"),
            ("Communication", 83.0, "Explains modelling choices clearly"),
        ]),
    ),
    dict(
        name="Dev Sharma", email="dev.sharma@example.com", job=0, years=3.0,
        title="Backend Developer", source="Job board", stage="applied",
        resume="""Dev Sharma — Backend Developer
3 years of experience with Python and Flask. Built REST APIs backed by MySQL.
SKILLS: Python, Flask, MySQL, Git, Docker""",
        interview=None,
    ),
    dict(
        name="Farhan Qureshi", email="farhan.q@example.com", job=1, years=2.0,
        title="Data Scientist", source="Career site", stage="screened",
        resume="""Farhan Qureshi — Data Scientist
2 years of experience in analytics and modelling.
SKILLS: Python, Pandas, NumPy, scikit-learn, SQL, Data Analysis""",
        interview=None,
    ),
]


# --------------------------------------------------------------------------
# Seeding
# --------------------------------------------------------------------------
OWNED_TABLES = [
    OnboardingTask, OnboardingPlan, AttendanceRecord, EmployeeSkill,
    Feedback, Goal, PerformanceReview, Employee, SkillRequirement,
    PolicyChunk, PolicyDocument, InterviewTurn, InterviewSession,
    Resume, Candidate, JobRequisition,
]


def reset_demo_data(db) -> None:
    """Delete the tables this script owns. Users are left alone."""
    for model in OWNED_TABLES:
        db.query(model).delete()
    db.commit()


def _ensure_hr_user(db) -> User:
    existing = get_user_by_email(db, HR_EMAIL)
    if existing:
        return existing
    return create_user(
        db,
        UserCreate(email=HR_EMAIL, full_name="Demo HR Lead", password=HR_PASSWORD),
    )


def _seed_employees(db) -> Dict[str, Employee]:
    created: Dict[str, Employee] = {}

    # Managers first so reports can reference them.
    ordered = sorted(EMPLOYEES, key=lambda e: 0 if e["name"] in MANAGER_OF.values() else 1)

    for spec in ordered:
        manager_name = MANAGER_OF.get(spec["dept"])
        manager = created.get(manager_name) if manager_name != spec["name"] else None
        employee = create_employee(
            db,
            full_name=spec["name"],
            email=spec["name"].lower().replace(" ", ".") + "@demo.local",
            employee_code=f"E{1000 + len(created) + 1}",
            department=spec["dept"],
            job_title=spec["title"],
            seniority=spec["seniority"],
            location=spec.get("location"),
            employment_type="full_time",
            work_mode=spec.get("mode"),
            manager_id=manager.id if manager else None,
            hire_date=_years_ago(spec["tenure"]),
            last_promotion_date=_months_ago(spec["promo"]),
            compa_ratio=spec.get("compa"),
            engagement_score=spec.get("engagement"),
            status="active",
        )
        created[spec["name"]] = employee

        for skill, proficiency, verified in spec["skills"]:
            add_employee_skill(
                db,
                employee_id=employee.id,
                skill=canonical_skill(skill),
                proficiency=proficiency,
                source="manager" if verified else "self_reported",
                verified=verified,
            )

    for spec in LEAVERS:
        create_employee(
            db,
            full_name=spec["name"],
            department=spec["dept"],
            job_title=spec["title"],
            hire_date=_years_ago(spec["tenure"] + spec["exit_months_ago"] / 12),
            exit_date=_months_ago(spec["exit_months_ago"]),
            status="resigned",
            employment_type="full_time",
        )

    return created


def _seed_attendance(db, employees: Dict[str, Employee], *, days: int = 180) -> int:
    rng = random.Random(RANDOM_SEED)
    rows: List[dict] = []

    for name, employee in employees.items():
        absence_p, overtime_base, late_p = ATTENDANCE_PROFILE.get(name, DEFAULT_ATTENDANCE)
        for offset in range(days):
            day = TODAY - timedelta(days=offset + 1)
            if day.weekday() >= 5:
                continue  # weekends are not tracked
            if day < employee.hire_date:
                continue

            roll = rng.random()
            if roll < absence_p:
                status = "absent"
                hours = 0.0
                overtime = 0.0
                late = False
            elif roll < absence_p + 0.04:
                status = "leave"  # approved: excluded from absence risk
                hours = 0.0
                overtime = 0.0
                late = False
            else:
                status = "remote" if (employee.work_mode == "remote" or rng.random() < 0.3) else "present"
                overtime = max(0.0, round(rng.gauss(overtime_base, 0.7), 1))
                hours = round(8.0 + overtime, 1)
                late = rng.random() < late_p

            rows.append(
                dict(
                    employee_id=employee.id,
                    work_date=day,
                    status=status,
                    hours_worked=hours,
                    overtime_hours=overtime,
                    late_arrival=late,
                )
            )

    return bulk_record_attendance(db, rows)


def _seed_performance(db, employees: Dict[str, Employee]) -> None:
    for name, reviews in REVIEWS.items():
        employee = employees.get(name)
        if not employee or not reviews:
            continue
        manager = employees.get(MANAGER_OF.get(employee.department, ""))
        for period, rating, strengths, improvements, comments, promotion_ready in reviews:
            create_review(
                db,
                employee_id=employee.id,
                reviewer_id=manager.id if manager and manager.id != employee.id else None,
                period=period,
                review_date=_months_ago(6 if period.endswith("H1") else 12),
                rating=rating,
                strengths=list(strengths),
                improvements=list(improvements),
                comments=comments,
                promotion_ready=promotion_ready,
            )

    for name, goals in GOALS.items():
        employee = employees.get(name)
        if not employee:
            continue
        for title, status, progress, weight in goals:
            create_goal(
                db,
                employee_id=employee.id,
                title=title,
                period="2025-H1",
                status=status,
                progress=progress,
                weight=weight,
                due_date=TODAY + timedelta(days=45),
            )

    for name, items in FEEDBACK.items():
        employee = employees.get(name)
        if not employee:
            continue
        author = employees.get(MANAGER_OF.get(employee.department, ""))
        for index, (source, content) in enumerate(items):
            create_feedback(
                db,
                employee_id=employee.id,
                author_id=author.id if source == "manager" and author else None,
                source=source,
                content=content,
                given_on=_months_ago(index + 1),
            )


def _seed_requirements(db) -> None:
    for spec in REQUIREMENTS:
        target_date = None
        if spec.get("target_months"):
            target_date = TODAY + timedelta(days=int(spec["target_months"] * 30.44))
        create_skill_requirement(
            db,
            skill=canonical_skill(spec["skill"]),
            department=spec.get("department"),
            role=spec.get("role"),
            importance=spec["importance"],
            horizon=spec["horizon"],
            required_headcount=spec["headcount"],
            required_proficiency=spec["proficiency"],
            target_date=target_date,
            rationale=spec.get("rationale"),
        )


def _seed_policies(db) -> None:
    from app.core.policy_qa import split_policy_into_chunks

    for spec in POLICIES:
        create_policy(
            db,
            chunks=split_policy_into_chunks(spec["content"]),
            title=spec["title"],
            category=spec["category"],
            version=spec["version"],
            effective_date=spec["effective"],
            applies_to=spec["applies_to"],
        )


def _seed_recruitment(db, hr_user: User) -> None:
    from app.core.skills import extract_skills

    jobs: List[JobRequisition] = []
    for spec in JOBS:
        job = JobRequisition(
            created_by_user_id=hr_user.id,
            title=spec["title"],
            department=spec["department"],
            seniority=spec["seniority"],
            location=spec["location"],
            employment_type=spec["employment_type"],
            description=spec["description"],
            required_skills=[canonical_skill(s) for s in spec["required"]],
            preferred_skills=[canonical_skill(s) for s in spec["preferred"]],
            min_years_experience=spec["min_years"],
            headcount=spec["headcount"],
            status="open",
        )
        db.add(job)
        jobs.append(job)
    db.flush()

    for spec in CANDIDATES:
        job = jobs[spec["job"]]
        candidate = Candidate(
            created_by_user_id=hr_user.id,
            job_requisition_id=job.id,
            full_name=spec["name"],
            email=spec["email"],
            current_title=spec["title"],
            years_experience=spec["years"],
            source=spec["source"],
            stage=spec["stage"],
        )
        db.add(candidate)
        db.flush()

        resume_text = spec["resume"]
        db.add(
            Resume(
                user_id=hr_user.id,
                candidate_id=candidate.id,
                original_filename=f"{spec['name'].lower().replace(' ', '_')}_resume.txt",
                stored_filename=f"seed_{candidate.id}.txt",
                content_type="text/plain",
                size_bytes=len(resume_text.encode("utf-8")),
                storage_path=f"uploads/resumes/seed_{candidate.id}.txt",
                extracted_text=resume_text,
                extraction_status="ok",
                extracted_skills=extract_skills(resume_text),
            )
        )

        if spec["interview"]:
            overall, skill_scores = spec["interview"]
            session = InterviewSession(
                user_id=hr_user.id,
                candidate_id=candidate.id,
                job_requisition_id=job.id,
                target_role=job.title,
                difficulty="medium",
                personality_mode="friendly",
                resume_text=resume_text,
                status="ended",
                question_index=6,
                overall_score=overall,
                skill_scores=[
                    {"name": name, "score": score, "comment": comment}
                    for name, score, comment in skill_scores
                ],
                report_summary=(
                    f"Interview completed for {spec['name']} against {job.title}."
                ),
                report_strengths=[c for _n, s, c in skill_scores if s >= 80],
                report_weaknesses=[c for _n, s, c in skill_scores if s < 60],
                scored_at=datetime.utcnow(),
                started_at=datetime.utcnow() - timedelta(days=4),
                ended_at=datetime.utcnow() - timedelta(days=4),
            )
            db.add(session)
            db.flush()
            db.add(
                InterviewTurn(
                    session_id=session.id,
                    role="assistant",
                    content=f"Walk me through your most complex {job.title} project.",
                    turn_index=0,
                )
            )
            db.add(
                InterviewTurn(
                    session_id=session.id,
                    role="user",
                    content="Summary of the candidate's answer captured during the interview.",
                    turn_index=1,
                )
            )

    db.commit()


def _seed_onboarding(db, employees: Dict[str, Employee]) -> Optional[OnboardingPlan]:
    """Generate a real plan for the most recent joiner via the onboarding agent."""
    joiner = min(employees.values(), key=lambda e: e.hire_date, default=None)
    if joiner is None:
        return None

    buddy = suggest_buddy(db, joiner)
    profile = build_onboarding_profile(db, joiner, buddy_name=buddy.full_name if buddy else None)
    journey = generate_onboarding_journey(
        profile, role_required_skills=role_required_skills(db, joiner)
    )

    plan = create_onboarding_plan(
        db,
        employee_id=joiner.id,
        role=joiner.job_title,
        department=joiner.department,
        seniority=joiner.seniority,
        work_mode=joiner.work_mode,
        buddy_id=buddy.id if buddy else None,
        start_date=joiner.hire_date,
        status="active",
        summary=journey.summary,
        targeted_skill_gaps=journey.targeted_skill_gaps,
        tasks=[
            {
                "title": t.title,
                "description": t.description,
                "phase": t.phase,
                "category": t.category,
                "day_offset": t.day_offset,
                "owner": t.owner,
                "mandatory": t.mandatory,
                "rationale": t.rationale,
                # Pre-boarding and early week-1 items are already done; the rest
                # are outstanding, which is what the dashboard should flag.
                "status": "done" if t.day_offset <= 1 else "pending",
            }
            for t in journey.tasks
        ],
    )
    return plan


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed the HR demo organisation.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete existing demo data (employees, policies, candidates, ...) before seeding.",
    )
    args = parser.parse_args()

    # Make sure every table exists before touching it.
    Base.metadata.create_all(bind=engine)
    init_db()

    db = SessionLocal()
    try:
        existing = db.query(Employee).count()
        if existing and not args.reset:
            print(
                f"Refusing to seed: {existing} employees already exist.\n"
                "Re-run with --reset to replace the demo data."
            )
            return 1
        if args.reset:
            print("Resetting demo data...")
            reset_demo_data(db)

        hr_user = _ensure_hr_user(db)
        print(f"HR login: {HR_EMAIL} / {HR_PASSWORD}")

        employees = _seed_employees(db)
        print(f"Employees:        {len(employees)} active, {len(LEAVERS)} leavers")

        attendance_rows = _seed_attendance(db, employees)
        print(f"Attendance:       {attendance_rows} day records")

        _seed_performance(db, employees)
        print(
            f"Performance:      {db.query(PerformanceReview).count()} reviews, "
            f"{db.query(Goal).count()} goals, {db.query(Feedback).count()} feedback notes"
        )

        _seed_requirements(db)
        print(
            f"Skill demand:     {db.query(SkillRequirement).count()} requirements "
            f"({sum(1 for r in REQUIREMENTS if r['horizon'] == 'future')} future)"
        )

        _seed_policies(db)
        print(
            f"Policies:         {db.query(PolicyDocument).count()} documents, "
            f"{db.query(PolicyChunk).count()} citable sections"
        )

        _seed_recruitment(db, hr_user)
        print(
            f"Recruitment:      {db.query(JobRequisition).count()} requisitions, "
            f"{db.query(Candidate).count()} candidates, "
            f"{db.query(InterviewSession).count()} scored interviews"
        )

        plan = _seed_onboarding(db, employees)
        if plan:
            print(
                f"Onboarding:       plan for {plan.employee.full_name} "
                f"({len(plan.tasks)} tasks, gaps: {', '.join(plan.targeted_skill_gaps or []) or 'none'})"
            )

        print("\nDone. Start the API and open /hr to see the dashboard.")
        print("Demo highlights to look for:")
        print("  - Ravi Menon: high flight risk, high performer, sole Kubernetes owner")
        print("  - Machine Learning / LLMs: future gaps with an internal reskilling candidate")
        print("  - Rohan Gupta: strong resume, weak interview -> conflict flag")
        print("  - Divya Suresh: candidate who closes the ML gap")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
