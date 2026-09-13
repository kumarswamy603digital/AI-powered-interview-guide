import { FormEvent, useEffect, useState } from "react";
import { HrNav } from "../components/HrNav";
import {
  Employee,
  Policy,
  PolicyAnswer,
  askPolicy,
  listEmployees,
  listPolicies
} from "../api/workforce";

const EXAMPLES = [
  "How many annual leave days can I carry forward?",
  "How late can I submit an expense claim?",
  "Am I eligible to work remotely?",
  "What is the promotion eligibility rule?",
  "How much is the referral bonus?"
];

export function PolicyPage() {
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [question, setQuestion] = useState("");
  const [employeeId, setEmployeeId] = useState<string>("");
  const [answer, setAnswer] = useState<PolicyAnswer | null>(null);
  const [history, setHistory] = useState<PolicyAnswer[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([listPolicies(), listEmployees()])
      .then(([policyData, employeeData]) => {
        setPolicies(policyData);
        setEmployees(employeeData);
      })
      .catch((err) => {
        setError("Could not load the policy library. Is the backend seeded?");
        // eslint-disable-next-line no-console
        console.error(err);
      });
  }, []);

  async function ask(text: string) {
    if (!text.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const result = await askPolicy({
        question: text,
        employee_id: employeeId ? Number(employeeId) : undefined
      });
      setAnswer(result);
      setHistory((prev) => [result, ...prev].slice(0, 5));
    } catch (err) {
      setError("The question could not be answered right now.");
      // eslint-disable-next-line no-console
      console.error(err);
    } finally {
      setBusy(false);
    }
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    await ask(question);
  }

  return (
    <div className="layout wide">
      <div className="card" style={{ maxWidth: 1100 }}>
        <HrNav
          title="HR policy reasoning"
          subtitle="Answers backed by the exact policy section they came from — and an explicit refusal when no policy covers the question."
        />

        {error && <div className="notice bad">{error}</div>}

        <form onSubmit={handleSubmit} className="stack" style={{ marginTop: 20 }}>
          <div className="input">
            <label htmlFor="question">Question</label>
            <input
              id="question"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="e.g. How many leave days can I carry forward?"
              required
            />
          </div>
          <div className="row" style={{ gap: 12, flexWrap: "wrap" }}>
            <div className="input" style={{ minWidth: 260 }}>
              <label htmlFor="employee">Ask on behalf of (optional)</label>
              <select
                id="employee"
                value={employeeId}
                onChange={(e) => setEmployeeId(e.target.value)}
              >
                <option value="">No specific employee</option>
                {employees.map((employee) => (
                  <option key={employee.id} value={employee.id}>
                    {employee.full_name} — {employee.employment_type ?? "?"},{" "}
                    {employee.location ?? "?"}
                  </option>
                ))}
              </select>
            </div>
            <button className="btn" type="submit" disabled={busy} style={{ alignSelf: "flex-end" }}>
              {busy ? "Searching policies…" : "Ask"}
            </button>
          </div>
        </form>

        <div className="row" style={{ gap: 8, marginTop: 12, flexWrap: "wrap" }}>
          {EXAMPLES.map((example) => (
            <button
              key={example}
              type="button"
              className="chip clickable"
              onClick={() => {
                setQuestion(example);
                void ask(example);
              }}
            >
              {example}
            </button>
          ))}
        </div>

        {answer && (
          <section style={{ marginTop: 28 }}>
            <div className="row" style={{ gap: 10, flexWrap: "wrap" }}>
              <h2 style={{ margin: 0 }}>{answer.answered ? "Answer" : "Not covered by policy"}</h2>
              <span className={`badge ${answer.answered ? "covered" : "reject"}`}>
                {answer.answered ? `${answer.confidence} confidence` : "escalate to HR"}
              </span>
              <span className="chip">
                {answer.generated_by === "gemini"
                  ? "synthesised by Gemini"
                  : answer.generated_by === "extractive"
                    ? "extracted from policy text"
                    : "refused"}
              </span>
            </div>

            <div className={`notice ${answer.answered ? "" : "warn"}`} style={{ whiteSpace: "pre-wrap" }}>
              {answer.answer}
            </div>

            {answer.caveats.length > 0 && (
              <div className="notice warn">
                {answer.caveats.map((caveat, index) => (
                  <div key={index}>{caveat}</div>
                ))}
              </div>
            )}

            {answer.citations.length > 0 && (
              <>
                <div className="reasoningTitle">Sources</div>
                <div className="stack">
                  {answer.citations.map((citation) => (
                    <div key={citation.marker} className="citation">
                      <div className="row space-between" style={{ gap: 12 }}>
                        <strong>
                          {citation.marker} {citation.policy_title}
                          {citation.section ? ` — ${citation.section}` : ""}
                        </strong>
                        <span className="muted">
                          {citation.version ? `v${citation.version}` : ""}
                          {citation.effective_date ? ` · effective ${citation.effective_date}` : ""}
                        </span>
                      </div>
                      <p className="muted" style={{ margin: "6px 0 0", lineHeight: 1.5 }}>
                        {citation.excerpt}
                      </p>
                    </div>
                  ))}
                </div>
              </>
            )}

            {answer.follow_up_suggestions.length > 0 && (
              <p className="muted" style={{ marginTop: 12 }}>
                Try instead: {answer.follow_up_suggestions.join(" · ")}
              </p>
            )}
          </section>
        )}

        <div className="twoCol" style={{ marginTop: 32 }}>
          <section>
            <h2>Policy library ({policies.length})</h2>
            {policies.length === 0 ? (
              <p className="muted">No policies loaded. Run the seed script to load six sample policies.</p>
            ) : (
              <table className="dataTable">
                <thead>
                  <tr>
                    <th>Policy</th>
                    <th>Applies to</th>
                    <th>Sections</th>
                  </tr>
                </thead>
                <tbody>
                  {policies.map((policy) => (
                    <tr key={policy.id}>
                      <td>
                        <strong>{policy.title}</strong>
                        <div className="muted">
                          {policy.category} {policy.version ? `· v${policy.version}` : ""}
                        </div>
                      </td>
                      <td className="muted">{policy.applies_to ?? "all"}</td>
                      <td>{policy.section_count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>

          {history.length > 1 && (
            <section>
              <h2>Recent questions</h2>
              <ul className="insights">
                {history.slice(1).map((item, index) => (
                  <li key={index}>
                    {item.question} —{" "}
                    <span className="muted">
                      {item.answered ? `${item.citations.length} source(s)` : "not covered"}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}
