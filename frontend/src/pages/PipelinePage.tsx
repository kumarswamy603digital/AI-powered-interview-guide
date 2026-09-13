import { FormEvent, useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  Candidate,
  CandidateStage,
  JobRequisition,
  createCandidate,
  createJob,
  listCandidates,
  listJobs,
  updateCandidateStage,
  uploadResume
} from "../api/hr";

const STAGES: CandidateStage[] = [
  "applied",
  "screened",
  "interviewed",
  "recommended",
  "rejected",
  "hired"
];

function parseSkills(value: string): string[] {
  return value
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);
}

function extractionMessage(candidate: Candidate): string {
  if (candidate.has_resume_text) {
    return `${candidate.extracted_skills.length} skills detected`;
  }
  return "no resume text";
}

export function PipelinePage() {
  const navigate = useNavigate();
  const [jobs, setJobs] = useState<JobRequisition[]>([]);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [selectedJobId, setSelectedJobId] = useState<number | "">("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [jobsData, candidatesData] = await Promise.all([listJobs(), listCandidates()]);
      setJobs(jobsData);
      setCandidates(candidatesData);
    } catch (err) {
      setError("Could not load jobs and candidates. Is the backend running?");
      // eslint-disable-next-line no-console
      console.error(err);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function handleCreateJob(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const data = new FormData(form);
    const required = parseSkills(String(data.get("required_skills") || ""));
    if (required.length === 0) {
      setError("Add at least one required skill — ranking needs something to match against.");
      return;
    }

    setBusy(true);
    setError(null);
    try {
      const job = await createJob({
        title: String(data.get("title") || ""),
        department: String(data.get("department") || "") || undefined,
        seniority: String(data.get("seniority") || "") || undefined,
        required_skills: required,
        preferred_skills: parseSkills(String(data.get("preferred_skills") || "")),
        min_years_experience: data.get("min_years")
          ? Number(data.get("min_years"))
          : undefined,
        description: String(data.get("description") || "") || undefined
      });
      setMessage(`Created requisition "${job.title}".`);
      form.reset();
      await refresh();
    } catch (err) {
      setError("Could not create the requisition.");
      // eslint-disable-next-line no-console
      console.error(err);
    } finally {
      setBusy(false);
    }
  }

  async function handleAddCandidate(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const data = new FormData(form);
    const file = data.get("resume") as File | null;
    const jobId = data.get("job_requisition_id");

    setBusy(true);
    setError(null);
    try {
      const candidate = await createCandidate({
        full_name: String(data.get("full_name") || ""),
        email: String(data.get("email") || "") || undefined,
        current_title: String(data.get("current_title") || "") || undefined,
        years_experience: data.get("years_experience")
          ? Number(data.get("years_experience"))
          : undefined,
        source: String(data.get("source") || "") || undefined,
        job_requisition_id: jobId ? Number(jobId) : undefined
      });

      if (file && file.size > 0) {
        const upload = await uploadResume(file, candidate.id);
        if (upload.extraction_status === "ok") {
          setMessage(
            `Added ${candidate.full_name}; parsed ${upload.extracted_characters} characters and ` +
              `detected ${upload.extracted_skills.length} skills.`
          );
        } else {
          setMessage(
            `Added ${candidate.full_name}, but the resume could not be parsed ` +
              `(${upload.extraction_status}: ${upload.extraction_detail ?? "unknown reason"}).`
          );
        }
      } else {
        setMessage(`Added ${candidate.full_name}. Upload a resume to enable skill matching.`);
      }

      form.reset();
      await refresh();
    } catch (err) {
      setError("Could not add the candidate.");
      // eslint-disable-next-line no-console
      console.error(err);
    } finally {
      setBusy(false);
    }
  }

  async function handleStageChange(candidate: Candidate, stage: CandidateStage) {
    try {
      await updateCandidateStage(candidate.id, stage);
      await refresh();
    } catch (err) {
      setError("Could not update the candidate stage.");
      // eslint-disable-next-line no-console
      console.error(err);
    }
  }

  const visibleCandidates =
    selectedJobId === ""
      ? candidates
      : candidates.filter((c) => c.job_requisition_id === selectedJobId);

  return (
    <div className="layout wide">
      <div className="card" style={{ maxWidth: 1100 }}>
        <div className="row space-between" style={{ alignItems: "flex-start" }}>
          <div>
            <h1 style={{ marginBottom: 4 }}>Recruitment pipeline</h1>
            <p className="muted" style={{ margin: 0 }}>
              Create requisitions, add candidates and upload resumes for parsing.
            </p>
          </div>
          <Link to="/hr">
            <button className="btn secondary" type="button">
              Back to dashboard
            </button>
          </Link>
        </div>

        {message && <div className="notice good">{message}</div>}
        {error && <div className="notice bad">{error}</div>}

        <div className="twoCol" style={{ marginTop: 20 }}>
          <section>
            <h2>New requisition</h2>
            <form onSubmit={handleCreateJob} className="stack">
              <div className="input">
                <label htmlFor="title">Title</label>
                <input id="title" name="title" required placeholder="Senior Backend Engineer" />
              </div>
              <div className="row" style={{ gap: 8 }}>
                <div className="input" style={{ flex: 1 }}>
                  <label htmlFor="department">Department</label>
                  <input id="department" name="department" placeholder="Engineering" />
                </div>
                <div className="input" style={{ flex: 1 }}>
                  <label htmlFor="seniority">Seniority</label>
                  <input id="seniority" name="seniority" placeholder="Senior" />
                </div>
              </div>
              <div className="input">
                <label htmlFor="required_skills">Required skills (comma separated)</label>
                <input
                  id="required_skills"
                  name="required_skills"
                  required
                  placeholder="Python, FastAPI, PostgreSQL, Kubernetes"
                />
              </div>
              <div className="input">
                <label htmlFor="preferred_skills">Preferred skills</label>
                <input id="preferred_skills" name="preferred_skills" placeholder="Redis, Terraform" />
              </div>
              <div className="input">
                <label htmlFor="min_years">Minimum years of experience</label>
                <input id="min_years" name="min_years" type="number" min={0} step={0.5} />
              </div>
              <div className="input">
                <label htmlFor="description">Description</label>
                <textarea id="description" name="description" rows={3} />
              </div>
              <button className="btn" type="submit" disabled={busy}>
                Create requisition
              </button>
            </form>
          </section>

          <section>
            <h2>Add candidate</h2>
            <form onSubmit={handleAddCandidate} className="stack">
              <div className="input">
                <label htmlFor="full_name">Full name</label>
                <input id="full_name" name="full_name" required placeholder="Priya Raman" />
              </div>
              <div className="row" style={{ gap: 8 }}>
                <div className="input" style={{ flex: 1 }}>
                  <label htmlFor="email">Email</label>
                  <input id="email" name="email" type="email" placeholder="priya@example.com" />
                </div>
                <div className="input" style={{ flex: 1 }}>
                  <label htmlFor="years_experience">Years experience</label>
                  <input
                    id="years_experience"
                    name="years_experience"
                    type="number"
                    min={0}
                    step={0.5}
                  />
                </div>
              </div>
              <div className="input">
                <label htmlFor="current_title">Current title</label>
                <input id="current_title" name="current_title" placeholder="Backend Engineer" />
              </div>
              <div className="row" style={{ gap: 8 }}>
                <div className="input" style={{ flex: 1 }}>
                  <label htmlFor="source">Source</label>
                  <input id="source" name="source" placeholder="Referral" />
                </div>
                <div className="input" style={{ flex: 1 }}>
                  <label htmlFor="job_requisition_id">Requisition</label>
                  <select id="job_requisition_id" name="job_requisition_id">
                    <option value="">Unassigned</option>
                    {jobs.map((job) => (
                      <option key={job.id} value={job.id}>
                        {job.title}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
              <div className="input">
                <label htmlFor="resume">Resume (PDF, DOCX or TXT)</label>
                <input id="resume" name="resume" type="file" accept=".pdf,.docx,.txt" />
              </div>
              <button className="btn" type="submit" disabled={busy}>
                Add candidate
              </button>
            </form>
          </section>
        </div>

        <section style={{ marginTop: 28 }}>
          <div className="row space-between" style={{ flexWrap: "wrap", gap: 12 }}>
            <h2 style={{ margin: 0 }}>Candidates ({visibleCandidates.length})</h2>
            <div className="input" style={{ minWidth: 240 }}>
              <select
                value={selectedJobId}
                onChange={(e) =>
                  setSelectedJobId(e.target.value === "" ? "" : Number(e.target.value))
                }
              >
                <option value="">All requisitions</option>
                {jobs.map((job) => (
                  <option key={job.id} value={job.id}>
                    {job.title}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {visibleCandidates.length === 0 ? (
            <p className="muted">No candidates yet.</p>
          ) : (
            <table className="dataTable" style={{ marginTop: 12 }}>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Requisition</th>
                  <th>Resume</th>
                  <th>Interviews</th>
                  <th>Stage</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {visibleCandidates.map((candidate) => {
                  const job = jobs.find((j) => j.id === candidate.job_requisition_id);
                  return (
                    <tr key={candidate.id}>
                      <td>
                        <strong>{candidate.full_name}</strong>
                        <div className="muted">{candidate.current_title ?? "—"}</div>
                      </td>
                      <td className="muted">{job?.title ?? "Unassigned"}</td>
                      <td>
                        <span className={candidate.has_resume_text ? "pill matched" : "pill missing"}>
                          {extractionMessage(candidate)}
                        </span>
                      </td>
                      <td className="muted">
                        {candidate.interviews_completed === 0
                          ? "—"
                          : `${candidate.interviews_completed} · ${
                              candidate.latest_interview_score
                                ? Math.round(candidate.latest_interview_score)
                                : "?"
                            }/100`}
                      </td>
                      <td>
                        <select
                          value={candidate.stage}
                          onChange={(e) =>
                            void handleStageChange(candidate, e.target.value as CandidateStage)
                          }
                        >
                          {STAGES.map((stage) => (
                            <option key={stage} value={stage}>
                              {stage}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td>
                        <button
                          className="btn secondary"
                          type="button"
                          disabled={!candidate.has_resume_text || !job}
                          title={
                            !job
                              ? "Assign the candidate to a requisition first"
                              : !candidate.has_resume_text
                                ? "Upload a parseable resume first"
                                : "Interview this candidate"
                          }
                          onClick={() =>
                            navigate(
                              `/interview?candidate_id=${candidate.id}&job_id=${job?.id ?? ""}`
                            )
                          }
                        >
                          Interview
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </section>
      </div>
    </div>
  );
}
