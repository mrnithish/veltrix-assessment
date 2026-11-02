"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";

export type Theme = "system" | "light" | "dark";

export interface Prefs {
  theme: Theme;
  streaming: boolean; // live "thinking" via /chat/stream
  thinkingExpanded: boolean; // keep the thinking panel open after an answer
  showRouteBadges: boolean;
}

const DEFAULTS: Prefs = { theme: "system", streaming: true, thinkingExpanded: false, showRouteBadges: true };
const KEY = "veltrix.prefs";

const PrefsContext = createContext<{ prefs: Prefs; update: (p: Partial<Prefs>) => void } | null>(null);

export function PrefsProvider({ children }: { children: React.ReactNode }) {
  const [prefs, setPrefs] = useState<Prefs>(DEFAULTS);

  useEffect(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(KEY) || "null");
      if (saved) setPrefs({ ...DEFAULTS, ...saved });
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    const root = document.documentElement;
    if (prefs.theme === "system") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", prefs.theme);
  }, [prefs.theme]);

  const value = useMemo(() => ({
    prefs,
    update: (p: Partial<Prefs>) => setPrefs((cur) => {
      const next = { ...cur, ...p };
      try {
        localStorage.setItem(KEY, JSON.stringify(next));
      } catch {
        /* ignore */
      }
      return next;
    }),
  }), [prefs]);

  return <PrefsContext.Provider value={value}>{children}</PrefsContext.Provider>;
}

export function usePrefs() {
  const ctx = useContext(PrefsContext);
  if (!ctx) throw new Error("usePrefs outside PrefsProvider");
  return ctx;
}
