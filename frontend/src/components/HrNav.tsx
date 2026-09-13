import { Link, useLocation } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";

const LINKS: { to: string; label: string }[] = [
  { to: "/hr", label: "Decisions" },
  { to: "/recruitment", label: "Recruitment" },
  { to: "/pipeline", label: "Pipeline" },
  { to: "/people", label: "People" },
  { to: "/attrition", label: "Attrition" },
  { to: "/performance", label: "Performance" },
  { to: "/skills", label: "Skill graph" },
  { to: "/onboarding", label: "Onboarding" },
  { to: "/policies", label: "Policy Q&A" }
];

export function HrNav({ title, subtitle }: { title: string; subtitle?: string }) {
  const { user, logout } = useAuth();
  const location = useLocation();

  return (
    <div className="stack" style={{ gap: 16 }}>
      <div className="row space-between" style={{ alignItems: "flex-start", gap: 16 }}>
        <div>
          <h1 style={{ marginBottom: 4 }}>{title}</h1>
          {subtitle && (
            <p className="muted" style={{ margin: 0 }}>
              {subtitle}
            </p>
          )}
        </div>
        <div className="row" style={{ gap: 8 }}>
          <span className="chip">{user?.full_name || user?.email}</span>
          <button className="btn secondary" type="button" onClick={logout}>
            Log out
          </button>
        </div>
      </div>

      <nav className="hrNav">
        {LINKS.map((link) => {
          const active = location.pathname === link.to;
          return (
            <Link key={link.to} to={link.to} className={`navLink ${active ? "active" : ""}`}>
              {link.label}
            </Link>
          );
        })}
      </nav>
    </div>
  );
}
