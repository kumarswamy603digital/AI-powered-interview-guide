import { useEffect, useState } from "react";
import { HrNav } from "../components/HrNav";
import {
  Employee,
  OnboardingJourney,
  OnboardingPlan,
  formatPercent,
  generateOnboarding,
  listEmployees,
  listOnboardingPlans,
  updateOnboardingTask
} from "../api/workforce";

export function OnboardingPage() {
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [plans, setPlans] = useState<OnboardingPlan[]>([]);
  const [selectedId, setSelectedId] = useState<string>("");
  const [journey, setJourney] = useState<OnboardingJourney | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    try {
      const [employeeData, planData] = await Promise.all([listEmployees(), listOnboardingPlans()]);
      setEmployees(employeeData);
      setPlans(planData);
    } catch (err) {
      setError("Could not load onboarding data. Is the backend seeded?");
      // eslint-disable-next-line no-console
      console.error(err);
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function handleGenerate(persist: boolean) {
    if (!selectedId) return;
    setBusy(true);
    setError(null);
    try {
      const result = await generateOnboarding({ employee_id: Number(selectedId), persist });
      setJourney(result);
      if (persist) await refresh();
    } catch (err) {
      setError("Could not generate the onboarding journey.");
      // eslint-disable-next-line no-console
      console.error(err);
    } finally {
      setBusy(false);
    }
  }

  async function toggleTask(taskId: number | null | undefined, done: boolean) {
    if (!taskId) return;
    try {
      await updateOnboardingTask(taskId, done ? "done" : "pending");
      await refresh();
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error(err);
    }
  }

  return (
    <div className="layout wide">
      <div className="card" style={{ maxWidth: 1200 }}>
        <HrNav
          title="Adaptive onboarding"
          subtitle="Journeys built from role, department, seniority, work mode, location and the employee's own skill gaps."
        />

        {error && <div className="notice bad">{error}</div>}

        <section style={{ marginTop: 20 }}>
          <div className="row" style={{ gap: 12, flexWrap: "wrap", alignItems: "flex-end" }}>
            <div className="input" style={{ minWidth: 320 }}>
              <label htmlFor="employee">Employee</label>
              <select
                id="employee"
                value={selectedId}
                onChange={(e) => setSelectedId(e.target.value)}
              >
                <option value="">Select an employee…</option>
                {employees.map((employee) => (
                  <option key={employee.id} value={employee.id}>
                    {employee.full_name} — {employee.job_title} ({employee.department})
                  </option>
                ))}
              </select>
            </div>
            <button
              className="btn"
              type="button"
              disabled={!selectedId || busy}
              onClick={() => void handleGenerate(false)}
            >
              {busy ? "Generating…" : "Preview journey"}
            </button>
            <button
              className="btn secondary"
              type="button"
              disabled={!selectedId || busy}
              onClick={() => void handleGenerate(true)}
            >
              Generate and save
            </button>
          </div>
        </section>

        {journey && (
          <section style={{ marginTop: 28 }}>
            <h2>
              {journey.full_name} — {journey.role}
            </h2>
            <p className="muted">{journey.summary}</p>

            <div className="row" style={{ gap: 8, flexWrap: "wrap", marginTop: 8 }}>
              {journey.department && <span className="chip">{journey.department}</span>}
              {journey.seniority && <span className="chip">{journey.seniority}</span>}
              {journey.work_mode && <span className="chip">{journey.work_mode}</span>}
              {journey.buddy_name && <span className="chip">buddy: {journey.buddy_name}</span>}
              <span className="chip">{journey.mandatory_count} mandatory</span>
            </div>

            {journey.targeted_skill_gaps.length > 0 && (
              <div className="notice">
                <strong>Personalised training added for:</strong>{" "}
                {journey.targeted_skill_gaps.join(", ")} — required for the role but not evidenced in
                this employee's skill profile.
              </div>
            )}

            <div className="reasoningTitle">What was tailored and why</div>
            <ul className="insights">
              {journey.personalization_notes.map((note, index) => (
                <li key={index}>{note}</li>
              ))}
            </ul>

            {journey.phases.map((phase) => (
              <div key={phase.phase} style={{ marginTop: 20 }}>
                <div className="row space-between">
                  <h3 style={{ margin: 0, fontSize: 15 }}>{phase.label}</h3>
                  <span className="muted">
                    day {phase.day_from} to {phase.day_to} · {phase.tasks.length} tasks
                  </span>
                </div>
                <table className="dataTable">
                  <thead>
                    <tr>
                      <th style={{ width: 60 }}>Day</th>
                      <th>Task</th>
                      <th style={{ width: 120 }}>Owner</th>
                      <th>Why this task</th>
                    </tr>
                  </thead>
                  <tbody>
                    {phase.tasks.map((task, index) => (
                      <tr key={`${task.title}-${index}`}>
                        <td className="muted">{task.day_offset}</td>
                        <td>
                          {task.mandatory && <span className="pill missing">required</span>}{" "}
                          {task.title}
                          <div className="muted">{task.category.replace(/_/g, " ")}</div>
                        </td>
                        <td className="muted">{task.owner}</td>
                        <td className="muted">{task.rationale}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
          </section>
        )}

        <section style={{ marginTop: 32 }}>
          <h2>Active plans ({plans.length})</h2>
          {plans.length === 0 ? (
            <p className="muted">No saved plans yet. Generate one above, or run the seed script.</p>
          ) : (
            plans.map((plan) => (
              <div key={plan.id} className="rankRow" style={{ marginTop: 12 }}>
                <div className="row space-between" style={{ flexWrap: "wrap", gap: 12 }}>
                  <div>
                    <strong>{plan.employee_name}</strong>
                    <div className="muted">
                      {plan.role} · started {plan.start_date ?? "—"}
                      {plan.buddy_name ? ` · buddy ${plan.buddy_name}` : ""}
                    </div>
                  </div>
                  <div className="miniScore">
                    <span>Progress</span>
                    <div className="scoreBar">
                      <div
                        className={plan.progress.completion_percent >= 60 ? "good" : "warn"}
                        style={{ width: `${plan.progress.completion_percent}%` }}
                      />
                    </div>
                    <strong>{formatPercent(plan.progress.completion_percent)}</strong>
                  </div>
                </div>

                {plan.progress.mandatory_outstanding.length > 0 && (
                  <div className="notice warn">
                    Outstanding mandatory tasks: {plan.progress.mandatory_outstanding.join(", ")}
                  </div>
                )}

                <div className="row" style={{ gap: 8, marginTop: 10, flexWrap: "wrap" }}>
                  {plan.progress.by_phase.map((phase) => (
                    <span key={phase.phase} className="pill">
                      {phase.label}: {phase.completed}/{phase.total}
                    </span>
                  ))}
                </div>

                <details style={{ marginTop: 10 }}>
                  <summary className="muted" style={{ cursor: "pointer", fontSize: 13 }}>
                    {plan.tasks.length} tasks — click to open
                  </summary>
                  <table className="dataTable" style={{ marginTop: 10 }}>
                    <tbody>
                      {plan.tasks.map((task) => (
                        <tr key={task.id}>
                          <td style={{ width: 40 }}>
                            <input
                              type="checkbox"
                              checked={task.status === "done"}
                              onChange={(e) => void toggleTask(task.id, e.target.checked)}
                            />
                          </td>
                          <td className="muted" style={{ width: 60 }}>
                            {task.due_date ?? `d${task.day_offset}`}
                          </td>
                          <td>
                            {task.mandatory && <span className="pill missing">required</span>}{" "}
                            {task.title}
                          </td>
                          <td className="muted">{task.owner}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </details>
              </div>
            ))
          )}
        </section>
      </div>
    </div>
  );
}
