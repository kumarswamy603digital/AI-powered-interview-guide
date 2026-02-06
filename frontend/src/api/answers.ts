import api from "./client";

export interface AnswerEvaluationResponse {
  relevance: number;
  depth: number;
  clarity: number;
  confidence: number;
  overall_score: number;
  feedback?: string | null;
}

export async function evaluateAnswer(params: {
  question: string;
  answer: string;
  target_role?: string;
}): Promise<AnswerEvaluationResponse> {
  const res = await api.post<AnswerEvaluationResponse>("/answers/evaluate", params);
  return res.data;
}

