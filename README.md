# 🧠 AI Workforce Intelligence Platform

**An AI-driven workforce management platform that reasons over multiple HR data sources and recommends actions.**

Eight HR capabilities on one shared workforce data model — recruitment, onboarding, policy,
attrition, performance, skills, interviewing and decision support. Every recommendation the
system makes carries the evidence that produced it.

![Python](https://img.shields.io/badge/python-3.10+-green)
![React](https://img.shields.io/badge/React-18.2-blue)
![License](https://img.shields.io/badge/license-proprietary-red)

---

## Contents

- [Track 1 capability coverage](#track-1-capability-coverage)
- [The core idea: cross-source reasoning](#the-core-idea-cross-source-reasoning)
- [How each engine works](#how-each-engine-works)
- [Architecture](#architecture)
- [Getting started](#getting-started)
- [Demo walkthrough](#demo-walkthrough)
- [API reference](#api-reference)
- [Environment variables](#environment-variables)
- [Design decisions](#design-decisions)
- [Known limitations](#known-limitations)

---

## Track 1 capability coverage

| # | Capability | Status | Where |
|---|---|---|---|
| 1 | **AI Recruitment Intelligence Engine** — ranks candidates using resumes, job requirements and skill relevance | ✅ | `core/ranking.py` · `POST /api/candidates/rank` · `/recruitment` |
| 2 | **Adaptive Onboarding Agent** — personalised journeys by role, department and employee profile | ✅ | `core/onboarding_agent.py` · `POST /api/onboarding/generate` · `/onboarding` |
| 3 | **HR Policy Reasoning Agent** — contextual, source-backed policy answers | ✅ | `core/policy_qa.py` · `POST /api/policies/ask` · `/policies` |
| 4 | **Employee Attrition Prediction** — flight risk from workforce patterns and engagement signals | ✅ | `core/attrition.py` · `GET /api/attrition` · `/attrition` |
| 5 | **AI Performance Intelligence** — goals, feedback and history → strengths and improvement areas | ✅ | `core/performance_intel.py` · `GET /api/performance/insights` · `/performance` |
| 6 | **Workforce Skill Graph** — employee skills against current *and future* requirements | ✅ | `core/skill_graph.py` · `GET /api/skills/graph` · `/skills` |
| 7 | **Intelligent Interview Agent** — role-specific questions, response evaluation, structured insights | ✅ | `core/interview_plan.py`, `live_interview.py`, `report.py` · `/interview` |
| 8 | **HR Decision Dashboard** — recruitment, attendance, performance and workforce data → actionable insights | ✅ | `core/decision_dashboard.py` · `GET /api/hr/decision-dashboard` · `/hr` |

> **The challenge:** *"reason over multiple HR data sources and recommend actions, rather than
> building a simple HR chatbot."* That is what section 8 is for, and it is the reason the other
> seven share one data model instead of being seven separate tools.

---

## The core idea: cross-source reasoning

Any one of these capabilities can be built in isolation. The interesting output appears when
they are correlated — findings that **no single source can produce**:

```
attrition risk  ×  skill graph      →  "Ravi is a flight risk AND the only person
                                        qualified on Kubernetes"        [critical]

attrition risk  ×  performance      →  "High performer at risk — this is regretted
                                        attrition if it happens"        [critical]

skill graph     ×  requisitions     →  "Security is a critical gap and no open
                                        requisition even mentions it"   [critical]

candidate rank  ×  skill graph      →  "This candidate would close the ML gap —
                                        prioritise them"             [opportunity]

attendance      ×  attrition        →  "10.5h/week overtime alongside a 64/100
                                        flight risk score"              [warning]

performance     ×  attrition        →  "Promotion-ready but 43 months stagnant"  [warning]

resume          ×  interview score  →  "Matches on paper, interviewed at 43/100"  [warning]
```

Each insight on `/hr` states **its sources**, **its evidence** and **the action it implies**,
so a reviewer can audit where it came from. The dashboard is a decision surface, not a chat log.

---

## How each engine works

### Attrition prediction — 9 weighted signals

| Signal | Weight | Signal | Weight |
|---|---|---|---|
| Career stagnation | 20% | Workload (overtime) | 10% |
| Engagement | 16% | Attendance pattern | 8% |
| Compensation position | 14% | Team attrition contagion | 5% |
| Performance trend | 12% | External market pull | 5% |
| Tenure stage | 10% | | |

- Weights **renormalise** over available signals — missing data lowers *confidence*, it does not invent risk.
- **Approved leave never counts** towards absence risk.
- Detects the classic underpaid high performer (rating ≥ 4 with compa-ratio < 0.97).
- Every factor maps to a retention action with an **estimated risk reduction**, so HR can prioritise by impact.

### Performance intelligence

Themes are extracted from feedback and review text across 9 dimensions (communication,
leadership, technical depth, delivery, quality, …) with a sentiment lexicon that handles
negation (*"not clear"* reads negative). Combines goal attainment (40%), latest rating (40%) and
feedback sentiment (20%), calibrates against the department average, and infers promotion
readiness — deferring to an explicit manager judgement when one exists.

### Workforce skill graph

Supply (employees, weighted by proficiency and verification) against demand split into
**current** and **future** horizons. Surfaces coverage %, gaps, **single points of failure**
(one qualified holder of a core skill), and **reskilling candidates** found via skill-category
adjacency — so the answer to a gap can be *train* rather than *hire*.

### Adaptive onboarding

Layers a base compliance journey with department, seniority, work-mode, location and
employment-type playbooks, then adds **targeted training for the employee's own skill gaps**
against their role's requirements. Every task carries a `rationale` explaining why it is in
*this* person's plan. A senior remote engineer and a junior onsite intern get materially
different journeys.

### Policy reasoning

IDF-weighted retrieval over policy **sections** (not whole documents), with query expansion
(`vacation` → `annual leave`) and stemming (`submit` matches `submitted`). Answers cite the
exact clause, version and effective date. **It refuses when no policy covers the question** and
escalates to a human — a wrong answer about notice period is worse than no answer. Passing an
`employee_id` scopes the answer and raises a caveat when a policy targets a different population.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│ Frontend — React + Vite                                              │
│  /hr          Decision dashboard (cross-source insights)             │
│  /recruitment Candidate ranking      /people   Directory + 360 view  │
│  /attrition   Risk + retention       /performance  Strengths/gaps    │
│  /skills      Skill graph            /onboarding   Journeys          │
│  /policies    Policy Q&A             /interview    Interview agent   │
└──────────────────────────────────────────────────────────────────────┘
                                  │ REST
┌──────────────────────────────────────────────────────────────────────┐
│ Backend — FastAPI                                                    │
│                                                                      │
│  core/  decision_dashboard.py   cross-source insight derivation      │
│         attrition.py            9-signal flight risk                 │
│         performance_intel.py    themes, trajectory, calibration      │
│         skill_graph.py          supply vs current/future demand      │
│         onboarding_agent.py     personalised 30/60/90 journeys       │
│         policy_qa.py            retrieval + citations + refusal       │
│         ranking.py              candidate scoring                    │
│         skills.py               78 skills, 187 aliases, categories   │
│         workforce_intelligence.py   DB → engine input assembly       │
│                                                                      │
│  models/ employees · employee_skills · attendance · reviews · goals  │
│          feedback · skill_requirements · policies · onboarding       │
│          candidates · job_requisitions · resumes · interviews        │
└──────────────────────────────────────────────────────────────────────┘
                                  │
                    ┌─────────────┴─────────────┐
                    │  Google Gemini (optional)  │  interview questions,
                    │  Deterministic fallbacks   │  answer evaluation,
                    │  everywhere else           │  policy synthesis
                    └────────────────────────────┘
```

**The analytics engines never call an LLM.** Attrition, performance, skills, onboarding and
policy retrieval are deterministic, so the same data always yields the same recommendation and
every number traces to its input. Gemini is used where generation is genuinely needed.

### Data model

```
JobRequisition ──< Candidate ──< Resume            (parsed text + skills)
                        │  └──< InterviewSession   (persisted scores)
                        │
                        └── hired ──> Employee     ← skills carry across
                                         │
        ┌────────────────┬───────────────┼──────────────┬───────────────┐
   EmployeeSkill   AttendanceRecord  PerformanceReview  Goal        Feedback
                                                        │
                        OnboardingPlan ──< OnboardingTask
                        SkillRequirement (current | future)
                        PolicyDocument ──< PolicyChunk  (citable sections)
```

`Candidate → Employee` closes the lifecycle loop: skills evidenced during hiring become
verified employee skills, feeding the workforce skill graph instead of being discarded at offer
stage.

---

## Getting started

### Prerequisites

Python 3.10+ (the config module uses `str | None`), Node.js 18+.

### Backend

```bash
cd backend
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                              # optional; defaults work

# Load the demo organisation — do this before opening the UI
python -m scripts.seed_demo --reset

python -m uvicorn app.main:app --reload --port 8000
```

> **Schema changes require a fresh database.** The app uses `Base.metadata.create_all()` with no
> migration tool: it creates missing *tables* but not missing *columns*. Upgrading an existing
> install? Delete `backend/app.db` first (`--reset` on the seed script does not add columns).

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend `http://localhost:5173` · API docs `http://localhost:8000/docs`

### Seeded demo login

```
hr@demo.local  /  DemoHr!2026
```

The seed script creates 22 employees across 5 departments plus 3 leavers (who drive the
department attrition-rate signal), ~2,730 attendance day records, 22 performance reviews, 24
goals, 20 feedback notes, 22 skill requirements of which 5 are future-facing, 6 policies split
into citable sections, 2 requisitions, 5 candidates with parsed resumes, and 3 scored
interviews. Values are deterministic — two runs produce identical numbers.

---

## Demo walkthrough

The seed data is shaped to make the cross-source reasoning visible, not to look tidy.

1. **`/hr` — decision dashboard.** Start here. The insight list is ordered by severity; the top
   entries are the cross-source findings.
2. **Ravi Menon** appears three times: high flight risk (64/100), a high performer (4.6/5), and
   the only Kubernetes holder. Three sources, one conclusion — act now.
3. **`/attrition` → "Explain"** on Ravi. Nine factors with weights, contributions and evidence.
   The compensation row reads *"High performer paid below midpoint"* because the model
   cross-references rating with compa-ratio.
4. **`/skills`** → filter **Future requirements**. Machine Learning and LLMs are critical gaps
   with **zero** qualified holders — and Arjun Das is surfaced as the reskilling candidate
   because he already works in the same skill category.
5. **`/recruitment`** → rank the ML requisition. **Divya Suresh** matches and already holds
   LLMs/RAG; the dashboard flags that hiring her closes a known workforce gap. **Rohan Gupta**
   matches 100% on paper but interviewed at 43/100 → capped at *further assessment*.
6. **`/onboarding`** → preview a journey for **Nisha Verma** (senior, remote, Bengaluru). Note
   the targeted training for FastAPI/Kubernetes/AWS — added because *she* lacks them — and the
   "what was tailored and why" list.
7. **`/policies`** → ask *"How many annual leave days can I carry forward?"* → answer with the
   exact clause cited. Then ask *"What is the policy on cryptocurrency trading?"* → **explicit
   refusal**, escalated to HR, rather than a fabricated answer.

---

## API reference

### Decision support
```
GET  /api/hr/decision-dashboard    Combined view + cross-source insights
GET  /api/hr/dashboard             Recruitment-only pipeline view
```

### Workforce
```
POST/GET/PATCH /api/employees          Employee records
GET  /api/employees/{id}/360           Everything about one person
POST /api/employees/from-candidate     Hire a candidate → employee (+ onboarding plan)
POST/GET /api/employees/{id}/skills    Skill profile
POST /api/attendance · /api/attendance/bulk · GET /api/attendance/{id}
```

### Intelligence
```
GET  /api/attrition                    Whole-workforce risk + org drivers
GET  /api/attrition/employees/{id}     One assessment with factors and actions
GET  /api/attrition/model              Signals, weights and bands (auditable)
GET  /api/performance/insights         Strengths, gaps, trajectory, calibration
POST /api/performance/reviews · /goals · /feedback
GET  /api/skills/graph                 Nodes, edges and summary
GET  /api/skills/gaps                  Under-covered skills only
POST/GET /api/skills/requirements      Demand side (current | future)
```

### Agents
```
POST /api/onboarding/generate          Personalised journey (persist or preview)
GET  /api/onboarding/plans             Active plans with progress
PATCH /api/onboarding/tasks/{id}       Complete a task
POST /api/policies · GET /api/policies Policy library (auto-sectioned)
POST /api/policies/ask                 Source-backed answer or refusal
POST /api/candidates/rank              Candidate ranking
POST /api/interviews/live/start · /{id}/submit · /{id}/end
```

Full interactive docs at `/docs`.

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./app.db` | Database connection string |
| `SECRET_KEY` | `CHANGE_ME_...` | JWT signing secret — **must** change for production |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` | Token lifetime |
| `GEMINI_API_KEY` | _none_ | Enables interview generation, evaluation, policy synthesis |
| `GEMINI_MODEL` | `models/gemini-1.5-pro` | Gemini model name |
| `RESUME_UPLOAD_DIR` | `uploads/resumes` | Resume storage |
| `RESUME_MAX_SIZE_MB` | `10` | Upload limit |
| `BACKEND_CORS_ORIGINS` | localhost dev | Allowed origins |

**No API key is required** for attrition, performance, skills, onboarding, policy retrieval,
resume parsing or candidate ranking. Without a key, interview questions come from a built-in
bank, answer evaluation uses a deterministic heuristic, and policy answers are extractive
rather than synthesised.

---

## Design decisions

**Why the analytics are not LLM-based.** A retention recommendation gets discussed with an
employee's manager; a policy answer affects someone's leave entitlement. Both must be
reproducible and auditable. Deterministic scoring also means the demo behaves identically
without an API key, and every score can be traced to the input that produced it.

**Why the policy agent refuses.** Retrieval below a relevance floor, or covering less than a
third of the question's terms, returns `answered: false` with an escalation instead of a guess.
Confident fabrication is the failure mode that makes HR tools unusable.

**Why skill demand has two horizons.** Current gaps are a hiring problem; future gaps are a
training problem, and they need to be visible *before* they become vacancies.

**Why candidates and employees are separate entities.** Candidates are records HR manages;
employees are the workforce. Conflating them (and with login accounts) is what previously made
cross-candidate ranking impossible.

---

## Known limitations

1. **No migrations.** Schema changes need the SQLite file recreated.
2. **Attrition is not a trained model.** There is no historical exit dataset here; it is an
   expert-weighted signal model. The weights are asserted, not learned — `GET /api/attrition/model`
   exposes them precisely so they can be challenged and tuned.
3. **Sentiment is lexicon-based.** It handles negation but not sarcasm or comparatives.
4. **Policy retrieval is lexical, not semantic.** IDF + synonyms + stemming, no embeddings, so a
   question sharing no vocabulary with the policy may be refused rather than answered.
5. **Reskilling adjacency is a heuristic.** Same-category skills are training candidates, not
   equivalents.
6. **Scanned PDFs yield no text** — no OCR. Affected candidates are flagged, not silently empty.
7. **Attendance drives burnout signals from overtime hours only**; it has no calendar or
   meeting-load data.
8. **Answer evaluation without a Gemini key is lexical.** The fallback scores relevance from
   question-keyword overlap plus recognised technologies, so an answer using domain synonyms is
   under-credited on that one dimension. The composite score (relevance 45%, depth 35%, clarity
   10%, confidence 10%) still ranks answers correctly — see the checks in
   `scripts/verify_capabilities.py`.
9. **Single-tenant.** No org isolation, and the HR role gate is permissive (all accounts default
   to `role="hr"`).
10. **No HTTP-level test suite.** The two harnesses below cover engine behaviour and wiring
    integrity, not the live request/response cycle.

---

## Verification

Two committed harnesses, both runnable with plain `python` (no pytest, no network):

```bash
cd backend
python scripts/verify_capabilities.py   # 135 behavioural checks across all 8 capabilities
python scripts/audit_wiring.py          # 16 structural checks on how it is wired together
```

**`verify_capabilities.py`** executes the real engines against fixture data and asserts the
outputs — per capability, e.g. that a sole-holder-of-a-core-skill insight fires, that an
uncovered policy question is refused rather than answered, that a resigned employee is excluded
from skill supply, that sparse data lowers confidence instead of inventing risk, and that a
strong interview answer outscores a fluent off-topic one.

**`audit_wiring.py`** checks what a server boot would catch: that all 242 internal imports
resolve, that all 14 dataclass→schema conversions supply every required field, that CRUD and
model keyword arguments are real columns, that all 34 SQLAlchemy relationships pair up, that no
route shadows another, and that every router is registered.

Both scripts stub only the packages that are genuinely missing, so in a fully installed
environment they audit the real libraries.

---

## License

Proprietary — All Rights Reserved.
