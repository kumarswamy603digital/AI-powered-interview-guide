import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  CandidateRanking,
  FLAG_LABELS,
  HrDashboard,
  JobRequisition,
  RankResponse,
  RECOMMENDATION_LABELS,
  getHrDashboard,
  listJobs,
  rankCandidates
} from "../api/hr";
import { useAuth } from "../hooks/useAuth";

function scoreClass(score: number): string {
  if (score >= 78) return "good";
  if (score >= 60) return "warn";
  return "bad";
}

function Metric({ label, value, hint }: { label: string; value: number | string; hint?: string }) {
  return (
    <div className="metric">
      <div className="metricValue">{value}</div>
      <div className="metricLabel">{label}</div>
      {hint && <div className="metricHint">{hint}</div>}
    </div>
  );
}

function RankingRow({ ranking, rank }: { ranking: CandidateRanking; rank: number }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="rankRow">
      <div className="row space-between" style={{ alignItems: "flex-start", gap: 16 }}>
        <div style={{ flex: 1 }}>
          <div className="row" style={{ gap: 10, flexWrap: "wrap" }}>
            <span className="rankIndex">#{rank}</span>
            <strong style={{ fontSize: 15 }}>{ranking.full_name}</strong>
            <span className={`badge ${ranking.recommendation}`}>
              {RECOMMENDATION_LABELS[ranking.recommendation]}
            </span>
            <span className="chip">{ranking.confidence} confidence</span>
            {ranking.flags.map((flag) => (
              <span key={flag} className={`chip flag ${flag}`}>
                {FLAG_LABELS[flag] ?? flag}
              </span>
            ))}
          </div>

          <div className="row" style={{ gap: 18, marginTop: 10, flexWrap: "wrap" }}>
            <div className="miniScore">
              <span>Role match</span>
              <div className="scoreBar">
                <div
                  className={scoreClass(ranking.final_score)}
                  style={{ width: `${Math.max(0, Math.min(100, ranking.final_score))}%` }}
                />
              </div>
              <strong>{Math.round(ranking.final_score)}%</strong>
            </div>
            <span className="muted">Skills {Math.round(ranking.skill_match_score)}%</span>
            <span className="muted">
              Experience{" "}
              {ranking.experience_match_score === null ||
              ranking.experience_match_score === undefined
                ? "—"
                : `${Math.round(ranking.experience_match_score)}%`}
            </span>
            <span className="muted">
              Interview{" "}
              {ranking.interview_score === null || ranking.interview_score === undefined
                ? "not held"
                : `${Math.round(ranking.interview_score)}/100`}
            </span>
          </div>

          <div className="row" style={{ gap: 6, marginTop: 10, flexWrap: "wrap" }}>
            {ranking.matched_skills.map((skill) => (
              <span key={skill} className="pill matched">
                {skill}
              </span>
            ))}
            {ranking.missing_skills.map((skill) => (
              <span key={skill} className="pill missing">
                {skill}
              </span>
            ))}
          </div>
        </div>

        <button className="btn secondary" type="button" onClick={() => setExpanded((v) => !v)}>
          {expanded ? "Hide why" : "Why?"}
        </button>
      </div>

      {expanded && (
        <div className="reasoning">
          <div className="reasoningTitle">How this score was produced</div>
          <ul>
            {ranking.reasoning.map((line, idx) => (
              <li key={idx}>{line}</li>
            ))}
          </ul>
          <div className="reasoningTitle">Weighting</div>
          <table className="componentTable">
            <thead>
              <tr>
                <th>Signal</th>
                <th>Score</th>
                <th>Weight</th>
                <th>Basis</th>
              </tr>
            </thead>
            <tbody>
              {ranking.components.map((component) => (
                <tr key={component.name}>
                  <td>{component.name.replace(/_/g, " ")}</td>
                  <td>{Math.round(component.score)}</td>
                  <td>{Math.round(component.weight * 100)}%</td>
                  <td className="muted">{component.detail}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="muted" style={{ marginTop: 8 }}>
            Data sources: {ranking.data_sources.join(", ")}
            {ranking.additional_skills.length > 0 && (
              <> · Additional skills: {ranking.additional_skills.join(", ")}</>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export function HrDashboardPage() {
  const { user, logout } = useAuth();
  const [dashboard, setDashboard] = useState<HrDashboard | null>(null);
  const [jobs, setJobs] = useState<JobRequisition[]>([]);
  const [selectedJobId, setSelectedJobId] = useState<number | null>(null);
  const [ranking, setRanking] = useState<RankResponse | null>(null);
  const [includeUnassigned, setIncludeUnassigned] = useState(false);
  const [loading, setLoading] = useState(true);
  const [rankLoading, setRankLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadOverview = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [dashboardData, jobsData] = await Promise.all([getHrDashboard(), listJobs()]);
      setDashboard(dashboardData);
      setJobs(jobsData);
      setSelectedJobId((current) => current ?? (jobsData.length > 0 ? jobsData[0].id : null));
    } catch (err) {
      setError("Could not load the HR dashboard. Is the backend running?");
      // eslint-disable-next-line no-console
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadOverview();
  }, [loadOverview]);

  useEffect(() => {
    if (selectedJobId === null) {
      setRanking(null);
      return;
    }
    let cancelled = false;
    setRankLoading(true);
    rankCandidates(selectedJobId, { includeUnassigned })
      .then((data) => {
        if (!cancelled) setRanking(data);
      })
      .catch((err) => {
        if (!cancelled) setRanking(null);
        // eslint-disable-next-line no-console
        console.error(err);
      })
      .finally(() => {
        if (!cancelled) setRankLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedJobId, includeUnassigned]);

  const selectedJob = useMemo(
    () => jobs.find((job) => job.id === selectedJobId) ?? null,
    [jobs, selectedJobId]
  );

  return (
    <div className="layout wide">
      <div className="card" style={{ maxWidth: 1100 }}>
        <div className="row space-between" style={{ alignItems: "flex-start" }}>
          <div>
            <h1 style={{ marginBottom: 4 }}>HR intelligence dashboard</h1>
            <p className="muted" style={{ margin: 0 }}>
              Recruitment pipeline, skill gaps and hiring recommendations for{" "}
              {user?.full_name || user?.email}
            </p>
          </div>
          <div className="row" style={{ gap: 8 }}>
            <Link to="/pipeline">
              <button className="btn secondary" type="button">
                Manage pipeline
              </button>
            </Link>
            <button className="btn secondary" type="button" onClick={logout}>
              Log out
            </button>
          </div>
        </div>

        {error && <div className="notice bad">{error}</div>}
        {loading && <p className="muted">Loading…</p>}

        {dashboard && (
          <>
            <div className="metrics">
              <Metric label="Open requisitions" value={dashboard.open_jobs} />
              <Metric label="Candidates" value={dashboard.total_candidates} />
              <Metric label="Interviews scored" value={dashboard.interviews_completed} />
              <Metric
                label="Awaiting interview"
                value={dashboard.candidates_awaiting_interview}
              />
              <Metric
                label="Unparsed resumes"
                value={dashboard.candidates_missing_resume_text}
                hint={dashboard.candidates_missing_resume_text > 0 ? "skill match unreliable" : undefined}
              />
            </div>

            <section style={{ marginTop: 24 }}>
              <h2>Pipeline</h2>
              <div className="pipeline">
                {(
                  [
                    ["Applied", dashboard.pipeline.applied],
                    ["Screened", dashboard.pipeline.screened],
                    ["Interviewed", dashboard.pipeline.interviewed],
                    ["Recommended", dashboard.pipeline.recommended],
                    ["Hired", dashboard.pipeline.hired],
                    ["Rejected", dashboard.pipeline.rejected]
                  ] as [string, number][]
                ).map(([label, count]) => (
                  <div key={label} className="pipelineStage">
                    <div className="pipelineCount">{count}</div>
                    <div className="pipelineLabel">{label}</div>
                  </div>
                ))}
              </div>
            </section>

            {dashboard.insights.length > 0 && (
              <section style={{ marginTop: 24 }}>
                <h2>Recommended actions</h2>
                <ul className="insights">
                  {dashboard.insights.map((insight, idx) => (
                    <li key={idx}>{insight}</li>
                  ))}
                </ul>
              </section>
            )}

            {dashboard.top_skill_gaps.length > 0 && (
              <section style={{ marginTop: 24 }}>
                <h2>Skill gaps across open roles</h2>
                <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
                  {dashboard.top_skill_gaps.map((gap) => (
                    <span key={gap.skill} className="pill missing">
                      {gap.skill} · {gap.candidates_missing} missing
                    </span>
                  ))}
                </div>
              </section>
            )}
          </>
        )}

        <section style={{ marginTop: 28 }}>
          <div className="row space-between" style={{ flexWrap: "wrap", gap: 12 }}>
            <h2 style={{ margin: 0 }}>Candidate ranking</h2>
            <div className="row" style={{ gap: 12, flexWrap: "wrap" }}>
              <div className="input" style={{ minWidth: 260 }}>
                <select
                  value={selectedJobId ?? ""}
                  onChange={(e) =>
                    setSelectedJobId(e.target.value === "" ? null : Number(e.target.value))
                  }
                >
                  <option value="">Select a requisition…</option>
                  {jobs.map((job) => (
                    <option key={job.id} value={job.id}>
                      {job.title} ({job.candidate_count} candidates)
                    </option>
                  ))}
                </select>
              </div>
              <label className="row" style={{ gap: 6, fontSize: 13 }}>
                <input
                  type="checkbox"
                  checked={includeUnassigned}
                  onChange={(e) => setIncludeUnassigned(e.target.checked)}
                />
                Include unassigned candidates
              </label>
            </div>
          </div>

          {jobs.length === 0 && !loading && (
            <div className="notice">
              No requisitions yet. <Link to="/pipeline">Create one</Link> and add candidates to see
              rankings.
            </div>
          )}

          {selectedJob && (
            <p className="muted" style={{ marginTop: 12 }}>
              Requires: {selectedJob.required_skills.join(", ") || "no skills specified"}
              {selectedJob.min_years_experience
                ? ` · ${selectedJob.min_years_experience}+ years`
                : ""}
            </p>
          )}

          {rankLoading && <p className="muted">Ranking candidates…</p>}

          {ranking?.warnings.map((warning, idx) => (
            <div key={idx} className="notice warn">
              {warning}
            </div>
          ))}

          {ranking && ranking.rankings.length > 0 && (
            <div className="stack" style={{ marginTop: 12 }}>
              {ranking.rankings.map((row, idx) => (
                <RankingRow key={row.candidate_id ?? idx} ranking={row} rank={idx + 1} />
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
