import { FormEvent, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";

export function LoginPage() {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const navigate = useNavigate();
  const location = useLocation() as any;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await login(email, password);
      const redirectTo = location.state?.from?.pathname ?? "/dashboard";
      navigate(redirectTo, { replace: true });
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? "Login failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="layout">
      <div className="card">
        <h1>Sign in</h1>
        <p>Access your AI-powered interview dashboard.</p>
        <form onSubmit={handleSubmit}>
          <div className="input">
            <label htmlFor="email">Email</label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>
          <div className="input">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>
          {error && <div style={{ color: "#f97373", fontSize: 14 }}>{error}</div>}
          <button className="btn" type="submit" disabled={submitting}>
            {submitting ? "Signing in..." : "Sign in"}
          </button>
        </form>
        <p style={{ marginTop: 16, fontSize: 14 }}>
          New here? <Link to="/signup">Create an account</Link>
        </p>
      </div>
    </div>
  );
}

