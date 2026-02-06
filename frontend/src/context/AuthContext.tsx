import { createContext, ReactNode, useEffect, useState } from "react";
import { fetchMe, login as apiLogin, signup as apiSignup, AuthResponse, MeResponse } from "../api/auth";

interface AuthContextValue {
  user: MeResponse | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, fullName: string | undefined, password: string) => Promise<void>;
  logout: () => void;
}

export const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<MeResponse | null>(null);
  const [loading, setLoading] = useState(true);

  async function handleAuthResponse(data: AuthResponse) {
    localStorage.setItem("access_token", data.access_token);
    const me = await fetchMe();
    setUser(me);
  }

  async function login(email: string, password: string) {
    const data = await apiLogin(email, password);
    await handleAuthResponse(data);
  }

  async function signup(email: string, fullName: string | undefined, password: string) {
    await apiSignup({ email, full_name: fullName, password });
    const data = await apiLogin(email, password);
    await handleAuthResponse(data);
  }

  function logout() {
    localStorage.removeItem("access_token");
    setUser(null);
  }

  useEffect(() => {
    const token = localStorage.getItem("access_token");
    if (!token) {
      setLoading(false);
      return;
    }
    fetchMe()
      .then((me) => setUser(me))
      .catch(() => {
        localStorage.removeItem("access_token");
        setUser(null);
      })
      .finally(() => setLoading(false));
  }, []);

  const value: AuthContextValue = {
    user,
    loading,
    login,
    signup,
    logout
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

