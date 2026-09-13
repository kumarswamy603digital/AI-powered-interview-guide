import api from "./client";

export interface LiveInterviewStartPayload {
  resume_text: string;
  target_role: string;
  difficulty?: "easy" | "medium" | "hard";
  personality_mode?: "strict" | "friendly" | "stress";
  max_questions?: number;
  // Bind the session to a tracked candidate so its score feeds ranking.
  candidate_id?: number;
  job_requisition_id?: number;
}

export interface LiveInterviewStartResponse {
  id: number;
  first_question: string;
  question_index: number;
}

export async function startLiveInterview(
  payload: LiveInterviewStartPayload
): Promise<LiveInterviewStartResponse> {
  const res = await api.post<LiveInterviewStartResponse>("/interviews/live/start", payload);
  return res.data;
}

export interface LiveInterviewSubmitResponse {
  id: number;
  next_question: string;
  question_index: number;
  is_follow_up: boolean;
}

export async function submitLiveAnswer(
  id: number,
  answer: string
): Promise<LiveInterviewSubmitResponse> {
  const res = await api.post<LiveInterviewSubmitResponse>(`/interviews/live/${id}/submit`, {
    answer
  });
  return res.data;
}

export interface LiveInterviewEndResponse {
  id: number;
  status: string;
  total_turns: number;
  ended_at?: string | null;
  // Scores are generated and persisted when the interview ends.
  overall_score?: number | null;
  scored: boolean;
}

export async function endLiveInterview(id: number): Promise<LiveInterviewEndResponse> {
  const res = await api.post<LiveInterviewEndResponse>(`/interviews/live/${id}/end`);
  return res.data;
}

