import { useEffect, useState } from "react";
import { HrNav } from "../components/HrNav";
import {
  SKILL_STATUS_LABELS,
  SkillGraph,
  SkillNode,
  formatPercent,
  getSkillGraph
} from "../api/workforce";

function coverageWidth(node: SkillNode): number {
  const demand = Math.max(node.demand_current, node.demand_future);
  if (!demand) return 100;
  return Math.max(0, Math.min(100, (node.qualified_holders / demand) * 100));
}

function SkillRow({ node }: { node: SkillNode }) {
  const [open, setOpen] = useState(false);
  const demand = Math.max(node.demand_current, node.demand_future);

  return (
    <div className="rankRow">
      <div className="row space-between" style={{ alignItems: "flex-start", gap: 16 }}>
        <div style={{ flex: 1 }}>
          <div className="row" style={{ gap: 10, flexWrap: "wrap" }}>
            <strong>{node.skill}</strong>
            <span className={`badge ${node.status}`}>
              {SKILL_STATUS_LABELS[node.status] ?? node.status}
            </span>
            {node.importance && <span className="chip">{node.importance.replace(/_/g, " ")}</span>}
            {node.single_point_of_failure && (
              <span className="chip flag resume_interview_mismatch">Single point of failure</span>
            )}
            {node.hot_market_skill && <span className="chip">in demand externally</span>}
            {node.demand_future > 0 && <span className="chip">future need</span>}
          </div>

          <div className="row" style={{ gap: 16, marginTop: 10, flexWrap: "wrap" }}>
            <div className="miniScore">
              <span>Coverage</span>
              <div className="scoreBar">
                <div
                  className={
                    node.status === "critical_gap"
                      ? "bad"
                      : node.status === "at_risk"
                        ? "warn"
                        : "good"
                  }
                  style={{ width: `${coverageWidth(node)}%` }}
                />
              </div>
              <strong>
                {node.qualified_holders}/{demand || node.qualified_holders}
              </strong>
            </div>
            <span className="muted">
              current demand {node.demand_current} · future {node.demand_future}
            </span>
            {node.average_proficiency !== null && node.average_proficiency !== undefined && (
              <span className="muted">avg proficiency {node.average_proficiency}/5</span>
            )}
            {node.gap_current + node.gap_future > 0 && (
              <span className="muted">
                gap: {node.gap_current} now / {node.gap_future} future
              </span>
            )}
          </div>

          {node.recommended_action && (
            <div className="insightAction" style={{ marginTop: 10 }}>
              <strong>Do this:</strong> {node.recommended_action}
            </div>
          )}
        </div>
        <button className="btn secondary" type="button" onClick={() => setOpen((v) => !v)}>
          {open ? "Hide" : "Detail"}
        </button>
      </div>

      {open && (
        <div className="reasoning">
          {node.holders.length > 0 && (
            <>
              <div className="reasoningTitle">Who holds it</div>
              <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
                {node.holders.map((holder) => (
                  <span key={holder} className="pill matched">
                    {holder}
                  </span>
                ))}
              </div>
            </>
          )}

          {node.reskilling_candidates.length > 0 && (
            <>
              <div className="reasoningTitle">Reskilling candidates (train instead of hire)</div>
              <table className="componentTable">
                <thead>
                  <tr>
                    <th>Employee</th>
                    <th>Affinity</th>
                    <th>Why</th>
                  </tr>
                </thead>
                <tbody>
                  {node.reskilling_candidates.map((candidate) => (
                    <tr key={candidate.employee_id ?? candidate.full_name}>
                      <td>
                        {candidate.full_name}
                        <div className="muted">{candidate.department}</div>
                      </td>
                      <td>{formatPercent(candidate.affinity)}</td>
                      <td className="muted">{candidate.reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}

          {node.rationale && (
            <p className="muted" style={{ marginTop: 8 }}>
              Requirement rationale: {node.rationale}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

export function SkillGraphPage() {
  const [graph, setGraph] = useState<SkillGraph | null>(null);
  const [filter, setFilter] = useState<string>("gaps");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getSkillGraph()
      .then((data) => {
        if (!cancelled) setGraph(data);
      })
      .catch((err) => {
        if (!cancelled) setError("Could not load the skill graph. Is the backend seeded?");
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

  const summary = graph?.summary ?? {};
  const nodes = (graph?.nodes ?? []).filter((node) => {
    if (filter === "gaps") return node.status === "critical_gap" || node.status === "at_risk";
    if (filter === "future") return node.demand_future > 0;
    if (filter === "spof") return node.single_point_of_failure;
    if (filter === "covered") return node.status === "covered" || node.status === "surplus";
    return true;
  });

  return (
    <div className="layout wide">
      <div className="card" style={{ maxWidth: 1200 }}>
        <HrNav
          title="Workforce skill graph"
          subtitle="What the organisation has, against what it needs now and in future."
        />

        {error && <div className="notice bad">{error}</div>}
        {loading && <p className="muted">Loading…</p>}

        {graph && (
          <>
            <div className="metrics" style={{ marginTop: 20 }}>
              <div className="metric">
                <div className="metricValue">{summary.employees_mapped ?? 0}</div>
                <div className="metricLabel">Employees mapped</div>
              </div>
              <div className="metric">
                <div className="metricValue">{summary.skills_tracked ?? 0}</div>
                <div className="metricLabel">Skills tracked</div>
              </div>
              <div className="metric">
                <div className="metricValue">{formatPercent(summary.current_coverage)}</div>
                <div className="metricLabel">Current coverage</div>
              </div>
              <div className="metric">
                <div className={`metricValue ${Number(summary.future_readiness ?? 100) < 60 ? "bad" : ""}`}>
                  {formatPercent(summary.future_readiness)}
                </div>
                <div className="metricLabel">Future readiness</div>
              </div>
              <div className="metric">
                <div className={`metricValue ${(summary.critical_gaps ?? []).length ? "bad" : ""}`}>
                  {(summary.critical_gaps ?? []).length}
                </div>
                <div className="metricLabel">Critical gaps</div>
              </div>
              <div className="metric">
                <div className={`metricValue ${(summary.single_points_of_failure ?? []).length ? "warn" : ""}`}>
                  {(summary.single_points_of_failure ?? []).length}
                </div>
                <div className="metricLabel">Single points of failure</div>
              </div>
            </div>

            {(summary.single_points_of_failure ?? []).length > 0 && (
              <div className="notice warn">
                Only one qualified person holds:{" "}
                {(summary.single_points_of_failure ?? [])
                  .map((row: any) => `${row.skill} (${row.holder})`)
                  .join(", ")}
                . Cross-train a second person for each.
              </div>
            )}

            {(summary.category_coverage ?? []).length > 0 && (
              <section style={{ marginTop: 24 }}>
                <h2>Coverage by category</h2>
                <table className="dataTable">
                  <thead>
                    <tr>
                      <th>Category</th>
                      <th>Demand</th>
                      <th>Qualified</th>
                      <th>Gap</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(summary.category_coverage ?? []).map((row: any) => (
                      <tr key={String(row.category)}>
                        <td>{String(row.category)}</td>
                        <td>{String(row.demand)}</td>
                        <td>{String(row.qualified)}</td>
                        <td className={Number(row.gap) > 0 ? "" : "muted"}>{String(row.gap)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>
            )}

            <section style={{ marginTop: 28 }}>
              <div className="row space-between" style={{ flexWrap: "wrap", gap: 12 }}>
                <h2 style={{ margin: 0 }}>Skills ({nodes.length})</h2>
                <div className="input" style={{ minWidth: 220 }}>
                  <select value={filter} onChange={(e) => setFilter(e.target.value)}>
                    <option value="gaps">Gaps and at-risk</option>
                    <option value="future">Future requirements</option>
                    <option value="spof">Single points of failure</option>
                    <option value="covered">Covered</option>
                    <option value="all">All skills</option>
                  </select>
                </div>
              </div>
              <div className="stack" style={{ marginTop: 12 }}>
                {nodes.length === 0 ? (
                  <p className="muted">Nothing matches this filter.</p>
                ) : (
                  nodes.map((node) => <SkillRow key={node.skill} node={node} />)
                )}
              </div>
            </section>
          </>
        )}
      </div>
    </div>
  );
}
