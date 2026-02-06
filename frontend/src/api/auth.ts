import api from "./client";

export interface AuthResponse {
  access_token: string;
  token_type: string;
}

export async function login(email: string, password: string): Promise<AuthResponse> {
  const res = await api.post<AuthResponse>("/auth/login", { email, password });
  return res.data;
}

export interface SignupPayload {
  email: string;
  full_name?: string;
  password: string;
}

export async function signup(payload: SignupPayload) {
  const res = await api.post("/auth/signup", payload);
  return res.data;
}

export interface MeResponse {
  id: number;
  email: string;
  full_name?: string;
  is_active: boolean;
  is_superuser: boolean;
}

export async function fetchMe(): Promise<MeResponse> {
  const res = await api.get<MeResponse>("/auth/me");
  return res.data;
}

