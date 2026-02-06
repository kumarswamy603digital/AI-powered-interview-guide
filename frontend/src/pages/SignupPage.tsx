import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";

export function SignupPage() {
  const { signup } = useAuth();
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const navigate = useNavigate();

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await signup(email, fullName || undefined, password);
      navigate("/dashboard", { replace: true });
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? "Signup failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="layout">
      <div className="card">
        <h1>Create account</h1>
        <p>Start practicing with AI-powered interviews.</p>
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
            <label htmlFor="fullName">Full name (optional)</label>
            <input
              id="fullName"
              type="text"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
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
            {submitting ? "Creating..." : "Create account"}
          </button>
        </form>
        <p style={{ marginTop: 16, fontSize: 14 }}>
          Already have an account? <Link to="/login">Sign in</Link>
        </p>
      </div>
    </div>
  );
}

