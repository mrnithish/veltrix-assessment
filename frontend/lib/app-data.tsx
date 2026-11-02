"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, type DevInfo, type SessionSummary } from "./api";

interface AppData {
  sessions: SessionSummary[];
  sessionsLoading: boolean;
  refreshSessions: () => Promise<void>;
  removeSession: (id: string) => Promise<void>;
  docTitles: Record<string, string>;
  info: DevInfo | null;
  refreshInfo: () => void;
}

const Ctx = createContext<AppData | null>(null);

export function AppDataProvider({ children }: { children: React.ReactNode }) {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [sessionsLoading, setSessionsLoading] = useState(true);
  const [docTitles, setDocTitles] = useState<Record<string, string>>({});
  const [info, setInfo] = useState<DevInfo | null>(null);

  const refreshSessions = useCallback(async () => {
    try {
      setSessions(await api.sessions());
    } catch {
      /* shown as empty */
    } finally {
      setSessionsLoading(false);
    }
  }, []);

  const removeSession = useCallback(async (id: string) => {
    await api.deleteSession(id);
    setSessions((s) => s.filter((x) => x.session_id !== id));
  }, []);

  const refreshInfo = useCallback(() => {
    api.info().then(setInfo).catch(() => undefined);
  }, []);

  useEffect(() => {
    refreshSessions();
    refreshInfo();
    api.documents().then((d) => setDocTitles(Object.fromEntries(d.documents.map((x) => [x.doc_id, x.title]))))
      .catch(() => undefined);
  }, [refreshSessions, refreshInfo]);

  const value = useMemo(() => ({ sessions, sessionsLoading, refreshSessions, removeSession, docTitles, info, refreshInfo }),
    [sessions, sessionsLoading, refreshSessions, removeSession, docTitles, info, refreshInfo]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAppData(): AppData {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAppData outside AppDataProvider");
  return ctx;
}
