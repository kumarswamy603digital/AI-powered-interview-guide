import api from "./client";

// --------------------------------------------------------------------------
// Employees
// --------------------------------------------------------------------------
export interface Employee {
  id: number;
  full_name: string;
  email?: string | null;
  department: string;
  job_title: string;
  seniority?: string | null;
  location?: string | null;
  work_mode?: string | null;
  employment_type?: string | null;
  manager_id?: number | null;
  manager_name?: string | null;
  hire_date: string;
  last_promotion_date?: string | null;
  compa_ratio?: number | null;
  engagement_score?: number | null;
  status: string;
  tenure_years?: number | null;
  skills: string[];
  direct_report_count: number;
}

export async function listEmployees(department?: string): Promise<Employee[]> {
  const res = await api.get<Employee[]>("/employees", {
    params: department ? { department } : {}
  });
  return res.data;
}

export async function listDepartments(): Promise<string[]> {
  const res = await api.get<string[]>("/employees/departments");
  return res.data;
}

// --------------------------------------------------------------------------
// Attrition
// --------------------------------------------------------------------------
export type RiskBand = "low" | "moderate" | "high" | "critical";

export interface RiskFactor {
  name: string;
  label: string;
  risk: number;
  weight: number;
  contribution: number;
  evidence: string;
}

export interface RetentionAction {
  action: string;
  rationale: string;
  expected_risk_reduction: number;
  priority: "high" | "medium" | "low";
  owner: string;
}

export interface AttritionAssessment {
  employee_id?: number | null;
  full_name: string;
  department: string;
  job_title: string;
  risk_score: number;
  risk_band: RiskBand;
  confidence: "high" | "medium" | "low";
  factors: RiskFactor[];
  protective_factors: RiskFactor[];
  recommended_actions: RetentionAction[];
  signals_available: number;
  signals_total: number;
  summary: string;
}

export interface AttritionOverview {
  employees_assessed: number;
  average_risk: number;
  band_distribution: Record<string, number>;
  high_risk_count: number;
  by_department: Array<Record<string, unknown>>;
  top_drivers: Array<Record<string, unknown>>;
  assessments: AttritionAssessment[];
}

export async function getAttritionOverview(params?: {
  department?: string;
  band?: string;
}): Promise<AttritionOverview> {
  const res = await api.get<AttritionOverview>("/attrition", { params: params ?? {} });
  return res.data;
}

export interface AttritionModelInfo {
  approach: string;
  signals: Array<{ name: string; label: string; weight: number }>;
  bands: Record<string, string>;
  notes: string[];
}

export async function getAttritionModel(): Promise<AttritionModelInfo> {
  const res = await api.get<AttritionModelInfo>("/attrition/model");
  return res.data;
}

// --------------------------------------------------------------------------
// Performance
// --------------------------------------------------------------------------
export interface ThemeInsight {
  theme: string;
  sentiment: number;
  mentions: number;
  sources: string[];
  evidence: string[];
}

export interface GoalSummary {
  total: number;
  achieved: number;
  on_track: number;
  at_risk: number;
  missed: number;
  not_started: number;
  weighted_attainment: number;
}

export interface PerformanceInsight {
  employee_id?: number | null;
  full_name: string;
  department: string;
  job_title: string;
  overall_score: number;
  latest_rating?: number | null;
  rating_trajectory: "improving" | "steady" | "declining" | "unknown";
  rating_delta?: number | null;
  goal_summary: GoalSummary;
  calibration?: string | null;
  calibration_delta?: number | null;
  strengths: ThemeInsight[];
  improvement_areas: ThemeInsight[];
  feedback_sentiment?: number | null;
  promotion_readiness: "ready" | "developing" | "not_yet" | "unknown";
  recommended_actions: Array<{
    action: string;
    rationale: string;
    owner: string;
    priority: "high" | "medium" | "low";
  }>;
  summary: string;
  data_sources: string[];
}

export async function listPerformanceInsights(params?: {
  department?: string;
  trajectory?: string;
  promotion_readiness?: string;
}): Promise<PerformanceInsight[]> {
  const res = await api.get<PerformanceInsight[]>("/performance/insights", {
    params: params ?? {}
  });
  return res.data;
}

// --------------------------------------------------------------------------
// Skill graph
// --------------------------------------------------------------------------
export interface ReskillCandidate {
  employee_id?: number | null;
  full_name: string;
  department: string;
  affinity: number;
  adjacent_skills_held: string[];
  reason: string;
}

export interface SkillNode {
  skill: string;
  category?: string | null;
  total_holders: number;
  qualified_holders: number;
  average_proficiency?: number | null;
  verified_holders: number;
  demand_current: number;
  demand_future: number;
  importance?: string | null;
  coverage_current?: number | null;
  coverage_future?: number | null;
  gap_current: number;
  gap_future: number;
  status: string;
  single_point_of_failure: boolean;
  hot_market_skill: boolean;
  holders: string[];
  departments: string[];
  demand_departments?: string[];
  reskilling_candidates: ReskillCandidate[];
  recommended_action?: string | null;
  rationale?: string | null;
}

export interface SkillGraph {
  nodes: SkillNode[];
  edges: Array<Record<string, unknown>>;
  summary: Record<string, any>;
}

export async function getSkillGraph(): Promise<SkillGraph> {
  const res = await api.get<SkillGraph>("/skills/graph");
  return res.data;
}

export interface SkillRequirement {
  id: number;
  skill: string;
  department?: string | null;
  role?: string | null;
  importance: string;
  horizon: string;
  required_headcount: number;
  required_proficiency: number;
  target_date?: string | null;
  rationale?: string | null;
}

export async function listRequirements(): Promise<SkillRequirement[]> {
  const res = await api.get<SkillRequirement[]>("/skills/requirements");
  return res.data;
}

export async function createRequirement(payload: {
  skill: string;
  department?: string;
  importance?: string;
  horizon?: string;
  required_headcount?: number;
  required_proficiency?: number;
  rationale?: string;
}): Promise<SkillRequirement> {
  const res = await api.post<SkillRequirement>("/skills/requirements", payload);
  return res.data;
}

// --------------------------------------------------------------------------
// Onboarding
// --------------------------------------------------------------------------
export interface OnboardingTask {
  id?: number | null;
  title: string;
  description?: string | null;
  phase: string;
  category: string;
  day_offset: number;
  owner?: string | null;
  mandatory: boolean;
  status: string;
  rationale?: string | null;
  due_date?: string | null;
}

export interface OnboardingPhase {
  phase: string;
  label: string;
  day_from: number;
  day_to: number;
  tasks: OnboardingTask[];
}

export interface OnboardingJourney {
  employee_id?: number | null;
  full_name: string;
  role: string;
  department: string;
  seniority?: string | null;
  work_mode?: string | null;
  buddy_name?: string | null;
  targeted_skill_gaps: string[];
  personalization_notes: string[];
  phases: OnboardingPhase[];
  tasks: OnboardingTask[];
  mandatory_count: number;
  summary: string;
}

export async function generateOnboarding(payload: {
  employee_id: number;
  persist?: boolean;
}): Promise<OnboardingJourney> {
  const res = await api.post<OnboardingJourney>("/onboarding/generate", {
    employee_id: payload.employee_id,
    persist: payload.persist ?? false
  });
  return res.data;
}

export interface OnboardingPlan {
  id: number;
  employee_id: number;
  employee_name?: string | null;
  role?: string | null;
  buddy_name?: string | null;
  start_date?: string | null;
  status: string;
  summary?: string | null;
  targeted_skill_gaps: string[];
  tasks: OnboardingTask[];
  progress: {
    total_tasks: number;
    completed_tasks: number;
    completion_percent: number;
    mandatory_total: number;
    mandatory_completed: number;
    mandatory_outstanding: string[];
    by_phase: Array<{ phase: string; label: string; total: number; completed: number; completion_percent: number }>;
  };
}

export async function listOnboardingPlans(): Promise<OnboardingPlan[]> {
  const res = await api.get<OnboardingPlan[]>("/onboarding/plans");
  return res.data;
}

export async function updateOnboardingTask(
  taskId: number,
  status: "pending" | "in_progress" | "done" | "skipped"
): Promise<OnboardingTask> {
  const res = await api.patch<OnboardingTask>(`/onboarding/tasks/${taskId}`, { status });
  return res.data;
}

// --------------------------------------------------------------------------
// Policies
// --------------------------------------------------------------------------
export interface Policy {
  id: number;
  title: string;
  category?: string | null;
  version?: string | null;
  effective_date?: string | null;
  applies_to?: string | null;
  section_count: number;
}

export async function listPolicies(): Promise<Policy[]> {
  const res = await api.get<Policy[]>("/policies");
  return res.data;
}

export interface Citation {
  marker: string;
  policy_id?: number | null;
  policy_title: string;
  section?: string | null;
  version?: string | null;
  effective_date?: string | null;
  relevance: number;
  excerpt: string;
}

export interface PolicyAnswer {
  question: string;
  answered: boolean;
  answer: string;
  citations: Citation[];
  confidence: "high" | "medium" | "low";
  matched_terms: string[];
  unmatched_terms: string[];
  related_policies: string[];
  caveats: string[];
  generated_by: "gemini" | "extractive" | "refusal";
  follow_up_suggestions: string[];
}

export async function askPolicy(payload: {
  question: string;
  employee_id?: number;
}): Promise<PolicyAnswer> {
  const res = await api.post<PolicyAnswer>("/policies/ask", payload);
  return res.data;
}

// --------------------------------------------------------------------------
// Employee 360
// --------------------------------------------------------------------------
export interface Employee360 {
  employee: Employee;
  skills: Array<{ id: number; skill: string; proficiency: number; source: string; verified: boolean }>;
  attendance: {
    employee_id: number;
    window_days: number;
    unplanned_absence_rate?: number | null;
    late_arrival_rate?: number | null;
    average_weekly_overtime?: number | null;
    note: string;
  };
  performance: PerformanceInsight;
  attrition: AttritionAssessment;
  reviews: Array<{
    id: number;
    period: string;
    rating: number;
    strengths: string[];
    improvements: string[];
    comments?: string | null;
    promotion_ready?: string | null;
  }>;
  goals: Array<{ id: number; title: string; status: string; progress: number; weight: number }>;
  feedback: Array<{
    id: number;
    source: string;
    content: string;
    sentiment?: number | null;
    inferred_sentiment?: number | null;
  }>;
  onboarding_progress?: Record<string, any> | null;
  skill_gaps_for_role: string[];
}

export async function getEmployee360(employeeId: number): Promise<Employee360> {
  const res = await api.get<Employee360>(`/employees/${employeeId}/360`);
  return res.data;
}

// --------------------------------------------------------------------------
// Decision dashboard
// --------------------------------------------------------------------------
export interface CrossSourceInsight {
  title: string;
  severity: "critical" | "warning" | "opportunity" | "info";
  detail: string;
  recommended_action: string;
  sources: string[];
  entities: string[];
}

export interface DecisionDashboard {
  headline: Record<string, any>;
  recruitment: Record<string, any>;
  workforce_risk: Record<string, any>;
  performance: Record<string, any>;
  attendance: Record<string, any>;
  skills: Record<string, any>;
  onboarding: Record<string, any>;
  insights: CrossSourceInsight[];
  data_sources: string[];
}

export async function getDecisionDashboard(): Promise<DecisionDashboard> {
  const res = await api.get<DecisionDashboard>("/hr/decision-dashboard");
  return res.data;
}

// --------------------------------------------------------------------------
// Display helpers
// --------------------------------------------------------------------------
export const RISK_BAND_LABELS: Record<RiskBand, string> = {
  low: "Low risk",
  moderate: "Moderate",
  high: "High risk",
  critical: "Critical"
};

export const SKILL_STATUS_LABELS: Record<string, string> = {
  surplus: "Surplus",
  covered: "Covered",
  at_risk: "At risk",
  critical_gap: "Critical gap",
  no_demand: "No stated demand"
};

export function formatPercent(value?: number | null): string {
  if (value === null || value === undefined) return "—";
  return `${Math.round(value)}%`;
}
