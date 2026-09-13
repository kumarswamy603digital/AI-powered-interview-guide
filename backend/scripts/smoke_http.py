"""
HTTP smoke test against a running server.

This is the layer the other two harnesses cannot reach: real requests, real
SQLAlchemy, real pydantic validation. Uses only the standard library.

    # terminal 1
    python -m scripts.seed_demo --reset
    python -m uvicorn app.main:app --port 8000

    # terminal 2
    python scripts/smoke_http.py
    python scripts/smoke_http.py --base-url http://127.0.0.1:8000

Exit codes: 0 all passed, 1 one or more checks failed, 2 server unreachable.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
import uuid
from typing import Any, Dict, List, Optional, Tuple

RESULTS: List[Tuple[str, str, bool, str]] = []  # (group, label, ok, detail)
TOKEN: Optional[str] = None
BASE_URL = "http://127.0.0.1:8000"


# --------------------------------------------------------------------------
# Tiny HTTP helper
# --------------------------------------------------------------------------
def request(
    method: str,
    path: str,
    *,
    body: Any = None,
    multipart: Optional[Tuple[str, str, bytes, str]] = None,
    form_fields: Optional[Dict[str, str]] = None,
    auth: bool = True,
) -> Tuple[int, Any]:
    """Returns (status_code, parsed_body_or_text). Never raises on HTTP errors."""
    url = BASE_URL.rstrip("/") + path
    headers: Dict[str, str] = {"Accept": "application/json"}
    data: Optional[bytes] = None

    if multipart is not None:
        field, filename, content, content_type = multipart
        boundary = f"----smoke{uuid.uuid4().hex}"
        parts: List[bytes] = []
        # Plain form fields alongside the file (e.g. candidate_id).
        for name, value in (form_fields or {}).items():
            parts += [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                str(value).encode(),
                b"\r\n",
            ]
        parts += [
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'.encode(),
            f"Content-Type: {content_type}\r\n\r\n".encode(),
            content,
            f"\r\n--{boundary}--\r\n".encode(),
        ]
        data = b"".join(parts)
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    elif body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"

    if auth and TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            raw = response.read().decode("utf-8", errors="replace")
            status = response.status
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        status = exc.code
    except urllib.error.URLError as exc:
        print(f"\nServer unreachable at {BASE_URL}: {exc.reason}")
        print("Start it with:  python -m uvicorn app.main:app --port 8000")
        sys.exit(2)

    try:
        return status, json.loads(raw)
    except json.JSONDecodeError:
        return status, raw


def form_login(email: str, password: str) -> Optional[str]:
    """OAuth2 password flow expects form encoding, not JSON."""
    import urllib.parse

    url = BASE_URL.rstrip("/") + "/api/auth/login"
    data = urllib.parse.urlencode({"username": email, "password": password}).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            payload = json.loads(response.read().decode())
            return payload.get("access_token")
    except urllib.error.HTTPError:
        return None
    except urllib.error.URLError as exc:
        print(f"\nServer unreachable at {BASE_URL}: {exc.reason}")
        sys.exit(2)


GROUP = ""


def group(name: str) -> None:
    global GROUP
    GROUP = name
    print()
    print("=" * 72)
    print(name)
    print("=" * 72)


def check(label: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append((GROUP, label, bool(ok), detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + ("" if ok else f"   << {detail}"))
    return bool(ok)


def expect_ok(label: str, method: str, path: str, **kwargs) -> Any:
    """Assert a 2xx and return the parsed body."""
    status, payload = request(method, path, **kwargs)
    ok = 200 <= status < 300
    snippet = json.dumps(payload)[:200] if not ok else ""
    check(f"{label}  [{method} {path}]", ok, f"HTTP {status} {snippet}")
    return payload if ok else None


# --------------------------------------------------------------------------
# Scenario
# --------------------------------------------------------------------------
def main() -> int:
    global TOKEN, BASE_URL

    parser = argparse.ArgumentParser(description="HTTP smoke test for the HR platform.")
    parser.add_argument("--base-url", default=BASE_URL)
    parser.add_argument("--email", default="hr@demo.local", help="Seeded HR login")
    parser.add_argument("--password", default="DemoHr!2026")
    args = parser.parse_args()
    BASE_URL = args.base_url

    group("0. HEALTH AND AUTH")
    health = expect_ok("health endpoint responds", "GET", "/health", auth=False)
    check("health reports ok", bool(health) and health.get("status") == "ok", str(health))

    TOKEN = form_login(args.email, args.password)
    if not TOKEN:
        # Fall back to creating a throwaway account so the run still works on an
        # unseeded database.
        throwaway = f"smoke_{uuid.uuid4().hex[:8]}@example.com"
        status, _ = request(
            "POST",
            "/api/auth/signup",
            body={"email": throwaway, "full_name": "Smoke Test", "password": "SmokeTest!2026"},
            auth=False,
        )
        TOKEN = form_login(throwaway, "SmokeTest!2026")
        check(f"signed up a throwaway account ({args.email} not found)", bool(TOKEN),
              f"signup HTTP {status}")
    else:
        check(f"logged in as {args.email}", True)

    if not TOKEN:
        print("\nCannot continue without a token.")
        return 1

    me = expect_ok("current user resolves", "GET", "/api/auth/me")
    check("HR role present on the account", bool(me) and me.get("role") in {"hr", "admin"},
          str(me.get("role") if me else None))

    check("protected endpoint rejects an anonymous request",
          request("GET", "/api/employees", auth=False)[0] in (401, 403))

    # ---------------------------------------------------------------- employees
    group("1. WORKFORCE / EMPLOYEES")
    employees = expect_ok("employee list", "GET", "/api/employees")
    seeded = bool(employees)
    check("employees present (seed script has been run)", seeded and len(employees) > 0,
          "0 employees - run: python -m scripts.seed_demo --reset")
    expect_ok("department list", "GET", "/api/employees/departments")

    employee_id = employees[0]["id"] if seeded and employees else None
    if employee_id:
        one = expect_ok("single employee", "GET", f"/api/employees/{employee_id}")
        check("employee skills serialise as strings (ORM relationship flattened)",
              bool(one) and all(isinstance(s, str) for s in one.get("skills", [])),
              str(one.get("skills")[:3] if one else None))
        check("derived tenure present", bool(one) and one.get("tenure_years") is not None)

        profile = expect_ok("employee 360 view", "GET", f"/api/employees/{employee_id}/360")
        if profile:
            check("360 includes attrition assessment with factors",
                  bool(profile.get("attrition", {}).get("factors")))
            check("360 includes performance insight",
                  "performance" in profile and "goal_summary" in profile["performance"])
            check("360 includes attendance summary with a real day count",
                  isinstance(profile.get("attendance", {}).get("days_recorded"), int))
            check("360 goals serialise (nullable JSON related_skills handled)",
                  isinstance(profile.get("goals"), list))
        expect_ok("employee skills", "GET", f"/api/employees/{employee_id}/skills")
        expect_ok("attendance summary", "GET", f"/api/employees/{employee_id}/attendance-summary")
        expect_ok("attendance history", "GET", f"/api/attendance/{employee_id}?days=60")

    # --------------------------------------------------------------- attrition
    group("2. ATTRITION PREDICTION")
    model = expect_ok("model description", "GET", "/api/attrition/model")
    check("model publishes weights that sum to 1.0",
          bool(model) and abs(sum(s["weight"] for s in model["signals"]) - 1.0) < 0.001,
          str(sum(s["weight"] for s in model["signals"]) if model else None))
    overview = expect_ok("workforce risk overview", "GET", "/api/attrition")
    if overview:
        check("assessments returned", len(overview.get("assessments", [])) > 0)
        check("band distribution present", bool(overview.get("band_distribution")))
        check("org-level drivers ranked", len(overview.get("top_drivers", [])) > 0)
        first = (overview.get("assessments") or [{}])[0]
        check("highest-risk employee has evidence on every factor",
              all(f.get("evidence") for f in first.get("factors", [])))
        check("at-risk employee has retention actions",
              first.get("risk_band") not in {"high", "critical"}
              or len(first.get("recommended_actions", [])) > 0)
    if employee_id:
        expect_ok("single employee assessment", "GET", f"/api/attrition/employees/{employee_id}")

    # ------------------------------------------------------------- performance
    group("3. PERFORMANCE INTELLIGENCE")
    insights = expect_ok("workforce insights", "GET", "/api/performance/insights")
    if insights:
        check("insights returned", len(insights) > 0)
        check("insight carries goal summary and themes",
              all("goal_summary" in i and "strengths" in i for i in insights[:3]))
    expect_ok("declining filter", "GET", "/api/performance/insights?trajectory=declining")
    expect_ok("promotion-ready filter", "GET", "/api/performance/insights?promotion_readiness=ready")
    expect_ok("department calibration", "GET", "/api/performance/calibration")
    if employee_id:
        expect_ok("single insight", "GET", f"/api/performance/insights/{employee_id}")
        expect_ok("reviews", "GET", f"/api/performance/reviews/{employee_id}")
        expect_ok("goals", "GET", f"/api/performance/goals/{employee_id}")
        expect_ok("feedback", "GET", f"/api/performance/feedback/{employee_id}")

    # ------------------------------------------------------------ skill graph
    group("4. WORKFORCE SKILL GRAPH")
    graph = expect_ok("skill graph", "GET", "/api/skills/graph")
    if graph:
        check("nodes present", len(graph.get("nodes", [])) > 0)
        check("edges present for visualisation", len(graph.get("edges", [])) > 0)
        summary = graph.get("summary", {})
        check("summary reports current coverage and future readiness",
              "current_coverage" in summary and "future_readiness" in summary)
    expect_ok("gaps only", "GET", "/api/skills/gaps")
    expect_ok("future gaps", "GET", "/api/skills/gaps?horizon=future")
    expect_ok("skill categories", "GET", "/api/skills/categories")
    expect_ok("adjacent skills", "GET", "/api/skills/adjacent/Kubernetes")
    expect_ok("requirements list", "GET", "/api/skills/requirements")

    created_requirement = None
    status, payload = request(
        "POST",
        "/api/skills/requirements",
        body={"skill": "k8s", "department": "Engineering", "importance": "core",
              "horizon": "future", "required_headcount": 2, "rationale": "smoke test"},
    )
    if check("create a requirement  [POST /api/skills/requirements]",
             200 <= status < 300, f"HTTP {status} {json.dumps(payload)[:160]}"):
        created_requirement = payload.get("id")
        check("skill name canonicalised on write (k8s -> Kubernetes)",
              payload.get("skill") == "Kubernetes", str(payload.get("skill")))
    if created_requirement:
        status, _ = request("DELETE", f"/api/skills/requirements/{created_requirement}")
        check("delete the requirement", status == 204, f"HTTP {status}")

    # ------------------------------------------------------------- onboarding
    group("5. ADAPTIVE ONBOARDING")
    expect_ok("phase reference", "GET", "/api/onboarding/phases")
    plans = expect_ok("active plans", "GET", "/api/onboarding/plans")
    if plans:
        check("seeded plan present with progress", len(plans) > 0
              and "progress" in plans[0], "no plans - was the seed script run?")
    if employee_id:
        journey = expect_ok("generate a journey (preview, not persisted)", "POST",
                            "/api/onboarding/generate",
                            body={"employee_id": employee_id, "persist": False})
        if journey:
            check("journey spans phases", len(journey.get("phases", [])) >= 3)
            check("every task explains why it is in this plan",
                  all(t.get("rationale") for t in journey.get("tasks", [])))
            check("personalisation notes returned",
                  len(journey.get("personalization_notes", [])) > 0)
    if plans and plans[0].get("tasks"):
        task = plans[0]["tasks"][0]
        status, updated = request("PATCH", f"/api/onboarding/tasks/{task['id']}",
                                  body={"status": "done"})
        check("complete an onboarding task", 200 <= status < 300, f"HTTP {status}")
        request("PATCH", f"/api/onboarding/tasks/{task['id']}",
                body={"status": task.get("status", "pending")})

    # ---------------------------------------------------------------- policies
    group("6. POLICY REASONING")
    policies = expect_ok("policy library", "GET", "/api/policies")
    if policies:
        check("policies loaded with citable sections",
              len(policies) > 0 and all(p.get("section_count", 0) > 0 for p in policies),
              "no policies - run the seed script")
        expect_ok("policy detail with sections", "GET", f"/api/policies/{policies[0]['id']}")

    answered = expect_ok("answer a covered question", "POST", "/api/policies/ask",
                         body={"question": "How many annual leave days can I carry forward?",
                               "use_llm": False})
    if answered:
        check("covered question is answered", answered.get("answered") is True)
        check("answer is source-backed", len(answered.get("citations", [])) > 0)
        check("citation names a policy and section",
              bool(answered["citations"][0].get("policy_title")) if answered.get("citations") else False)

    refused = expect_ok("refuse an uncovered question", "POST", "/api/policies/ask",
                        body={"question": "What is the policy on cryptocurrency trading?",
                              "use_llm": False})
    if refused:
        check("uncovered question is refused rather than answered",
              refused.get("answered") is False, str(refused.get("answered")))
        check("refusal escalates to a human", "hr" in refused.get("answer", "").lower())

    if employee_id:
        scoped = expect_ok("employee-scoped question", "POST", "/api/policies/ask",
                           body={"question": "Can I work remotely?", "employee_id": employee_id,
                                 "use_llm": False})
        if scoped:
            check("scoped answer returns caveats field", "caveats" in scoped)

    # -------------------------------------------------------------- recruitment
    group("7. RECRUITMENT INTELLIGENCE + INTERVIEW AGENT")
    jobs = expect_ok("requisition list", "GET", "/api/jobs")
    candidates = expect_ok("candidate list", "GET", "/api/candidates")
    job_id = jobs[0]["id"] if jobs else None

    if job_id:
        ranking = expect_ok("rank candidates for a requisition", "POST", "/api/candidates/rank",
                            body={"job_requisition_id": job_id})
        if ranking:
            check("candidates ranked", len(ranking.get("rankings", [])) > 0,
                  "no candidates on this requisition")
            rows = ranking.get("rankings", [])
            if rows:
                check("ranking sorted best-first",
                      all(rows[i]["final_score"] >= rows[i + 1]["final_score"]
                          for i in range(len(rows) - 1)))
                check("every ranking carries reasoning", all(r.get("reasoning") for r in rows))
                check("skill match itemised into matched/missing",
                      all("matched_skills" in r and "missing_skills" in r for r in rows))

    if candidates:
        expect_ok("candidate intelligence profile", "GET",
                  f"/api/candidates/{candidates[0]['id']}/profile")

    # Resume upload + parsing (multipart).
    resume_text = (
        b"Smoke Test Candidate\n7 years of experience.\n"
        b"SKILLS: Python, FastAPI, PostgreSQL, Kubernetes, AWS, Terraform\n"
        b"EXPERIENCE: Built backend services on Kubernetes with Terraform.\n"
    )
    upload = expect_ok("upload and parse a resume", "POST", "/api/resumes/upload",
                       multipart=("file", "smoke_resume.txt", resume_text, "text/plain"))
    if upload:
        check("resume text extracted at upload", upload.get("extraction_status") == "ok",
              str(upload.get("extraction_status")))
        check("skills detected from the resume text",
              "Kubernetes" in (upload.get("extracted_skills") or []),
              str(upload.get("extracted_skills")))
        check("character count reported", (upload.get("extracted_characters") or 0) > 50)
        expect_ok("fetch extracted text", "GET", f"/api/resumes/{upload['id']}/text")

    plan = expect_ok("generate an interview plan", "POST", "/api/interviews/plan/generate",
                     body={"resume_text": resume_text.decode(),
                           "target_role": "Senior Backend Engineer", "difficulty": "hard"})
    if plan:
        check("plan has rounds and categories",
              len(plan.get("interview_structure", [])) > 0
              and len(plan.get("question_categories", [])) > 0)

    started = expect_ok("start a live interview", "POST", "/api/interviews/live/start",
                        body={"resume_text": resume_text.decode(),
                              "target_role": "Senior Backend Engineer",
                              "difficulty": "medium", "personality_mode": "friendly"})
    if started:
        session_id = started["id"]
        check("first question generated", bool(started.get("first_question")))
        submitted = expect_ok("submit an answer", "POST",
                              f"/api/interviews/live/{session_id}/submit",
                              body={"answer": (
                                  "I used a token bucket in Redis with a Lua script for atomicity, "
                                  "because it keeps the check atomic across pods. That cut rejected "
                                  "requests by 30%.")})
        check("next question returned", bool(submitted and submitted.get("next_question")))

        strong = expect_ok("evaluate a strong answer", "POST", "/api/answers/evaluate",
                           body={"question": "How would you design a rate limiter?",
                                 "answer": ("I would use a token bucket in Redis with a Lua script "
                                            "for atomicity, because it keeps the check atomic "
                                            "across pods, which cut rejections by 30%."),
                                 "target_role": "Senior Backend Engineer"})
        weak = expect_ok("evaluate a non-answer", "POST", "/api/answers/evaluate",
                         body={"question": "How would you design a rate limiter?",
                               "answer": "Not sure.",
                               "target_role": "Senior Backend Engineer"})
        if strong and weak:
            check("evaluation differentiates answer quality",
                  strong["overall_score"] > weak["overall_score"] + 15,
                  f"{strong['overall_score']} vs {weak['overall_score']}")

        ended = expect_ok("end the interview (scores persist)", "POST",
                          f"/api/interviews/live/{session_id}/end")
        if ended:
            check("interview scored on completion", ended.get("scored") is True,
                  str(ended.get("scored")))
            check("overall score persisted", ended.get("overall_score") is not None)
        expect_ok("interview report", "GET", f"/api/reports/{session_id}")

    # --------------------------------------------------------------- dashboards
    group("8. HR DECISION DASHBOARD")
    expect_ok("recruitment dashboard", "GET", "/api/hr/dashboard")
    decision = expect_ok("decision dashboard", "GET", "/api/hr/decision-dashboard")
    if decision:
        check("headline metrics present", bool(decision.get("headline")))
        for section in ("recruitment", "workforce_risk", "performance", "attendance",
                        "skills", "onboarding"):
            check(f"section present: {section}", section in decision)
        check("cross-source insights produced", len(decision.get("insights", [])) > 0,
              "0 insights - seed the demo data to populate them")
        insights = decision.get("insights", [])
        if insights:
            check("every insight names its sources",
                  all(i.get("sources") for i in insights))
            check("every insight states an action",
                  all(i.get("recommended_action") for i in insights))
            check("most insights combine two or more sources",
                  sum(1 for i in insights if len(i.get("sources", [])) >= 2) >= max(1, len(insights) // 2))
        check("data sources declared", len(decision.get("data_sources", [])) >= 2)

    # ------------------------------------------------------- write + lifecycle
    # These exercise the write paths, where model/schema mismatches surface. Every
    # record created here is prefixed SMOKE so it is easy to spot and remove.
    group("9. WRITE PATHS AND CANDIDATE -> EMPLOYEE LIFECYCLE")

    new_job = expect_ok("create a requisition", "POST", "/api/jobs",
                        body={"title": "SMOKE Backend Engineer", "department": "Engineering",
                              "seniority": "Senior",
                              "required_skills": ["python", "fastapi", "k8s"],
                              "preferred_skills": ["terraform"],
                              "min_years_experience": 4, "headcount": 1,
                              "description": "Created by smoke_http.py"})
    if new_job:
        check("requisition skills canonicalised on write",
              new_job.get("required_skills") == ["Python", "FastAPI", "Kubernetes"],
              str(new_job.get("required_skills")))
        new_job_id = new_job["id"]
        expect_ok("read the requisition", "GET", f"/api/jobs/{new_job_id}")
        patched = expect_ok("patch the requisition", "PATCH", f"/api/jobs/{new_job_id}",
                            body={"headcount": 2, "seniority": "Staff"})
        check("patch applied", bool(patched) and patched.get("headcount") == 2)
        expect_ok("requisition candidate count", "GET", f"/api/jobs/{new_job_id}/candidate-count")

        new_candidate = expect_ok("create a candidate", "POST", "/api/candidates",
                                  body={"full_name": "SMOKE Candidate",
                                        "email": f"smoke_{uuid.uuid4().hex[:6]}@example.com",
                                        "current_title": "Backend Engineer",
                                        "years_experience": 6, "source": "Smoke test",
                                        "job_requisition_id": new_job_id})
        if new_candidate:
            candidate_id = new_candidate["id"]
            resume_for_candidate = (
                b"SMOKE Candidate\n6 years of experience.\n"
                b"SKILLS: Python, FastAPI, Kubernetes, Terraform, PostgreSQL\n"
            )
            linked = expect_ok("upload a resume linked to the candidate", "POST",
                               "/api/resumes/upload",
                               multipart=("file", "smoke_candidate.txt",
                                          resume_for_candidate, "text/plain"),
                               form_fields={"candidate_id": str(candidate_id)})
            expect_ok("list my resumes", "GET", "/api/resumes")
            if linked:
                check("linked upload parsed", linked.get("extraction_status") == "ok")
                check("upload attached to the candidate",
                      linked.get("candidate_id") == candidate_id,
                      str(linked.get("candidate_id")))
                check("skills extracted from the linked resume",
                      "Kubernetes" in (linked.get("extracted_skills") or []),
                      str(linked.get("extracted_skills")))
                expect_ok("latest resume for that candidate", "GET",
                          f"/api/resumes/candidates/{candidate_id}/latest")

            expect_ok("patch the candidate stage", "PATCH", f"/api/candidates/{candidate_id}",
                      body={"stage": "screened"})
            expect_ok("candidate profile", "GET", f"/api/candidates/{candidate_id}")

            hired = expect_ok("hire the candidate into an employee", "POST",
                              "/api/employees/from-candidate",
                              body={"candidate_id": candidate_id, "department": "Engineering",
                                    "job_title": "Senior Backend Engineer", "seniority": "senior",
                                    "hire_date": "2026-09-01", "work_mode": "remote",
                                    "location": "Bengaluru", "employment_type": "full_time",
                                    "compa_ratio": 1.0, "generate_onboarding_plan": True})
            if hired:
                new_employee_id = hired["id"]
                check("hired employee links back to the candidate",
                      hired.get("source_candidate_id") == candidate_id)
                plan = expect_ok("onboarding plan auto-created on hire", "GET",
                                 f"/api/onboarding/employees/{new_employee_id}")
                if plan:
                    check("auto plan has tasks", len(plan.get("tasks", [])) > 0)
                    check("auto plan reports progress", "progress" in plan)
                    expect_ok("read that plan by id", "GET", f"/api/onboarding/plans/{plan['id']}")

                added = expect_ok("add a skill to the employee", "POST",
                                  f"/api/employees/{new_employee_id}/skills",
                                  body={"skill": "observability", "proficiency": 4,
                                        "source": "manager", "verified": True})
                check("skill canonicalised on write",
                      bool(added) and added.get("skill") == "Observability",
                      str(added.get("skill") if added else None))
                status, _ = request("DELETE",
                                    f"/api/employees/{new_employee_id}/skills/Observability")
                check("remove the skill", status == 204, f"HTTP {status}")

                expect_ok("patch the employee", "PATCH", f"/api/employees/{new_employee_id}",
                          body={"engagement_score": 71.0, "location": "Chennai"})

                expect_ok("record one attendance day", "POST", "/api/attendance",
                          body={"employee_id": new_employee_id, "work_date": "2026-09-02",
                                "status": "remote", "hours_worked": 8.5,
                                "overtime_hours": 0.5, "late_arrival": False})
                expect_ok("bulk record attendance", "POST", "/api/attendance/bulk",
                          body={"records": [
                              {"employee_id": new_employee_id, "work_date": "2026-09-03",
                               "status": "present", "hours_worked": 8.0, "overtime_hours": 0.0},
                              {"employee_id": new_employee_id, "work_date": "2026-09-04",
                               "status": "absent", "hours_worked": 0.0, "overtime_hours": 0.0}]})

                expect_ok("create a performance review", "POST", "/api/performance/reviews",
                          body={"employee_id": new_employee_id, "period": "2026-H1",
                                "rating": 4.2, "strengths": ["Strong system design"],
                                "improvements": ["Documentation"],
                                "comments": "Created by smoke test.",
                                "promotion_ready": "not_yet"})
                new_goal = expect_ok("create a goal", "POST", "/api/performance/goals",
                                     body={"employee_id": new_employee_id,
                                           "title": "SMOKE goal", "status": "on_track",
                                           "progress": 40, "weight": 1.0,
                                           "related_skills": ["Python"]})
                if new_goal:
                    expect_ok("patch the goal", "PATCH",
                              f"/api/performance/goals/{new_goal['id']}",
                              body={"status": "achieved", "progress": 100})
                expect_ok("create feedback", "POST", "/api/performance/feedback",
                          body={"employee_id": new_employee_id, "source": "manager",
                                "content": "Excellent technical depth and clear ownership."})

                after = expect_ok("360 view reflects the new records", "GET",
                                  f"/api/employees/{new_employee_id}/360")
                if after:
                    check("review recorded in 360", len(after.get("reviews", [])) >= 1)
                    check("goal recorded in 360", len(after.get("goals", [])) >= 1)
                    check("feedback recorded in 360", len(after.get("feedback", [])) >= 1)
                    check("performance insight computed from the new data",
                          after["performance"].get("latest_rating") is not None)

    new_policy = expect_ok("create a policy (auto-sectioned)", "POST", "/api/policies",
                           body={"title": "SMOKE Test Policy", "category": "smoke",
                                 "version": "1.0", "applies_to": "all",
                                 "content": ("1. Scope\nThis policy exists only to verify the "
                                             "smoke test path and may be deleted.\n\n"
                                             "2. Widget Allowance\nEmployees may claim up to 3 "
                                             "widgets per quarter with manager approval.")})
    if new_policy:
        check("policy split into sections", len(new_policy.get("chunks", [])) >= 2,
              str(len(new_policy.get("chunks", []))))
        answered_new = expect_ok("the new policy is immediately answerable", "POST",
                                 "/api/policies/ask",
                                 body={"question": "How many widgets can I claim per quarter?",
                                       "use_llm": False})
        if answered_new:
            check("answer cites the new policy",
                  answered_new.get("answered") is True
                  and any(c["policy_title"] == "SMOKE Test Policy"
                          for c in answered_new.get("citations", [])),
                  str(answered_new.get("answered")))
        status, _ = request("DELETE", f"/api/policies/{new_policy['id']}")
        check("delete the policy (cleanup)", status == 204, f"HTTP {status}")

    if candidates:
        expect_ok("latest resume for a seeded candidate", "GET",
                  f"/api/resumes/candidates/{candidates[0]['id']}/latest")

    # ------------------------------------------------------------------ errors
    group("10. ERROR HANDLING")
    check("unknown employee returns 404", request("GET", "/api/employees/999999")[0] == 404)
    check("unknown policy returns 404", request("GET", "/api/policies/999999")[0] == 404)
    check("ranking an unknown requisition returns 404",
          request("POST", "/api/candidates/rank", body={"job_requisition_id": 999999})[0] == 404)
    check("invalid payload returns 422",
          request("POST", "/api/employees", body={"full_name": "x"})[0] == 422)
    check("ATS scoring requires a resume source",
          request("POST", "/api/ats/score", body={"job_role": "Engineer"})[0] == 422)

    # ----------------------------------------------------------------- summary
    print()
    print("=" * 72)
    print("SUMMARY BY GROUP")
    print("=" * 72)
    groups: Dict[str, List[bool]] = {}
    for group_name, _label, ok, _detail in RESULTS:
        groups.setdefault(group_name, []).append(ok)
    for group_name, oks in groups.items():
        passed = sum(1 for ok in oks if ok)
        flag = "OK  " if passed == len(oks) else "FAIL"
        print(f"  [{flag}] {passed:>2}/{len(oks):<2}  {group_name}")

    failures = [(g, label, detail) for g, label, ok, detail in RESULTS if not ok]
    print()
    print(f"TOTAL: {len(RESULTS) - len(failures)}/{len(RESULTS)} checks passed")
    if failures:
        print("\nFAILURES:")
        for group_name, label, detail in failures:
            print(f"  - [{group_name}] {label}")
            if detail:
                print(f"      {detail}")
        return 1
    print("\nALL HTTP CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
