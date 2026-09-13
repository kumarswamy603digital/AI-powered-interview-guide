# 🧠 AI HR Recruitment Intelligence

**An HR platform that reasons over multiple recruitment data sources and recommends actions.**

Given a job requisition, a candidate's parsed resume, and their interview performance, the
system produces a ranked shortlist where every recommendation carries the reasoning that
produced it.

![Python](https://img.shields.io/badge/python-3.10+-green)
![React](https://img.shields.io/badge/React-18.2-blue)
![License](https://img.shields.io/badge/license-proprietary-red)

---

## Live deployment

👉 [Live demo](https://chowdary1-ai-interviewer-version-1.hf.space/login)

> Note: the hosted build may lag behind `main`.

---

## 📋 Contents

- [What it does](#what-it-does)
- [How the ranking works](#how-the-ranking-works)
- [Feature status](#feature-status)
- [Architecture](#architecture)
- [Getting started](#getting-started)
- [Environment variables](#environment-variables)
- [API reference](#api-reference)
- [Demo walkthrough](#demo-walkthrough)
- [Known limitations](#known-limitations)

---

## What it does

Most recruitment tooling scores one thing at a time: a resume, or an interview. The problem
is that those signals disagree, and the disagreement is the most useful information an HR
team has. This platform's core is a **ranking engine that joins three independent sources**:

```
   Job requisition            Parsed resume            Interview transcript
 (required skills,        (skills, years of         (per-skill scores from
  min experience)           experience)              the AI interviewer)
        │                        │                          │
        └────────────────────────┼──────────────────────────┘
                                 ▼
                    Skill match · Experience match · Interview performance
                                 ▼
                    Weighted score + cross-source conflict detection
                                 ▼
              Recommend hire / Advance / Further assessment / Reject
                        + the reasoning behind it
```

The output HR acts on is not a chat reply — it is a ranked list with matched skills, missing
skills, a recommendation, and an auditable explanation per candidate.

### Why this is not a chatbot

Recommendations are produced by **deterministic, explainable logic** (`backend/app/core/ranking.py`),
not by an LLM. The same inputs always produce the same recommendation, and every number can be
traced to the input that produced it. The LLM is used where generation is genuinely needed:
producing interview questions and grading answers.

---

## How the ranking works

**Signals and weights** (renormalised over whatever is available, so a candidate who has not
interviewed yet is not penalised for the missing score):

| Signal | Weight | Source |
|---|---|---|
| Skill match | 45% | required skills vs parsed resume |
| Experience match | 20% | candidate record, or years parsed from the resume |
| Interview performance | 35% | persisted per-skill interview scores |

**Gate:** if fewer than 50% of required skills are evidenced, the candidate is rejected
regardless of the blended score — a strong interview cannot mask missing mandatory skills.

**Cross-source flags** — the signals that only exist because multiple sources are combined:

| Flag | Meaning | Effect |
|---|---|---|
| `resume_interview_mismatch` | ≥75% skill match but interview < 55 | caps recommendation at *further assessment* |
| `outperformed_resume` | ≤50% skill match but interview ≥ 80 | resume likely understates the candidate |
| `partial_skill_gap` | some required skills missing | surfaced as a gap, not a rejection |
| `no_resume_text` | resume never parsed | lowers confidence, warns in the response |

Confidence is `high` only when all three signals are present and do not conflict.

---

## Feature status

### Implemented

| Area | What works |
|---|---|
| **Job requisitions** | Create/list/update roles with required skills, preferred skills, minimum experience |
| **Candidate records** | Candidates as HR-managed records (separate from login accounts), pipeline stages |
| **Resume parsing** | PDF/DOCX/TXT text extraction at upload time, with skill detection |
| **Skill matching** | 78 canonical skills / 187 aliases (`k8s`→Kubernetes, `postgres`→PostgreSQL, `c++` handled) |
| **Candidate ranking** | `POST /api/candidates/rank` — multi-source scoring, recommendations, reasoning |
| **Candidate profile** | Resume + job match + interviews + recommendation in one response |
| **HR dashboard** | Pipeline counts, aggregated skill gaps, recommended actions |
| **Interview agent** | AI-generated plan, dynamic questions, follow-ups, answer evaluation, live session |
| **Score persistence** | Interview scores computed once at end-of-interview and stored |
| **ATS scoring** | Resume-vs-role scoring against a stored resume or requisition |
| **Auth** | JWT signup/login, bcrypt hashing, HR-role gate on HR endpoints |

### Not implemented

Deliberately out of scope — the goal was depth on recruitment intelligence rather than
breadth across the whole employee lifecycle:

- Onboarding journeys, attrition prediction, policy reasoning, performance reviews
- Real camera/microphone analysis (no speech, emotion or body-language inference)
- Multi-language support (English only)
- Automated tests

---

## Architecture

```
┌───────────────────────────────────────────────────────────────┐
│ Frontend — React + Vite                                       │
│  /hr         HR intelligence dashboard (ranking + insights)   │
│  /pipeline   Requisitions, candidates, resume upload          │
│  /interview  Live AI interview (bindable to a candidate)      │
└───────────────────────────────────────────────────────────────┘
                              │ REST
┌───────────────────────────────────────────────────────────────┐
│ Backend — FastAPI                                             │
│                                                               │
│  routes/      jobs · candidates · hr_dashboard · resumes      │
│               interviews_live · answers · reports · analytics │
│                                                               │
│  core/        ranking.py         deterministic scoring        │
│               skills.py          extraction + matching        │
│               resume_text.py     PDF/DOCX/TXT parsing         │
│               hr_intelligence.py DB → ranking assembly        │
│               interview_plan · live_interview · report  (LLM) │
│                                                               │
│  models/      users · candidates · job_requisitions           │
│               resumes · interview_sessions · interview_turns  │
└───────────────────────────────────────────────────────────────┘
                              │
                    ┌─────────┴─────────┐
                    │  Google Gemini    │  (optional — deterministic
                    │  question gen,    │   fallbacks are used when
                    │  evaluation,      │   no API key is configured)
                    │  reports          │
                    └───────────────────┘
```

### Data model

```
JobRequisition ──< Candidate ──< Resume            (parsed text + skills)
                        │
                        └──< InterviewSession ──< InterviewTurn
                                    │
                                    └── overall_score, skill_scores  (persisted at end)
```

---

## Getting started

### Prerequisites

- Python 3.10+ (the config module uses `str | None` syntax)
- Node.js 18+

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Optional: configure AI + secrets
cp .env.example .env            # then edit

python -m uvicorn app.main:app --reload --port 8000
```

> **Schema changes require a fresh database.** The app uses
> `Base.metadata.create_all()` with no migration tool, so it creates missing *tables* but
> not missing *columns*. If you are upgrading an existing install, delete `backend/app.db`
> (or point `DATABASE_URL` at a new database) before starting.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

- Frontend: http://localhost:5173
- API docs: http://localhost:8000/docs

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./app.db` | Database connection string |
| `SECRET_KEY` | `CHANGE_ME_...` | JWT signing secret — **must** be changed for production |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` | Token lifetime |
| `GEMINI_API_KEY` | _none_ | Enables AI question generation, evaluation and reports |
| `GEMINI_MODEL` | `models/gemini-1.5-pro` | Gemini model name |
| `RESUME_UPLOAD_DIR` | `uploads/resumes` | Where uploaded resumes are stored |
| `RESUME_MAX_SIZE_MB` | `10` | Upload size limit |
| `BACKEND_CORS_ORIGINS` | localhost dev origins | Allowed CORS origins |
| `ENVIRONMENT` | `local` | `local` enables debug + dev CORS defaults |

Without `GEMINI_API_KEY` the system still runs end to end: interview questions come from a
built-in bank and reports use deterministic placeholder scoring. **Ranking, skill matching and
resume parsing never require an API key.**

Generate a secret:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

---

## API reference

### HR intelligence

```
POST   /api/jobs                        Create a requisition (title, required_skills, ...)
GET    /api/jobs                        List requisitions (?status=open)
GET    /api/jobs/{id}                   Read a requisition
PATCH  /api/jobs/{id}                   Update a requisition

POST   /api/candidates                  Create a candidate
GET    /api/candidates                  List candidates (?job_requisition_id, ?stage)
GET    /api/candidates/{id}             Read a candidate
PATCH  /api/candidates/{id}             Update a candidate (incl. pipeline stage)
GET    /api/candidates/{id}/profile     Candidate intelligence profile
POST   /api/candidates/rank             Rank candidates for a requisition  ★

GET    /api/hr/dashboard                Pipeline, skill gaps, recommended actions
```

★ The core endpoint. Example:

```bash
curl -X POST localhost:8000/api/candidates/rank \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"job_requisition_id": 1}'
```

```jsonc
{
  "job_title": "Senior Backend Engineer",
  "candidates_evaluated": 4,
  "rankings": [{
    "full_name": "Anita Rao",
    "final_score": 96.05,
    "skill_match_score": 100.0,
    "experience_match_score": 96.0,
    "interview_score": 91.0,
    "matched_skills": ["Python", "FastAPI", "PostgreSQL", "Kubernetes", "AWS"],
    "missing_skills": [],
    "recommendation": "recommend_hire",
    "confidence": "high",
    "data_sources": ["job_requirements", "resume", "interview", "candidate_record"],
    "reasoning": [
      "Matched 5 of 5 required skills (100%): Python, FastAPI, PostgreSQL, Kubernetes, AWS.",
      "8 years experience vs 5 required.",
      "Interview score 91/100 — System design 94, Problem solving 88."
    ]
  }],
  "skill_gaps": [{"skill": "Kubernetes", "candidates_missing": 2}],
  "warnings": []
}
```

### Resumes, interviews, auth

```
POST   /api/resumes/upload                        Upload + parse (multipart: file, candidate_id)
GET    /api/resumes                               List your uploads
GET    /api/resumes/{id}/text                     Extracted text + skills
GET    /api/resumes/candidates/{id}/latest        Latest parsed resume for a candidate

POST   /api/ats/score                             Score a resume (text, resume_id or candidate_id)
POST   /api/interviews/plan/generate              Generate an interview plan
POST   /api/interviews/live/start                 Start (optionally candidate_id + job_requisition_id)
POST   /api/interviews/live/{id}/submit           Submit an answer, get the next question
POST   /api/interviews/live/{id}/end              End, score and persist  ★
POST   /api/answers/evaluate                      Evaluate a single answer
GET    /api/reports/{interview_id}                Interview report
GET    /api/analytics/skills/progress             Skill progress (reads persisted scores)

POST   /api/auth/signup · /api/auth/login · GET /api/auth/me
```

Full interactive docs at `/docs`.

---

## Demo walkthrough

1. **Sign up** and land on the HR dashboard (`/hr`).
2. **Create a requisition** in `/pipeline` — e.g. *Senior Backend Engineer*, required skills
   `Python, FastAPI, PostgreSQL, Kubernetes, AWS`, minimum 5 years.
3. **Add candidates** with resume files. Parsed skills appear immediately in the candidate table.
4. **Rank** on `/hr` — candidates are ordered by role match, each with matched/missing skills.
   Click **Why?** to see the weighting and the reasoning.
5. **Interview** a candidate from the pipeline. The resume text is prefilled from the parsed
   file. On completion the score is persisted and the ranking updates — candidates whose
   interview contradicts their resume are flagged.

The most convincing part of the demo is step 5 on a strong-resume/weak-interview candidate:
the recommendation drops to *further assessment* and states why.

---

## Known limitations

1. **No migrations.** Schema changes need the SQLite file recreated (see above).
2. **Scanned PDFs yield no text.** There is no OCR; extraction status is recorded as `empty`
   and the affected candidates are flagged `no_resume_text` with a dashboard warning.
3. **Skill vocabulary is finite.** 78 canonical skills with 187 aliases; unknown requirements
   are still matched by literal text search, but without alias awareness.
4. **Interview scoring quality depends on Gemini.** Without an API key, reports fall back to
   fixed placeholder scores, so rankings will show identical interview scores.
5. **HR role gate is permissive.** All accounts default to `role="hr"`; the gate exists so a
   future candidate-facing portal can be excluded from the pipeline endpoints.
6. **No automated tests.**
7. **Ranking assumes one requisition per candidate.** Candidates can be ranked against any
   job, but each holds a single `job_requisition_id`; a full many-to-many application model
   would be the next step.

---

## License

Proprietary — All Rights Reserved.
