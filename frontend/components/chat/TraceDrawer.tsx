"use client";

import { useEffect, useState } from "react";
import { TracePanel } from "@/components/TracePanel";
import { api, type Trace } from "@/lib/api";
import { useAppData } from "@/lib/app-data";
import { useAuth } from "@/lib/auth";

/** Slide-over with the full trace of one answer (GET /traces/{request_id}). */
export function TraceDrawer({ requestId, onClose }: { requestId: string | null; onClose: () => void }) {
  const { profile } = useAuth();
  const { info } = useAppData();
  const [trace, setTrace] = useState<Trace | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!requestId || !profile) return;
    setLoading(true);
    setError(null);
    api.trace(profile.employee_id, requestId).then(setTrace).catch((e) => setError(String(e.message ?? e)))
      .finally(() => setLoading(false));
  }, [requestId, profile]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  if (!requestId) return null;
  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      <div className="absolute inset-0 bg-black/30 backdrop-blur-[1px]" onClick={onClose} />
      <aside className="scroll-thin relative h-full w-full max-w-[520px] overflow-y-auto border-l shadow-2xl fade-up"
        style={{ background: "var(--panel)", borderColor: "var(--border)" }}>
        <TracePanel trace={trace} loading={loading} error={error} phoenixUrl={info?.phoenix_url ?? null} onClose={onClose} />
      </aside>
    </div>
  );
}
