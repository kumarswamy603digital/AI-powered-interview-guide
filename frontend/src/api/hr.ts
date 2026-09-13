import api from "./client";

// --------------------------------------------------------------------------
// Job requisitions
// --------------------------------------------------------------------------
export interface JobRequisition {
  id: number;
  title: string;
  department?: string | null;
  seniority?: string | null;
  location?: string | null;
  employment_type?: string | null;
  description?: string | null;
  required_skills: string[];
  preferred_skills: string[];
  min_years_experience?: number | null;
  headcount: number;
  status: "open" | "on_hold" | "closed";
  candidate_count: number;
  created_at: string;
  updated_at: string;
}

export interface JobRequisitionPayload {
  title: string;
  department?: string;
  seniority?: string;
  description?: string;
  required_skills: string[];
  preferred_skills?: string[];
  min_years_experience?: number;
  headcount?: number;
}

export async function listJobs(status?: JobRequisition["status"]): Promise<JobRequisition[]> {
  const res = await api.get<JobRequisition[]>("/jobs", { params: status ? { status } : {} });
  return res.data;
}

export async function createJob(payload: JobRequisitionPayload): Promise<JobRequisition> {
  const res = await api.post<JobRequisition>("/jobs", payload);
  return res.data;
}

export async function getJob(jobId: number): Promise<JobRequisition> {
  const res = await api.get<JobRequisition>(`/jobs/${jobId}`);
  return res.data;
}

// --------------------------------------------------------------------------
// Candidates
// --------------------------------------------------------------------------
export type CandidateStage =
  | "applied"
  | "screened"
  | "interviewed"
  | "recommended"
  | "rejected"
  | "hired";

export interface Candidate {
  id: number;
  full_name: string;
  email?: string | null;
  current_title?: string | null;
  years_experience?: number | null;
  source?: string | null;
  job_requisition_id?: number | null;
  stage: CandidateStage;
  notes?: string | null;
  has_resume_text: boolean;
  extracted_skills: string[];
  interviews_completed: number;
  latest_interview_score?: number | null;
  created_at: string;
  updated_at: string;
}

export interface CandidatePayload {
  full_name: string;
  email?: string;
  current_title?: string;
  years_experience?: number;
  source?: string;
  job_requisition_id?: number;
}

export async function listCandidates(jobRequisitionId?: number): Promise<Candidate[]> {
  const res = await api.get<Candidate[]>("/candidates", {
    params: jobRequisitionId ? { job_requisition_id: jobRequisitionId } : {}
  });
  return res.data;
}

export async function createCandidate(payload: CandidatePayload): Promise<Candidate> {
  const res = await api.post<Candidate>("/candidates", payload);
  return res.data;
}

export async function updateCandidateStage(
  candidateId: number,
  stage: CandidateStage
): Promise<Candidate> {
  const res = await api.patch<Candidate>(`/candidates/${candidateId}`, { stage });
  return res.data;
}

// --------------------------------------------------------------------------
// Resume upload (multipart)
// --------------------------------------------------------------------------
export interface ResumeUploadResult {
  id: number;
  candidate_id?: number | null;
  original_filename: string;
  extraction_status?: string | null;
  extraction_detail?: string | null;
  extracted_skills: string[];
  extracted_characters: number;
}

export async function uploadResume(
  file: File,
  candidateId?: number
): Promise<ResumeUploadResult> {
  const form = new FormData();
  form.append("file", file);
  if (candidateId !== undefined) {
    form.append("candidate_id", String(candidateId));
  }
  const res = await api.post<ResumeUploadResult>("/resumes/upload", form);
  return res.data;
}

export interface ResumeText {
  id: number;
  candidate_id?: number | null;
  extraction_status?: string | null;
  extracted_skills: string[];
  extracted_text: string;
}

export async function getLatestCandidateResume(candidateId: number): Promise<ResumeText> {
  const res = await api.get<ResumeText>(`/resumes/candidates/${candidateId}/latest`);
  return res.data;
}

// --------------------------------------------------------------------------
// Ranking
// --------------------------------------------------------------------------
export type Recommendation =
  | "recommend_hire"
  | "advance_to_interview"
  | "further_assessment"
  | "reject";

export interface ScoreComponent {
  name: string;
  score: number;
  weight: number;
  detail: string;
}

export interface CandidateRanking {
  candidate_id: number | null;
  full_name: string;
  stage: string;
  final_score: number;
  skill_match_score: number;
  experience_match_score?: number | null;
  interview_score?: number | null;
  preferred_skill_score?: number | null;
  matched_skills: string[];
  missing_skills: string[];
  matched_preferred_skills: string[];
  additional_skills: string[];
  recommendation: Recommendation;
  confidence: "high" | "medium" | "low";
  reasoning: string[];
  flags: string[];
  data_sources: string[];
  components: ScoreComponent[];
  interview_session_id?: number | null;
}

export interface SkillGap {
  skill: string;
  candidates_missing: number;
}

export interface RankResponse {
  job_requisition_id: number;
  job_title: string;
  required_skills: string[];
  candidates_evaluated: number;
  rankings: CandidateRanking[];
  skill_gaps: SkillGap[];
  warnings: string[];
}

export async function rankCandidates(
  jobRequisitionId: number,
  options?: { includeUnassigned?: boolean; limit?: number }
): Promise<RankResponse> {
  const res = await api.post<RankResponse>("/candidates/rank", {
    job_requisition_id: jobRequisitionId,
    include_unassigned: options?.includeUnassigned ?? false,
    limit: options?.limit ?? 50
  });
  return res.data;
}

// --------------------------------------------------------------------------
// HR dashboard
// --------------------------------------------------------------------------
export interface PipelineCounts {
  applied: number;
  screened: number;
  interviewed: number;
  recommended: number;
  rejected: number;
  hired: number;
}

export interface HrDashboard {
  open_jobs: number;
  total_candidates: number;
  interviews_completed: number;
  candidates_awaiting_interview: number;
  candidates_missing_resume_text: number;
  pipeline: PipelineCounts;
  top_skill_gaps: SkillGap[];
  recommendation_counts: Record<string, number>;
  insights: string[];
}

export async function getHrDashboard(): Promise<HrDashboard> {
  const res = await api.get<HrDashboard>("/hr/dashboard");
  return res.data;
}

// --------------------------------------------------------------------------
// Display helpers
// --------------------------------------------------------------------------
export const RECOMMENDATION_LABELS: Record<Recommendation, string> = {
  recommend_hire: "Recommend hire",
  advance_to_interview: "Advance to interview",
  further_assessment: "Further assessment",
  reject: "Not a fit"
};

export const FLAG_LABELS: Record<string, string> = {
  resume_interview_mismatch: "Resume/interview conflict",
  outperformed_resume: "Outperformed resume",
  partial_skill_gap: "Partial skill gap",
  no_resume_text: "No resume text"
};
