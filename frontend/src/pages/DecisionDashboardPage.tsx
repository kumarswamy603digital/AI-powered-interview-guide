import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { HrNav } from "../components/HrNav";
import {
  CrossSourceInsight,
  DecisionDashboard,
  formatPercent,
  getDecisionDashboard
} from "../api/workforce";

function Metric({
  label,
  value,
  tone
}: {
  label: string;
  value: number | string | null | undefined;
  tone?: "bad" | "warn" | "good";
}) {
  return (
    <div className="metric">
      <div className={`metricValue ${tone ?? ""}`}>
        {value === null || value === undefined ? "—" : value}
      </div>
      <div className="metricLabel">{label}</div>
    </div>
  );
}

function InsightCard({ insight }: { insight: CrossSourceInsight }) {
  return (
    <div className={`insightCard ${insight.severity}`}>
      <div className="row space-between" style={{ alignItems: "flex-start", gap: 12 }}>
        <strong style={{ fontSize: 14 }}>{insight.title}</strong>
        <span className={`badge sev-${insight.severity}`}>{insight.severity}</span>
      </div>
      <p style={{ margin: "8px 0", fontSize: 13, lineHeight: 1.55 }}>{insight.detail}</p>
      <div className="insightAction">
        <strong>Do this:</strong> {insight.recommended_action}
      </div>
      <div className="row" style={{ gap: 6, marginTop: 8, flexWrap: "wrap" }}>
        {insight.sources.map((source) => (
          <span key={source} className="chip source">
            {source.replace(/_/g, " ")}
          </span>
        ))}
      </div>
    </div>
  );
}

export function DecisionDashboardPage() {
  const [data, setData] = useState<DecisionDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getDecisionDashboard()
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(
            "Could not load the decision dashboard. Is the backend running and seeded (python -m scripts.seed_demo)?"
          );
        }
        // eslint-disable-next-line no-console
        console.error(err);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const headline = data?.headline ?? {};
  const risk = data?.workforce_risk ?? {};
  const skills = data?.skills ?? {};
  const performance = data?.performance ?? {};
  const attendance = data?.attendance ?? {};
  const recruitment = data?.recruitment ?? {};

  return (
    <div className="layout wide">
      <div className="card" style={{ maxWidth: 1200 }}>
        <HrNav
          title="HR decision dashboard"
          subtitle="Recruitment, attendance, performance, attrition and skills in one view — with the actions they imply."
        />

        {error && <div className="notice bad">{error}</div>}
        {loading && <p className="muted">Loading…</p>}

        {data && (
          <>
            <div className="metrics" style={{ marginTop: 20 }}>
              <Metric label="Headcount" value={headline.headcount} />
              <Metric
                label="High attrition risk"
                value={headline.high_attrition_risk}
                tone={Number(headline.high_attrition_risk) > 0 ? "bad" : undefined}
              />
              <Metric label="Avg risk score" value={headline.average_attrition_risk} />
              <Metric label="Avg rating" value={headline.average_performance_rating} />
              <Metric
                label="Critical skill gaps"
                value={headline.critical_skill_gaps}
                tone={Number(headline.critical_skill_gaps) > 0 ? "warn" : undefined}
              />
              <Metric label="Open requisitions" value={headline.open_requisitions} />
              <Metric label="Candidates" value={headline.candidates_in_pipeline} />
              <Metric label="Onboarding" value={headline.active_onboarding} />
            </div>

            <p className="muted" style={{ marginTop: 12 }}>
              Reasoning over: {(data.data_sources ?? []).join(", ")}
            </p>

            <section style={{ marginTop: 28 }}>
              <h2>
                Cross-source insights{" "}
                <span className="muted" style={{ fontSize: 13, fontWeight: 400 }}>
                  — findings that need more than one data source
                </span>
              </h2>
              {data.insights.length === 0 ? (
                <p className="muted">
                  No cross-source findings. Seed the demo data to see this populated.
                </p>
              ) : (
                <div className="insightGrid">
                  {data.insights.map((insight, index) => (
                    <InsightCard key={index} insight={insight} />
                  ))}
                </div>
              )}
            </section>

            <div className="twoCol" style={{ marginTop: 28 }}>
              <section>
                <h2>Retention watchlist</h2>
                {(risk.watchlist ?? []).length === 0 ? (
                  <p className="muted">Nobody is currently in the high or critical band.</p>
                ) : (
                  <table className="dataTable">
                    <thead>
                      <tr>
                        <th>Employee</th>
                        <th>Risk</th>
                        <th>Top driver</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(risk.watchlist ?? []).map((row: any) => (
                        <tr key={row.employee_id}>
                          <td>
                            <Link to={`/people/${row.employee_id}`}>
                              <strong>{row.name}</strong>
                            </Link>
                            <div className="muted">{row.department}</div>
                          </td>
                          <td>
                            <span className={`badge risk-${row.band}`}>
                              {Math.round(row.risk_score)}
                            </span>
                          </td>
                          <td className="muted">{row.top_driver}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
                <Link to="/attrition">
                  <button className="btn secondary" type="button" style={{ marginTop: 12 }}>
                    Full attrition analysis
                  </button>
                </Link>
              </section>

              <section>
                <h2>Skill gaps</h2>
                {(skills.top_gaps ?? []).length === 0 ? (
                  <p className="muted">No under-covered skills against current requirements.</p>
                ) : (
                  <table className="dataTable">
                    <thead>
                      <tr>
                        <th>Skill</th>
                        <th>Gap</th>
                        <th>Internal option</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(skills.top_gaps ?? []).slice(0, 6).map((row: any) => (
                        <tr key={row.skill}>
                          <td>
                            <strong>{row.skill}</strong>
                            <div className="muted">{row.importance}</div>
                          </td>
                          <td>
                            <span className={`badge ${row.status}`}>{row.gap}</span>
                          </td>
                          <td className="muted">{row.reskilling_candidate ?? "none"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
                <div className="row" style={{ gap: 16, marginTop: 12, flexWrap: "wrap" }}>
                  <span className="muted">
                    Current coverage: {formatPercent(skills.current_coverage)}
                  </span>
                  <span className="muted">
                    Future readiness: {formatPercent(skills.future_readiness)}
                  </span>
                </div>
                <Link to="/skills">
                  <button className="btn secondary" type="button" style={{ marginTop: 12 }}>
                    Open skill graph
                  </button>
                </Link>
              </section>
            </div>

            <div className="twoCol" style={{ marginTop: 28 }}>
              <section>
                <h2>Performance</h2>
                <div className="row" style={{ gap: 18, flexWrap: "wrap" }}>
                  <span className="muted">
                    Avg goal attainment: {formatPercent(performance.average_goal_attainment)}
                  </span>
                  <span className="muted">Declining: {performance.declining_count ?? 0}</span>
                  <span className="muted">
                    Promotion-ready: {(performance.promotion_ready ?? []).length}
                  </span>
                </div>
                <div className="row" style={{ gap: 8, marginTop: 12, flexWrap: "wrap" }}>
                  {Object.entries(performance.rating_distribution ?? {}).map(([band, count]) => (
                    <span key={band} className="pill">
                      {band.replace(/_/g, " ")}: {String(count)}
                    </span>
                  ))}
                </div>
                {(performance.common_development_themes ?? []).length > 0 && (
                  <p className="muted" style={{ marginTop: 12 }}>
                    Most common development themes:{" "}
                    {(performance.common_development_themes ?? [])
                      .map((t: any) => `${t.theme} (${t.employees})`)
                      .join(", ")}
                  </p>
                )}
              </section>

              <section>
                <h2>Attendance</h2>
                <div className="row" style={{ gap: 18, flexWrap: "wrap" }}>
                  <span className="muted">
                    Avg absence: {formatPercent(attendance.average_absence_rate)}
                  </span>
                  <span className="muted">
                    Avg weekly overtime: {attendance.average_weekly_overtime ?? "—"}h
                  </span>
                </div>
                {(attendance.overtime_watchlist ?? []).length > 0 && (
                  <>
                    <div className="reasoningTitle">Overtime watchlist</div>
                    <ul className="insights">
                      {(attendance.overtime_watchlist ?? []).slice(0, 5).map((row: any) => (
                        <li key={row.employee_id}>
                          {row.name} — {row.weekly_overtime}h/week ({row.department})
                        </li>
                      ))}
                    </ul>
                  </>
                )}
              </section>
            </div>

            <section style={{ marginTop: 28 }}>
              <h2>Recruitment</h2>
              <div className="row" style={{ gap: 18, flexWrap: "wrap" }}>
                <span className="muted">Ranked candidates: {recruitment.candidates_ranked ?? 0}</span>
                <span className="muted">Interviews scored: {recruitment.interviews_scored ?? 0}</span>
                <span className="muted">
                  Resume/interview conflicts: {(recruitment.conflicts ?? []).length}
                </span>
              </div>
              {(recruitment.top_candidates ?? []).length > 0 && (
                <table className="dataTable" style={{ marginTop: 12 }}>
                  <thead>
                    <tr>
                      <th>Candidate</th>
                      <th>Match</th>
                      <th>Recommendation</th>
                      <th>Missing</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(recruitment.top_candidates ?? []).map((row: any) => (
                      <tr key={row.name}>
                        <td>
                          <strong>{row.name}</strong>
                        </td>
                        <td>{Math.round(row.score)}%</td>
                        <td className="muted">{String(row.recommendation).replace(/_/g, " ")}</td>
                        <td className="muted">
                          {(row.missing_skills ?? []).join(", ") || "none"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </section>
          </>
        )}
      </div>
    </div>
  );
}
