import api from "./client";

export interface LiveInterviewStartPayload {
  resume_text: string;
  target_role: string;
  difficulty?: "easy" | "medium" | "hard";
  personality_mode?: "strict" | "friendly" | "stress";
  max_questions?: number;
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

export async function endLiveInterview(id: number) {
  const res = await api.post(`/interviews/live/${id}/end`);
  return res.data;
}

