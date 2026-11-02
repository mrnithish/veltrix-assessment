"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, setAuth, type Profile } from "./api";

interface AuthState {
  ready: boolean;
  token: string | null;
  profile: Profile | null;
  login: (identifier: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);
const KEY = "veltrix.auth";

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);
  const [token, setToken] = useState<string | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);

  const logout = useCallback(() => {
    try {
      localStorage.removeItem(KEY);
    } catch {
      /* storage unavailable */
    }
    setAuth(null);
    setToken(null);
    setProfile(null);
  }, []);

  // Restore a saved session and re-validate it against the API.
  useEffect(() => {
    let saved: { token: string; profile: Profile } | null = null;
    try {
      saved = JSON.parse(localStorage.getItem(KEY) || "null");
    } catch {
      saved = null;
    }
    if (!saved) {
      setReady(true);
      return;
    }
    setAuth(saved.token, logout);
    setToken(saved.token);
    setProfile(saved.profile);
    api.me().then(setProfile).catch(() => logout()).finally(() => setReady(true));
  }, [logout]);

  const login = useCallback(async (identifier: string, password: string) => {
    const res = await api.login(identifier, password);
    setAuth(res.token, logout);
    setToken(res.token);
    setProfile(res.profile);
    try {
      localStorage.setItem(KEY, JSON.stringify(res));
    } catch {
      /* storage unavailable: session lasts for this tab */
    }
  }, [logout]);

  const value = useMemo(() => ({ ready, token, profile, login, logout }), [ready, token, profile, login, logout]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth outside AuthProvider");
  return ctx;
}
