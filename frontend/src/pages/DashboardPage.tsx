import { Link } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";

export function DashboardPage() {
  const { user, logout } = useAuth();

  return (
    <div className="layout">
      <div className="card" style={{ maxWidth: 720 }}>
        <div className="row space-between">
          <div>
            <h1>Dashboard</h1>
            <p>Welcome back, {user?.full_name || user?.email}</p>
          </div>
          <button className="btn secondary" onClick={logout}>
            Log out
          </button>
        </div>

        <div className="stack" style={{ marginTop: 24 }}>
          <section>
            <h2>HR intelligence</h2>
            <p>
              Rank candidates against a requisition using parsed resumes, stated job
              requirements and interview scores, with the reasoning behind every
              recommendation.
            </p>
            <Link to="/hr">
              <button className="btn">Open HR dashboard</button>
            </Link>
          </section>

          <section>
            <h2>Recruitment pipeline</h2>
            <p>Create requisitions, add candidates and upload resumes for parsing.</p>
            <Link to="/pipeline">
              <button className="btn secondary">Manage pipeline</button>
            </Link>
          </section>

          <section>
            <h2>Interviews</h2>
            <p>
              Run an AI interview. Launch it from the pipeline to bind the score to a
              candidate, or start a standalone practice session here.
            </p>
            <Link to="/interview">
              <button className="btn secondary">Start interview</button>
            </Link>
          </section>
        </div>
      </div>
    </div>
  );
}
