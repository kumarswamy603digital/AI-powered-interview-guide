import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { HrNav } from "../components/HrNav";
import {
  AttritionOverview,
  Employee,
  getAttritionOverview,
  listDepartments,
  listEmployees
} from "../api/workforce";

export function PeoplePage() {
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [departments, setDepartments] = useState<string[]>([]);
  const [risk, setRisk] = useState<AttritionOverview | null>(null);
  const [department, setDepartment] = useState<string>("");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([
      listEmployees(department || undefined),
      listDepartments(),
      getAttritionOverview(department ? { department } : {})
    ])
      .then(([employeeData, departmentData, riskData]) => {
        if (cancelled) return;
        setEmployees(employeeData);
        setDepartments(departmentData);
        setRisk(riskData);
      })
      .catch((err) => {
        if (!cancelled) setError("Could not load the employee directory. Is the backend seeded?");
        // eslint-disable-next-line no-console
        console.error(err);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [department]);

  const riskById = useMemo(() => {
    const map = new Map<number, { score: number; band: string }>();
    for (const assessment of risk?.assessments ?? []) {
      if (assessment.employee_id) {
        map.set(assessment.employee_id, {
          score: assessment.risk_score,
          band: assessment.risk_band
        });
      }
    }
    return map;
  }, [risk]);

  const visible = employees.filter((employee) => {
    if (!search.trim()) return true;
    const needle = search.toLowerCase();
    return (
      employee.full_name.toLowerCase().includes(needle) ||
      employee.job_title.toLowerCase().includes(needle) ||
      employee.skills.some((skill) => skill.toLowerCase().includes(needle))
    );
  });

  return (
    <div className="layout wide">
      <div className="card" style={{ maxWidth: 1200 }}>
        <HrNav
          title="People directory"
          subtitle="Every employee, with their skills and current flight risk. Open anyone for a full 360 view."
        />

        {error && <div className="notice bad">{error}</div>}
        {loading && <p className="muted">Loading…</p>}

        <div className="row" style={{ gap: 12, marginTop: 20, flexWrap: "wrap" }}>
          <div className="input" style={{ minWidth: 220 }}>
            <label htmlFor="department">Department</label>
            <select
              id="department"
              value={department}
              onChange={(e) => setDepartment(e.target.value)}
            >
              <option value="">All departments</option>
              {departments.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </div>
          <div className="input" style={{ minWidth: 260, flex: 1 }}>
            <label htmlFor="search">Search name, title or skill</label>
            <input
              id="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="e.g. Kubernetes"
            />
          </div>
        </div>

        <table className="dataTable" style={{ marginTop: 20 }}>
          <thead>
            <tr>
              <th>Employee</th>
              <th>Department</th>
              <th>Tenure</th>
              <th>Flight risk</th>
              <th>Skills</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {visible.map((employee) => {
              const employeeRisk = riskById.get(employee.id);
              return (
                <tr key={employee.id}>
                  <td>
                    <Link to={`/people/${employee.id}`}>
                      <strong>{employee.full_name}</strong>
                    </Link>
                    <div className="muted">{employee.job_title}</div>
                  </td>
                  <td className="muted">
                    {employee.department}
                    {employee.manager_name && <div>reports to {employee.manager_name}</div>}
                  </td>
                  <td className="muted">
                    {employee.tenure_years ? `${employee.tenure_years.toFixed(1)}y` : "—"}
                  </td>
                  <td>
                    {employeeRisk ? (
                      <span className={`badge risk-${employeeRisk.band}`}>
                        {Math.round(employeeRisk.score)}
                      </span>
                    ) : (
                      <span className="muted">—</span>
                    )}
                  </td>
                  <td>
                    <div className="row" style={{ gap: 4, flexWrap: "wrap" }}>
                      {employee.skills.slice(0, 5).map((skill) => (
                        <span key={skill} className="pill">
                          {skill}
                        </span>
                      ))}
                      {employee.skills.length > 5 && (
                        <span className="muted">+{employee.skills.length - 5}</span>
                      )}
                    </div>
                  </td>
                  <td>
                    <Link to={`/people/${employee.id}`}>
                      <button className="btn secondary" type="button">
                        360 view
                      </button>
                    </Link>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>

        {visible.length === 0 && !loading && (
          <p className="muted">
            No employees found. Run <code>python -m scripts.seed_demo</code> in the backend to load
            the demo organisation.
          </p>
        )}
      </div>
    </div>
  );
}
