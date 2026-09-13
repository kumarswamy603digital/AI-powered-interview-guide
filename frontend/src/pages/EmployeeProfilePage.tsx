import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { HrNav } from "../components/HrNav";
import { Employee360, formatPercent, getEmployee360 } from "../api/workforce";

export function EmployeeProfilePage() {
  const { employeeId } = useParams();
  const [data, setData] = useState<Employee360 | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!employeeId) return;
    let cancelled = false;
    setLoading(true);
    getEmployee360(Number(employeeId))
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((err) => {
        if (!cancelled) setError("Could not load this employee.");
        // eslint-disable-next-line no-console
        console.error(err);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [employeeId]);

  const employee = data?.employee;
  const performance = data?.performance;
  const attrition = data?.attrition;

  return (
    <div className="layout wide">
      <div className="card" style={{ maxWidth: 1200 }}>
        <HrNav
          title={employee ? employee.full_name : "Employee"}
          subtitle={
            employee
              ? `${employee.job_title} · ${employee.department}${
                  employee.manager_name ? ` · reports to ${employee.manager_name}` : ""
                }`
              : undefined
          }
        />

        {error && <div className="notice bad">{error}</div>}
        {loading && <p className="muted">Loading…</p>}

        {data && employee && performance && attrition && (
          <>
            <div className="metrics" style={{ marginTop: 20 }}>
              <div className="metric">
                <div className={`metricValue ${attrition.risk_score >= 55 ? "bad" : ""}`}>
                  {Math.round(attrition.risk_score)}
                </div>
                <div className="metricLabel">Flight risk ({attrition.risk_band})</div>
              </div>
              <div className="metric">
                <div className="metricValue">{performance.latest_rating ?? "—"}</div>
                <div className="metricLabel">Latest rating ({performance.rating_trajectory})</div>
              </div>
              <div className="metric">
                <div className="metricValue">
                  {formatPercent(performance.goal_summary.weighted_attainment)}
                </div>
                <div className="metricLabel">Goal attainment</div>
              </div>
              <div className="metric">
                <div className="metricValue">
                  {employee.tenure_years ? `${employee.tenure_years.toFixed(1)}y` : "—"}
                </div>
                <div className="metricLabel">Tenure</div>
              </div>
              <div className="metric">
                <div className="metricValue">
                  {data.attendance.average_weekly_overtime ?? "—"}h
                </div>
                <div className="metricLabel">Weekly overtime</div>
              </div>
              <div className="metric">
                <div className="metricValue">
                  {formatPercent(
                    data.attendance.unplanned_absence_rate !== null &&
                      data.attendance.unplanned_absence_rate !== undefined
                      ? data.attendance.unplanned_absence_rate * 100
                      : null
                  )}
                </div>
                <div className="metricLabel">Unplanned absence</div>
              </div>
              <div className="metric">
                <div className="metricValue">{employee.compa_ratio ?? "—"}</div>
                <div className="metricLabel">Compa-ratio</div>
              </div>
              <div className="metric">
                <div className="metricValue">{employee.engagement_score ?? "—"}</div>
                <div className="metricLabel">Engagement</div>
              </div>
            </div>

            <div className="twoCol" style={{ marginTop: 28 }}>
              <section>
                <h2>Attrition risk</h2>
                <p className="muted">{attrition.summary}</p>
                <table className="componentTable">
                  <thead>
                    <tr>
                      <th>Signal</th>
                      <th>Risk</th>
                      <th>Adds</th>
                      <th>Evidence</th>
                    </tr>
                  </thead>
                  <tbody>
                    {attrition.factors.map((factor) => (
                      <tr key={factor.name}>
                        <td>{factor.label}</td>
                        <td>{Math.round(factor.risk)}</td>
                        <td>{factor.contribution.toFixed(1)}</td>
                        <td className="muted">{factor.evidence}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>

                {attrition.recommended_actions.length > 0 && (
                  <>
                    <div className="reasoningTitle">Retention actions</div>
                    <ul className="insights">
                      {attrition.recommended_actions.map((action, index) => (
                        <li key={index}>
                          <strong>{action.action}</strong> — {action.rationale}{" "}
                          <span className="muted">
                            ({action.owner}, est. −{action.expected_risk_reduction} pts)
                          </span>
                        </li>
                      ))}
                    </ul>
                  </>
                )}
              </section>

              <section>
                <h2>Performance intelligence</h2>
                <p className="muted">{performance.summary}</p>
                <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
                  <span className="chip">readiness: {performance.promotion_readiness}</span>
                  {performance.calibration && (
                    <span className="chip">
                      {performance.calibration} department average
                      {performance.calibration_delta !== null &&
                      performance.calibration_delta !== undefined
                        ? ` (${performance.calibration_delta > 0 ? "+" : ""}${performance.calibration_delta})`
                        : ""}
                    </span>
                  )}
                  {performance.feedback_sentiment !== null &&
                    performance.feedback_sentiment !== undefined && (
                      <span className="chip">
                        feedback sentiment {performance.feedback_sentiment > 0 ? "+" : ""}
                        {performance.feedback_sentiment}
                      </span>
                    )}
                </div>

                {performance.strengths.length > 0 && (
                  <>
                    <div className="reasoningTitle">Strengths</div>
                    {performance.strengths.map((theme) => (
                      <div key={theme.theme} className="themeRow">
                        <div className="row space-between">
                          <strong>{theme.theme}</strong>
                          <span className="muted">
                            {theme.sentiment > 0 ? "+" : ""}
                            {theme.sentiment} · {theme.mentions} mention(s)
                          </span>
                        </div>
                        {theme.evidence.slice(0, 2).map((line, index) => (
                          <p key={index} className="muted" style={{ margin: "4px 0 0" }}>
                            “{line}”
                          </p>
                        ))}
                      </div>
                    ))}
                  </>
                )}

                {performance.improvement_areas.length > 0 && (
                  <>
                    <div className="reasoningTitle">Development areas</div>
                    {performance.improvement_areas.map((theme) => (
                      <div key={theme.theme} className="themeRow negative">
                        <div className="row space-between">
                          <strong>{theme.theme}</strong>
                          <span className="muted">
                            {theme.sentiment} · {theme.mentions} mention(s)
                          </span>
                        </div>
                        {theme.evidence.slice(0, 2).map((line, index) => (
                          <p key={index} className="muted" style={{ margin: "4px 0 0" }}>
                            “{line}”
                          </p>
                        ))}
                      </div>
                    ))}
                  </>
                )}

                {performance.recommended_actions.length > 0 && (
                  <>
                    <div className="reasoningTitle">Recommended actions</div>
                    <ul className="insights">
                      {performance.recommended_actions.map((action, index) => (
                        <li key={index}>
                          <strong>{action.action}</strong> — {action.rationale}{" "}
                          <span className="muted">({action.owner})</span>
                        </li>
                      ))}
                    </ul>
                  </>
                )}
              </section>
            </div>

            <div className="twoCol" style={{ marginTop: 28 }}>
              <section>
                <h2>Skills</h2>
                <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
                  {data.skills.map((skill) => (
                    <span key={skill.id} className={`pill ${skill.verified ? "matched" : ""}`}>
                      {skill.skill} · {skill.proficiency}/5
                    </span>
                  ))}
                </div>
                {data.skill_gaps_for_role.length > 0 && (
                  <div className="notice warn">
                    Missing for this role: {data.skill_gaps_for_role.join(", ")}
                  </div>
                )}
              </section>

              <section>
                <h2>Goals</h2>
                {data.goals.length === 0 ? (
                  <p className="muted">No goals recorded.</p>
                ) : (
                  <table className="dataTable">
                    <tbody>
                      {data.goals.map((goal) => (
                        <tr key={goal.id}>
                          <td>{goal.title}</td>
                          <td>
                            <span
                              className={`pill ${
                                goal.status === "achieved"
                                  ? "matched"
                                  : goal.status === "missed"
                                    ? "missing"
                                    : ""
                              }`}
                            >
                              {goal.status.replace(/_/g, " ")}
                            </span>
                          </td>
                          <td className="muted">{Math.round(goal.progress)}%</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </section>
            </div>

            <div className="twoCol" style={{ marginTop: 28 }}>
              <section>
                <h2>Review history</h2>
                {data.reviews.length === 0 ? (
                  <p className="muted">No reviews recorded.</p>
                ) : (
                  data.reviews.map((review) => (
                    <div key={review.id} className="themeRow">
                      <div className="row space-between">
                        <strong>
                          {review.period} — {review.rating}/5
                        </strong>
                        {review.promotion_ready && (
                          <span className="chip">promotion: {review.promotion_ready}</span>
                        )}
                      </div>
                      {review.comments && (
                        <p className="muted" style={{ margin: "4px 0 0" }}>
                          {review.comments}
                        </p>
                      )}
                      {review.improvements.length > 0 && (
                        <p className="muted" style={{ margin: "4px 0 0" }}>
                          Development: {review.improvements.join("; ")}
                        </p>
                      )}
                    </div>
                  ))
                )}
              </section>

              <section>
                <h2>Feedback</h2>
                {data.feedback.length === 0 ? (
                  <p className="muted">No feedback recorded.</p>
                ) : (
                  data.feedback.map((item) => {
                    const sentiment = item.sentiment ?? item.inferred_sentiment;
                    return (
                      <div key={item.id} className="themeRow">
                        <div className="row space-between">
                          <span className="chip">{item.source}</span>
                          {sentiment !== null && sentiment !== undefined && (
                            <span className="muted">
                              sentiment {sentiment > 0 ? "+" : ""}
                              {sentiment.toFixed(2)}
                            </span>
                          )}
                        </div>
                        <p style={{ margin: "6px 0 0", fontSize: 13 }}>{item.content}</p>
                      </div>
                    );
                  })
                )}
              </section>
            </div>

            {data.onboarding_progress && (
              <section style={{ marginTop: 28 }}>
                <h2>Onboarding</h2>
                <div className="row" style={{ gap: 16, flexWrap: "wrap" }}>
                  <span className="muted">
                    {String(data.onboarding_progress.completed_tasks)}/
                    {String(data.onboarding_progress.total_tasks)} tasks complete (
                    {formatPercent(Number(data.onboarding_progress.completion_percent))})
                  </span>
                  <Link to="/onboarding">
                    <button className="btn secondary" type="button">
                      Open onboarding
                    </button>
                  </Link>
                </div>
                {(data.onboarding_progress.mandatory_outstanding ?? []).length > 0 && (
                  <div className="notice warn">
                    Outstanding mandatory tasks:{" "}
                    {(data.onboarding_progress.mandatory_outstanding as string[]).join(", ")}
                  </div>
                )}
              </section>
            )}
          </>
        )}
      </div>
    </div>
  );
}
