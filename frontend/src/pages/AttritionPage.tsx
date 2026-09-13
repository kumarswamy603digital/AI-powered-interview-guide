import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { HrNav } from "../components/HrNav";
import {
  AttritionAssessment,
  AttritionModelInfo,
  AttritionOverview,
  getAttritionModel,
  getAttritionOverview
} from "../api/workforce";

function AssessmentRow({ assessment }: { assessment: AttritionAssessment }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="rankRow">
      <div className="row space-between" style={{ alignItems: "flex-start", gap: 16 }}>
        <div style={{ flex: 1 }}>
          <div className="row" style={{ gap: 10, flexWrap: "wrap" }}>
            <span className={`badge risk-${assessment.risk_band}`}>
              {Math.round(assessment.risk_score)}
            </span>
            {assessment.employee_id ? (
              <Link to={`/people/${assessment.employee_id}`}>
                <strong>{assessment.full_name}</strong>
              </Link>
            ) : (
              <strong>{assessment.full_name}</strong>
            )}
            <span className="muted">
              {assessment.job_title} · {assessment.department}
            </span>
            <span className="chip">{assessment.confidence} confidence</span>
            <span className="chip">
              {assessment.signals_available}/{assessment.signals_total} signals
            </span>
          </div>
          <p style={{ margin: "8px 0 0", fontSize: 13 }}>{assessment.summary}</p>
        </div>
        <button className="btn secondary" type="button" onClick={() => setOpen((v) => !v)}>
          {open ? "Hide" : "Explain"}
        </button>
      </div>

      {open && (
        <div className="reasoning">
          <div className="reasoningTitle">Risk factors (contribution to the score)</div>
          <table className="componentTable">
            <thead>
              <tr>
                <th>Signal</th>
                <th>Risk</th>
                <th>Weight</th>
                <th>Adds</th>
                <th>Evidence</th>
              </tr>
            </thead>
            <tbody>
              {assessment.factors.map((factor) => (
                <tr key={factor.name}>
                  <td>{factor.label}</td>
                  <td>{Math.round(factor.risk)}</td>
                  <td>{Math.round(factor.weight * 100)}%</td>
                  <td>{factor.contribution.toFixed(1)}</td>
                  <td className="muted">{factor.evidence}</td>
                </tr>
              ))}
            </tbody>
          </table>

          {assessment.recommended_actions.length > 0 && (
            <>
              <div className="reasoningTitle">Retention actions</div>
              <ul className="insights">
                {assessment.recommended_actions.map((action, index) => (
                  <li key={index}>
                    <strong>{action.action}</strong> — {action.rationale}{" "}
                    <span className="muted">
                      (owner: {action.owner}; est. −{action.expected_risk_reduction} pts,{" "}
                      {action.priority} priority)
                    </span>
                  </li>
                ))}
              </ul>
            </>
          )}

          {assessment.protective_factors.length > 0 && (
            <p className="muted" style={{ marginTop: 8 }}>
              Protective: {assessment.protective_factors.map((f) => f.label).join(", ")}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

export function AttritionPage() {
  const [overview, setOverview] = useState<AttritionOverview | null>(null);
  const [model, setModel] = useState<AttritionModelInfo | null>(null);
  const [band, setBand] = useState<string>("");
  const [showModel, setShowModel] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([getAttritionOverview(band ? { band } : {}), getAttritionModel()])
      .then(([overviewData, modelData]) => {
        if (cancelled) return;
        setOverview(overviewData);
        setModel(modelData);
      })
      .catch((err) => {
        if (!cancelled) setError("Could not load attrition data. Is the backend seeded?");
        // eslint-disable-next-line no-console
        console.error(err);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [band]);

  return (
    <div className="layout wide">
      <div className="card" style={{ maxWidth: 1200 }}>
        <HrNav
          title="Attrition prediction"
          subtitle="Flight risk per employee from nine workforce signals, with the retention action each one implies."
        />

        {error && <div className="notice bad">{error}</div>}
        {loading && <p className="muted">Loading…</p>}

        {overview && (
          <>
            <div className="metrics" style={{ marginTop: 20 }}>
              <div className="metric">
                <div className="metricValue">{overview.employees_assessed}</div>
                <div className="metricLabel">Assessed</div>
              </div>
              <div className="metric">
                <div className="metricValue">{overview.average_risk}</div>
                <div className="metricLabel">Average risk</div>
              </div>
              {Object.entries(overview.band_distribution).map(([bandName, count]) => (
                <div className="metric" key={bandName}>
                  <div className={`metricValue ${bandName === "critical" || bandName === "high" ? "bad" : ""}`}>
                    {count}
                  </div>
                  <div className="metricLabel">{bandName}</div>
                </div>
              ))}
            </div>

            <div className="twoCol" style={{ marginTop: 24 }}>
              <section>
                <h2>Risk by department</h2>
                <table className="dataTable">
                  <thead>
                    <tr>
                      <th>Department</th>
                      <th>Employees</th>
                      <th>Avg risk</th>
                      <th>At risk</th>
                    </tr>
                  </thead>
                  <tbody>
                    {overview.by_department.map((row: any) => (
                      <tr key={String(row.department)}>
                        <td>{String(row.department)}</td>
                        <td>{String(row.employees)}</td>
                        <td>{String(row.average_risk)}</td>
                        <td>{String(row.at_risk)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>

              <section>
                <h2>What drives risk org-wide</h2>
                <table className="dataTable">
                  <thead>
                    <tr>
                      <th>Driver</th>
                      <th>Avg contribution</th>
                      <th>Employees</th>
                    </tr>
                  </thead>
                  <tbody>
                    {overview.top_drivers.map((row: any) => (
                      <tr key={String(row.factor)}>
                        <td>{String(row.label)}</td>
                        <td>{String(row.average_contribution)}</td>
                        <td>{String(row.employees_affected)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <button
                  className="btn secondary"
                  type="button"
                  style={{ marginTop: 12 }}
                  onClick={() => setShowModel((v) => !v)}
                >
                  {showModel ? "Hide model" : "How the model works"}
                </button>
              </section>
            </div>

            {showModel && model && (
              <div className="reasoning" style={{ marginTop: 16 }}>
                <div className="reasoningTitle">Approach</div>
                <p style={{ fontSize: 13 }}>{model.approach}</p>
                <div className="reasoningTitle">Signal weights</div>
                <table className="componentTable">
                  <thead>
                    <tr>
                      <th>Signal</th>
                      <th>Weight</th>
                    </tr>
                  </thead>
                  <tbody>
                    {model.signals.map((signal) => (
                      <tr key={signal.name}>
                        <td>{signal.label}</td>
                        <td>{Math.round(signal.weight * 100)}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <div className="reasoningTitle">Notes</div>
                <ul className="insights">
                  {model.notes.map((note, index) => (
                    <li key={index}>{note}</li>
                  ))}
                </ul>
              </div>
            )}

            <section style={{ marginTop: 28 }}>
              <div className="row space-between" style={{ flexWrap: "wrap", gap: 12 }}>
                <h2 style={{ margin: 0 }}>Employees ({overview.assessments.length})</h2>
                <div className="input" style={{ minWidth: 200 }}>
                  <select value={band} onChange={(e) => setBand(e.target.value)}>
                    <option value="">All bands</option>
                    <option value="critical">Critical only</option>
                    <option value="high">High only</option>
                    <option value="moderate">Moderate only</option>
                    <option value="low">Low only</option>
                  </select>
                </div>
              </div>
              <div className="stack" style={{ marginTop: 12 }}>
                {overview.assessments.map((assessment) => (
                  <AssessmentRow key={assessment.employee_id ?? assessment.full_name} assessment={assessment} />
                ))}
              </div>
            </section>
          </>
        )}
      </div>
    </div>
  );
}
