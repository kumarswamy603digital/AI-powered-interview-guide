import { Link } from "react-router-dom";
import { HrNav } from "../components/HrNav";

const CAPABILITIES: { to: string; title: string; description: string }[] = [
  {
    to: "/hr",
    title: "HR decision dashboard",
    description:
      "Recruitment, attendance, performance, attrition and skills combined, with insights that need more than one source."
  },
  {
    to: "/recruitment",
    title: "Recruitment intelligence",
    description: "Rank candidates against a requisition from resumes, requirements and interview scores."
  },
  {
    to: "/people",
    title: "People directory and 360 view",
    description: "Every employee with skills, risk, performance, attendance and onboarding in one profile."
  },
  {
    to: "/attrition",
    title: "Attrition prediction",
    description: "Flight risk from nine signals, each mapped to a retention action and an expected impact."
  },
  {
    to: "/performance",
    title: "Performance intelligence",
    description: "Strengths and development areas from goals, feedback themes and review trajectory."
  },
  {
    to: "/skills",
    title: "Workforce skill graph",
    description: "Supply against current and future demand, single points of failure, reskilling candidates."
  },
  {
    to: "/onboarding",
    title: "Adaptive onboarding",
    description: "Personalised 30/60/90 journeys driven by role, department, work mode and skill gaps."
  },
  {
    to: "/policies",
    title: "Policy reasoning",
    description: "Source-backed policy answers with citations, and an explicit refusal when uncovered."
  }
];

export function DashboardPage() {
  return (
    <div className="layout wide">
      <div className="card" style={{ maxWidth: 1100 }}>
        <HrNav
          title="AI workforce intelligence"
          subtitle="Eight capabilities over one shared workforce data model."
        />

        <div className="insightGrid" style={{ marginTop: 24 }}>
          {CAPABILITIES.map((capability) => (
            <Link key={capability.to} to={capability.to} className="capabilityCard">
              <strong>{capability.title}</strong>
              <p className="muted" style={{ margin: "6px 0 0", lineHeight: 1.5 }}>
                {capability.description}
              </p>
            </Link>
          ))}
        </div>

        <section style={{ marginTop: 28 }}>
          <h2>Interview agent</h2>
          <p className="muted">
            Run an AI interview. Launch it from the recruitment pipeline to bind the score to a
            candidate so it feeds ranking, or start a standalone session.
          </p>
          <Link to="/interview">
            <button className="btn secondary" type="button">
              Start interview
            </button>
          </Link>
        </section>
      </div>
    </div>
  );
}
