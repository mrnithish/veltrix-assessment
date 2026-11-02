"use client";

import { CalendarDays, FileText, MessageSquareText, Scale, ShieldAlert, Users, Wallet } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, newSessionId, streamChat, type AgentEvent, type ChatResponse } from "@/lib/api";
import { useAppData } from "@/lib/app-data";
import { useAuth } from "@/lib/auth";
import { usePrefs } from "@/lib/prefs";
import { AssistantMessage, UserMessage, type UIMessage } from "./AssistantMessage";
import { Composer, type ComposerHandle } from "./Composer";
import { TraceDrawer } from "./TraceDrawer";
import { useNow } from "@/components/TopBar";

const SUGGESTIONS: Record<string, { icon: typeof Wallet; text: string }[]> = {
  employee: [
    { icon: Scale, text: "How many sick days do I get per year?" },
    { icon: Wallet, text: "How many annual leave days will I have by the end of December?" },
    { icon: CalendarDays, text: "What are the public holidays in December?" },
    { icon: MessageSquareText, text: "Apply for annual leave next Monday to Wednesday" },
    { icon: FileText, text: "How many days a week can I work from home?" },
    { icon: ShieldAlert, text: "What was the sick leave allowance in 2025?" },
  ],
  manager: [
    { icon: Users, text: "Who on my team is off next week?" },
    { icon: Wallet, text: "What is my annual leave balance?" },
    { icon: FileText, text: "Who am I and who reports to me?" },
    { icon: CalendarDays, text: "What are the public holidays in December?" },
    { icon: Scale, text: "How much annual leave can I carry forward?" },
    { icon: MessageSquareText, text: "Cancel my next leave request" },
  ],
  hr: [
    { icon: Wallet, text: "What is the annual leave balance of E2004?" },
    { icon: FileText, text: "What are the performance improvement plan steps?" },
    { icon: Scale, text: "How many sick days do employees get per year?" },
    { icon: CalendarDays, text: "What are the public holidays in December?" },
    { icon: ShieldAlert, text: "Show me everyone's leave balances" },
    { icon: MessageSquareText, text: "What is the notice period after probation?" },
  ],
};

export function ChatView({ sessionId, prefill }: { sessionId: string | null; prefill?: string }) {
  const router = useRouter();
  const { profile } = useAuth();
  const { prefs } = usePrefs();
  const { refreshSessions, docTitles, info } = useAppData();
  const [messages, setMessages] = useState<UIMessage[]>([]);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [traceId, setTraceId] = useState<string | null>(null);
  const now = useNow(30_000);
  const activeId = useRef<string>(sessionId ?? newSessionId());
  const ownNavigation = useRef<string | null>(null);
  const abort = useRef<AbortController | null>(null);
  const composer = useRef<ComposerHandle>(null);
  const bottom = useRef<HTMLDivElement>(null);

  // Load a conversation from history (skip when the URL changed because we just created it).
  useEffect(() => {
    if (sessionId && ownNavigation.current === sessionId) return;
    activeId.current = sessionId ?? newSessionId();
    setMessages([]);
    setLoadError(null);
    if (!sessionId) return;
    setLoading(true);
    api.sessionMessages(sessionId).then((res) => {
      setMessages(res.messages.map((m) => ({
        key: `h-${m.id}`, role: m.role, text: m.content, response: m.response, createdAt: m.created_at,
      })));
    }).catch((e: ApiError) => setLoadError(e.status === 404 ? "This conversation was not found." : e.message))
      .finally(() => setLoading(false));
  }, [sessionId]);

  useEffect(() => {
    if (prefill) composer.current?.setText(prefill);
  }, [prefill]);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  const patchLast = (fn: (m: UIMessage) => UIMessage) =>
    setMessages((ms) => ms.map((m, i) => (i === ms.length - 1 ? fn(m) : m)));

  const send = useCallback(async (text: string) => {
    if (!profile || busy) return;
    const sid = activeId.current;
    const isNew = !sessionId;
    setBusy(true);
    setMessages((ms) => [...ms, { key: `u-${Date.now()}`, role: "user", text },
      { key: `a-${Date.now()}`, role: "assistant", text: "", running: true, events: [] }]);
    const controller = new AbortController();
    abort.current = controller;
    try {
      let response: ChatResponse;
      if (prefs.streaming) {
        response = await streamChat(profile.employee_id, sid, text, (e: AgentEvent) => {
          patchLast((m) => ({ ...m, events: [...(m.events ?? []), e] }));
        }, controller.signal);
      } else {
        response = await api.chat(profile.employee_id, sid, text);
      }
      patchLast((m) => ({ ...m, running: false, response, text: response.answer }));
      if (isNew) {
        ownNavigation.current = sid;
        router.replace(`/chat?s=${sid}`);
      }
      refreshSessions();
    } catch (e) {
      const err = e as ApiError;
      const message = err.name === "AbortError" ? "Stopped." : err.status === 403
        ? "This conversation belongs to another employee." : err.message;
      patchLast((m) => ({ ...m, running: false, error: message,
        events: (m.events ?? []).concat({ type: "final", t_ms: 0 } as AgentEvent) }));
    } finally {
      setBusy(false);
      abort.current = null;
    }
  }, [profile, busy, sessionId, prefs.streaming, router, refreshSessions]);

  if (!profile) return null;
  const suggestions = SUGGESTIONS[profile.role] ?? SUGGESTIONS.employee;
  const firstName = profile.full_name.split(" ")[0];

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="scroll-thin min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-3xl px-4 pb-6 pt-6 sm:px-6">
          {loading && <div className="space-y-4">{[0, 1].map((i) => <div key={i} className="skeleton h-24" />)}</div>}
          {loadError && <div className="muted py-10 text-center">{loadError}</div>}

          {!loading && !loadError && messages.length === 0 && (
            <div className="fade-up pt-[8vh]">
              <div className="mb-2 inline-flex items-center gap-2 rounded-full px-3 py-1 text-[12px]"
                style={{ background: "var(--accent-soft)", color: "var(--accent-text)" }}>
                {info ? `${info.agent_mode === "tools" ? "Tool calling" : "Code Mode"} · ${info.llm_model.split("/").pop()}` : "Assistant"}
              </div>
              <h2 className="text-[28px] font-semibold tracking-tight">
                {now ? (now.getHours() < 12 ? "Good morning" : now.getHours() < 17 ? "Good afternoon" : "Good evening") : "Hi"}, {firstName} — how can I help?
              </h2>
              {now && (
                <p className="mt-1 text-[13.5px] font-medium" style={{ color: "var(--text-2)" }}>
                  {now.toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric" })}
                  {" · "}{now.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}
                  {" · "}{profile.employee_id} · {profile.level} · {profile.region}
                  {profile.manager_id ? ` · reports to ${profile.manager_id}` : ""}
                  {profile.direct_reports.length ? ` · ${profile.direct_reports.length} direct reports` : ""}
                </p>
              )}
              <p className="muted mt-1.5 text-[14px]">
                Answers use only the HR documents that apply to you ({profile.region}, {profile.role === "hr" ? "HR" : profile.role})
                — with sources — and your leave data. Leave changes always ask for confirmation first.
              </p>
              <div className="mt-7 grid gap-2.5 sm:grid-cols-2">
                {suggestions.map((s) => (
                  <button key={s.text} onClick={() => send(s.text)} disabled={busy}
                    className="card group flex items-start gap-3 p-3.5 text-left transition-colors hover:border-[var(--accent)]">
                    <s.icon size={16} className="mt-0.5 shrink-0" style={{ color: "var(--accent)" }} />
                    <span className="text-[13.5px]">{s.text}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          <div className="space-y-6">
            {messages.map((m, i) => m.role === "user"
              ? <UserMessage key={m.key} text={m.text} />
              : <AssistantMessage key={m.key} msg={m} isLast={i === messages.length - 1} busy={busy} docTitles={docTitles}
                  onSend={send} onEdit={(t) => composer.current?.setText(t)} onOpenTrace={setTraceId} />)}
          </div>
          <div ref={bottom} className="h-2" />
        </div>
      </div>

      <div className="border-t px-4 pb-4 pt-3 sm:px-6" style={{ borderColor: "var(--border)", background: "var(--bg)" }}>
        <div className="mx-auto max-w-3xl">
          <Composer ref={composer} disabled={!!loadError} busy={busy} onSend={send} onStop={() => abort.current?.abort()} />
          <p className="muted mt-2 text-center text-[11.5px]">
            Signed in as {profile.employee_id}. Identity, role and region come from the HR database, not from the chat.
          </p>
        </div>
      </div>
      <TraceDrawer requestId={traceId} onClose={() => setTraceId(null)} />
    </div>
  );
}
