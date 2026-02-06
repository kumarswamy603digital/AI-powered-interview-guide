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
            <h2>Live interviews</h2>
            <p>Start an AI-powered mock interview tailored to your target role.</p>
            <Link to="/interview">
              <button className="btn">Start interview</button>
            </Link>
          </section>

          <section>
            <h2>Analytics & reports</h2>
            <p>Coming next: charts for history, skill progress, and performance trends.</p>
          </section>
        </div>
      </div>
    </div>
  );
}

