"use client";

import { Check, CheckCircle2, Copy, FileText, ListTree, Pencil, Wrench, X, XCircle } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { RouteBadge, StatusBadge } from "@/components/Badges";
import { api, type AgentEvent, type ChatResponse } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { usePrefs } from "@/lib/prefs";
import { stepsFromEvents, stepsFromTrace, type ThinkingStep, type ThinkingSummary } from "@/lib/thinking";
import { Markdown } from "./Markdown";
import { ThinkingBlock } from "./ThinkingBlock";

export interface UIMessage {
  key: string;
  role: "user" | "assistant";
  text: string;
  response?: ChatResponse;
  events?: AgentEvent[]; // live stream events
  running?: boolean;
  error?: string;
  createdAt?: string;
}

const TOOL_LABEL: Record<string, string> = {
  get_leave_balance: "Leave balance",
  list_leave_requests: "Leave requests",
  get_team_leave: "Team leave",
  apply_leave: "Apply for leave",
  cancel_leave: "Cancel leave",
};

export function AssistantMessage({ msg, isLast, busy, docTitles, onSend, onEdit, onOpenTrace }: {
  msg: UIMessage; isLast: boolean; busy: boolean; docTitles: Record<string, string>;
  onSend: (text: string) => void; onEdit: (text: string) => void; onOpenTrace: (requestId: string) => void;
}) {
  const { profile } = useAuth();
  const { prefs } = usePrefs();
  const [copied, setCopied] = useState(false);
  const [history, setHistory] = useState<{ steps: ThinkingStep[]; summary: ThinkingSummary } | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const r = msg.response;

  // Live events win; for stored messages, load the trace lazily the first time.
  const live = useMemo(() => (msg.events?.length ? stepsFromEvents(msg.events) : null), [msg.events]);
  const needsTrace = !live && !!r?.request_id;
  useEffect(() => {
    if (!needsTrace || history || !profile || !r) return;
    setHistoryLoading(true);
    api.trace(profile.employee_id, r.request_id).then((t) => setHistory(stepsFromTrace(t)))
      .catch(() => setHistory({ steps: [], summary: { mode: "codemode", llmCalls: 0, maxCorpusTokens: 0, running: false } }))
      .finally(() => setHistoryLoading(false));
  }, [needsTrace, history, profile, r]);

  const thinking = live ?? history;
  const docIds = useMemo(() => new Set(r?.citations.map((c) => c.doc_id) ?? []), [r]);

  return (
    <div className="fade-up flex gap-3">
      <div className="mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-lg text-[13px] font-bold text-white"
        style={{ background: "linear-gradient(135deg, var(--accent), #8b5cf6)" }}>V</div>
      <div className="min-w-0 flex-1">
        <div className="mb-1.5 flex items-center gap-2">
          <span className="text-[13.5px] font-semibold">Veltrix Assistant</span>
          {r && prefs.showRouteBadges && <RouteBadge route={r.route} answer={r.answer} />}
        </div>

        {(thinking || msg.running) && (
          <ThinkingBlock steps={thinking?.steps ?? []} summary={thinking?.summary ?? (msg.running ? {
            mode: "codemode", llmCalls: 0, maxCorpusTokens: 0, running: true } : null)}
            defaultOpen={prefs.thinkingExpanded} loading={historyLoading} />
        )}

        {msg.error && (
          <div className="rounded-xl px-4 py-3 text-[13.5px]" style={{ background: "var(--bad-soft)", color: "var(--bad)" }}>
            {msg.error}
          </div>
        )}

        {r && <Markdown text={r.answer} docIds={docIds} titles={docTitles} />}

        {r && r.citations.length > 0 && (
          <div className="mt-3">
            <div className="muted mb-1.5 text-[11.5px] font-semibold uppercase tracking-wide">Sources</div>
            <div className="flex flex-wrap gap-1.5">
              {r.citations.map((c) => (
                <span key={`${c.doc_id}-${c.locator}`} className="chip" title={docTitles[c.doc_id] ?? c.doc_id}>
                  <FileText size={12} className="muted" />
                  <span className="font-medium">{docTitles[c.doc_id] ?? c.doc_id}</span>
                  <span className="muted">· {c.locator}</span>
                </span>
              ))}
            </div>
          </div>
        )}

        {r && r.tool_calls.length > 0 && (
          <div className="mt-3 space-y-1.5">
            {r.tool_calls.map((t, i) => (
              <div key={i} className="flex flex-wrap items-center gap-2 rounded-xl border px-3 py-2 text-[12.5px]"
                style={{ borderColor: "var(--border)", background: "var(--panel)" }}>
                <Wrench size={13} className="muted" />
                <span className="font-medium">{TOOL_LABEL[t.name] ?? t.name}</span>
                <span className="muted font-mono">{t.name}({Object.entries(t.args).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(", ")})</span>
                <span className="ml-auto"><StatusBadge status={t.status} /></span>
              </div>
            ))}
          </div>
        )}

        {r?.pending_confirmation && isLast && (
          <div className="mt-3 flex flex-wrap items-center gap-2 rounded-xl border p-3"
            style={{ borderColor: "var(--warn)", background: "var(--warn-soft)" }}>
            <span className="mr-auto text-[13px]" style={{ color: "var(--warn)" }}>
              Nothing is saved until you confirm.
            </span>
            <button className="btn btn-primary" disabled={busy} onClick={() => onSend("yes")}>
              <CheckCircle2 size={15} /> Confirm
            </button>
            <button className="btn" disabled={busy} onClick={() => onEdit("Change it to ")}>
              <Pencil size={14} /> Change
            </button>
            <button className="btn" disabled={busy} onClick={() => onSend("No, don't do that")}>
              <XCircle size={15} /> Cancel
            </button>
          </div>
        )}

        {r && (
          <div className="mt-2 flex items-center gap-1">
            <button className="btn btn-ghost !px-2 !py-1 text-[12px]" title="Copy answer" onClick={() => {
              navigator.clipboard?.writeText(r.answer);
              setCopied(true);
              setTimeout(() => setCopied(false), 1200);
            }}>
              {copied ? <Check size={14} /> : <Copy size={14} />}
            </button>
            <button className="btn btn-ghost !px-2 !py-1 text-[12px]" title="Full trace" onClick={() => onOpenTrace(r.request_id)}>
              <ListTree size={14} /> <span className="muted">Trace</span>
            </button>
            <span className="muted ml-1 hidden font-mono text-[11px] sm:inline">{r.request_id.slice(0, 8)}</span>
          </div>
        )}
      </div>
    </div>
  );
}

export function UserMessage({ text }: { text: string }) {
  return (
    <div className="fade-up flex justify-end">
      <div className="max-w-[78%] whitespace-pre-wrap rounded-2xl rounded-br-md px-4 py-2.5 text-[14.5px] leading-relaxed"
        style={{ background: "var(--accent-soft)", color: "var(--text)" }}>
        {text}
      </div>
    </div>
  );
}

export function CloseButton({ onClick }: { onClick: () => void }) {
  return <button className="btn btn-ghost !p-1.5" onClick={onClick} aria-label="Close"><X size={16} /></button>;
}
