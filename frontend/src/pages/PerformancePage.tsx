import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { HrNav } from "../components/HrNav";
import {
  PerformanceInsight,
  formatPercent,
  listPerformanceInsights
} from "../api/workforce";

function trajectoryTone(trajectory: string): string {
  if (trajectory === "improving") return "good";
  if (trajectory === "declining") return "bad";
  return "";
}

function InsightRow({ insight }: { insight: PerformanceInsight }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="rankRow">
      <div className="row space-between" style={{ alignItems: "flex-start", gap: 16 }}>
        <div style={{ flex: 1 }}>
          <div className="row" style={{ gap: 10, flexWrap: "wrap" }}>
            {insight.employee_id ? (
              <Link to={`/people/${insight.employee_id}`}>
                <strong>{insight.full_name}</strong>
              </Link>
            ) : (
              <strong>{insight.full_name}</strong>
            )}
            <span className="muted">
              {insight.job_title} · {insight.department}
            </span>
            <span className={`chip ${trajectoryTone(insight.rating_trajectory)}`}>
              {insight.rating_trajectory}
              {insight.rating_delta !== null && insight.rating_delta !== undefined
                ? ` (${insight.rating_delta > 0 ? "+" : ""}${insight.rating_delta})`
                : ""}
            </span>
            <span className={`badge ${insight.promotion_readiness === "ready" ? "covered" : ""}`}>
              {insight.promotion_readiness.replace(/_/g, " ")}
            </span>
          </div>

          <div className="row" style={{ gap: 18, marginTop: 10, flexWrap: "wrap" }}>
            <div className="miniScore">
              <span>Overall</span>
              <div className="scoreBar">
                <div
                  className={
                    insight.overall_score >= 75 ? "good" : insight.overall_score >= 55 ? "warn" : "bad"
                  }
                  style={{ width: `${Math.max(0, Math.min(100, insight.overall_score))}%` }}
                />
              </div>
              <strong>{Math.round(insight.overall_score)}</strong>
            </div>
            <span className="muted">rating {insight.latest_rating ?? "—"}/5</span>
            <span className="muted">
              goals {formatPercent(insight.goal_summary.weighted_attainment)} (
              {insight.goal_summary.achieved}/{insight.goal_summary.total})
            </span>
            {insight.calibration && (
              <span className="muted">{insight.calibration} dept average</span>
            )}
          </div>

          <div className="row" style={{ gap: 6, marginTop: 10, flexWrap: "wrap" }}>
            {insight.strengths.slice(0, 3).map((theme) => (
              <span key={theme.theme} className="pill matched">
                {theme.theme}
              </span>
            ))}
            {insight.improvement_areas.slice(0, 3).map((theme) => (
              <span key={theme.theme} className="pill missing">
                {theme.theme}
              </span>
            ))}
          </div>
        </div>
        <button className="btn secondary" type="button" onClick={() => setOpen((v) => !v)}>
          {open ? "Hide" : "Detail"}
        </button>
      </div>

      {open && (
        <div className="reasoning">
          <p style={{ fontSize: 13 }}>{insight.summary}</p>

          {insight.strengths.length > 0 && (
            <>
              <div className="reasoningTitle">Strengths and evidence</div>
              {insight.strengths.map((theme) => (
                <div key={theme.theme} className="themeRow">
                  <div className="row space-between">
                    <strong>{theme.theme}</strong>
                    <span className="muted">
                      {theme.sentiment > 0 ? "+" : ""}
                      {theme.sentiment} from {theme.sources.join(", ")}
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

          {insight.improvement_areas.length > 0 && (
            <>
              <div className="reasoningTitle">Development areas</div>
              {insight.improvement_areas.map((theme) => (
                <div key={theme.theme} className="themeRow negative">
                  <div className="row space-between">
                    <strong>{theme.theme}</strong>
                    <span className="muted">{theme.sentiment}</span>
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

          {insight.recommended_actions.length > 0 && (
            <>
              <div className="reasoningTitle">Recommended actions</div>
              <ul className="insights">
                {insight.recommended_actions.map((action, index) => (
                  <li key={index}>
                    <strong>{action.action}</strong> — {action.rationale}{" "}
                    <span className="muted">
                      ({action.owner}, {action.priority} priority)
                    </span>
                  </li>
                ))}
              </ul>
            </>
          )}

          <p className="muted" style={{ marginTop: 8 }}>
            Sources: {insight.data_sources.join(", ") || "none"}
          </p>
        </div>
      )}
    </div>
  );
}

export function PerformancePage() {
  const [insights, setInsights] = useState<PerformanceInsight[]>([]);
  const [trajectory, setTrajectory] = useState("");
  const [readiness, setReadiness] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    listPerformanceInsights({
      trajectory: trajectory || undefined,
      promotion_readiness: readiness || undefined
    })
      .then((data) => {
        if (!cancelled) setInsights(data);
      })
      .catch((err) => {
        if (!cancelled) setError("Could not load performance insights. Is the backend seeded?");
        // eslint-disable-next-line no-console
        console.error(err);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [trajectory, readiness]);

  const declining = insights.filter((i) => i.rating_trajectory === "declining").length;
  const ready = insights.filter((i) => i.promotion_readiness === "ready").length;

  return (
    <div className="layout wide">
      <div className="card" style={{ maxWidth: 1200 }}>
        <HrNav
          title="Performance intelligence"
          subtitle="Strengths and development areas derived from goals, feedback themes and review history — with the evidence behind each."
        />

        {error && <div className="notice bad">{error}</div>}
        {loading && <p className="muted">Loading…</p>}

        <div className="metrics" style={{ marginTop: 20 }}>
          <div className="metric">
            <div className="metricValue">{insights.length}</div>
            <div className="metricLabel">Analysed</div>
          </div>
          <div className="metric">
            <div className={`metricValue ${declining ? "bad" : ""}`}>{declining}</div>
            <div className="metricLabel">Declining</div>
          </div>
          <div className="metric">
            <div className="metricValue good">{ready}</div>
            <div className="metricLabel">Promotion-ready</div>
          </div>
        </div>

        <div className="row" style={{ gap: 12, marginTop: 20, flexWrap: "wrap" }}>
          <div className="input" style={{ minWidth: 200 }}>
            <label htmlFor="trajectory">Trajectory</label>
            <select
              id="trajectory"
              value={trajectory}
              onChange={(e) => setTrajectory(e.target.value)}
            >
              <option value="">All</option>
              <option value="improving">Improving</option>
              <option value="steady">Steady</option>
              <option value="declining">Declining</option>
            </select>
          </div>
          <div className="input" style={{ minWidth: 200 }}>
            <label htmlFor="readiness">Promotion readiness</label>
            <select id="readiness" value={readiness} onChange={(e) => setReadiness(e.target.value)}>
              <option value="">All</option>
              <option value="ready">Ready</option>
              <option value="developing">Developing</option>
              <option value="not_yet">Not yet</option>
            </select>
          </div>
        </div>

        <div className="stack" style={{ marginTop: 20 }}>
          {insights.length === 0 && !loading ? (
            <p className="muted">No performance data. Run the seed script to load the demo org.</p>
          ) : (
            insights.map((insight) => (
              <InsightRow key={insight.employee_id ?? insight.full_name} insight={insight} />
            ))
          )}
        </div>
      </div>
    </div>
  );
}
