"use client";

import type { Trace, TraceStep } from "@/lib/api";
import { StatusBadge } from "./Badges";

const BUDGET = 3000;

function Section({ title, children, right }: { title: string; children: React.ReactNode; right?: React.ReactNode }) {
  return (
    <section className="border-t px-4 py-3" style={{ borderColor: "var(--border)" }}>
      <div className="mb-2 flex items-center gap-2">
        <h3 className="text-[12px] font-semibold uppercase tracking-wide muted">{title}</h3>
        <div className="ml-auto">{right}</div>
      </div>
      {children}
    </section>
  );
}

function Timeline({ steps, total }: { steps: TraceStep[]; total: number }) {
  const max = Math.max(total, 1);
  return (
    <div className="space-y-1">
      {steps.map((s, i) => (
        <div key={i} className="grid grid-cols-[150px_1fr_56px] items-center gap-2 text-[12px]">
          <span className="truncate font-mono" title={s.name}>{s.name}</span>
          <div className="relative h-2.5 rounded" style={{ background: "var(--panel-2)" }}>
            <div className="absolute h-2.5 rounded"
              style={{
                left: `${(s.start_ms / max) * 100}%`,
                width: `${Math.max((s.duration_ms / max) * 100, 0.8)}%`,
                background: s.error ? "var(--bad)" : "var(--accent)",
              }} />
          </div>
          <span className="text-right muted tabular-nums">{Math.round(s.duration_ms)}ms</span>
        </div>
      ))}
    </div>
  );
}

export function TracePanel({ trace, loading, error, phoenixUrl, onClose }: {
  trace: Trace | null; loading: boolean; error: string | null; phoenixUrl: string | null; onClose: () => void;
}) {
  if (loading) return <div className="p-6 muted text-[13px]">Loading trace…</div>;
  if (error) return <div className="p-6 text-[13px]" style={{ color: "var(--bad)" }}>{error}</div>;
  if (!trace) {
    return (
      <div className="p-6 text-[13px] muted leading-relaxed">
        Select <b>View trace</b> on any answer to see how it was produced: identity, document eligibility, the
        code the model wrote, every tool call and permission decision, retrieved passages, precedence decisions,
        and each LLM call with its corpus-token count.
      </div>
    );
  }
  const execSteps = trace.steps.filter((s) => s.name === "codemode.execute");
  const pack = trace.steps.find((s) => s.name === "budget.pack");
  const plan = trace.plan_1 ?? trace.plan_0;
  return (
    <div className="text-[13px]">
      <div className="flex items-center gap-2 px-4 py-3">
        <div>
          <div className="font-semibold">Trace</div>
          <div className="font-mono text-[11px] muted">{trace.request_id}</div>
        </div>
        <button className="btn ml-auto" onClick={onClose}>Close</button>
      </div>

      <Section title="Summary">
        <div className="grid grid-cols-2 gap-x-4 gap-y-1">
          <span className="muted">Requester</span>
          <span className="font-mono">{trace.requester.employee_id} · {trace.requester.role} · {trace.requester.region}</span>
          <span className="muted">Agent mode</span><span>{trace.agent_mode}</span>
          {trace.llm && (<><span className="muted">LLM</span>
            <span className="font-mono text-[11px]">{trace.llm.provider} · {trace.llm.model}</span></>)}
          <span className="muted">Today</span><span>{trace.today}</span>
          <span className="muted">Total</span><span>{(trace.total_ms / 1000).toFixed(2)}s</span>
          {trace.pending_proposal && (<>
            <span className="muted">Pending proposal</span>
            <span>{trace.pending_proposal.name} · {trace.pending_proposal.confirmed ? "confirmed" : "discarded"}</span>
          </>)}
          {trace.leave_type_guard && (<><span className="muted">Guard</span><span>{trace.leave_type_guard}</span></>)}
          {trace.error && (<><span className="muted">Error</span><span style={{ color: "var(--bad)" }}>{trace.error}</span></>)}
        </div>
      </Section>

      {(trace.ungrounded_candidates?.length || trace.answer_unsupported_numbers?.length || trace.leave_action_guard) && (
        <Section title="Safety checks">
          <div className="space-y-1.5 text-[12.5px]">
            {trace.leave_action_guard && <div>• {trace.leave_action_guard}</div>}
            {trace.ungrounded_candidates?.map((u, i) => (
              <div key={i} style={{ color: "var(--warn)" }}>
                • Dropped “{u.value}” from <span className="font-mono">{u.doc_id}</span> — {u.reason ?? "not in passage"}
              </div>
            ))}
            {!!trace.answer_unsupported_numbers?.length && (
              <div style={{ color: "var(--warn)" }}>
                • Numbers in the answer not found in any source (calculated or to review): {trace.answer_unsupported_numbers.join(", ")}
              </div>
            )}
          </div>
        </Section>
      )}

      <Section title="Document eligibility" right={<span className="muted text-[11px]">filtered before retrieval</span>}>
        <div className="flex flex-wrap gap-1.5">
          {Object.entries(trace.eligibility).map(([k, v]) => (
            <span key={k} className="chip">{k.replace("_", " ")}: <b>{v}</b></span>
          ))}
        </div>
      </Section>

      <Section title="Timeline"><Timeline steps={trace.steps} total={trace.total_ms} /></Section>

      <Section title="LLM calls" right={phoenixUrl ? (
        <a className="text-[12px] underline" style={{ color: "var(--accent)" }} href={phoenixUrl} target="_blank"
          rel="noreferrer">Open Phoenix ↗</a>) : null}>
        {trace.llm_calls.length === 0 && <div className="muted">No LLM calls (handled deterministically).</div>}
        <div className="space-y-2">
          {trace.llm_calls.map((c, i) => (
            <div key={i} className="rounded-lg p-2.5" style={{ background: "var(--panel-2)" }}>
              <div className="flex items-center gap-2">
                <span className="font-mono font-medium">{c.purpose}</span>
                <span className="muted text-[11px]">{c.provider} · {c.model}</span>
                <span className="ml-auto muted tabular-nums">{Math.round(c.latency_ms)}ms</span>
              </div>
              <div className="mt-1.5 flex items-center gap-2 text-[11px]">
                <span className="muted w-24">corpus tokens</span>
                <div className="h-1.5 flex-1 rounded" style={{ background: "var(--border)" }}>
                  <div className="h-1.5 rounded" style={{ width: `${Math.min(c.corpus_tokens / BUDGET, 1) * 100}%`,
                    background: c.corpus_tokens > BUDGET ? "var(--bad)" : "var(--ok)" }} />
                </div>
                <span className="tabular-nums">{c.corpus_tokens} / {BUDGET}</span>
              </div>
              <div className="mt-1 text-[11px] muted">prompt {c.prompt_tokens} · completion {c.completion_tokens}</div>
            </div>
          ))}
        </div>
      </Section>

      {plan && (
        <Section title="Plan" right={<span className="chip">{plan.action}{plan.refuse_reason ? ` · ${plan.refuse_reason}` : ""}</span>}>
          {plan.code && <pre className="code">{plan.code}</pre>}
        </Section>
      )}

      {execSteps.map((s, i) => (
        <Section key={i} title={`Sandbox run ${i + 1}`}
          right={<StatusBadge status={s.ok ? "success" : "error"} />}>
          <div className="muted mb-1 text-[11px]">{String(s.sandbox_ms ?? "")} ms · isolated subprocess, no DB/network/secrets</div>
          {Array.isArray(s.calls) && s.calls.length > 0 && (
            <ol className="mb-2 list-decimal space-y-0.5 pl-5 font-mono text-[11px]">
              {(s.calls as { fn: string; kwargs: Record<string, unknown> }[]).map((c, j) => (
                <li key={j}>{c.fn}({Object.entries(c.kwargs).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(", ")})</li>
              ))}
            </ol>
          )}
          {typeof s.error === "string" && s.error && <div style={{ color: "var(--bad)" }}>{s.error}</div>}
          {typeof s.stdout === "string" && s.stdout && <pre className="code mt-1">{s.stdout}</pre>}
        </Section>
      ))}

      {trace.all_tool_records && trace.all_tool_records.length > 0 && (
        <Section title="Tool calls & permission checks">
          <div className="space-y-1">
            {trace.all_tool_records.map((t, i) => (
              <div key={i} className="flex flex-wrap items-center gap-2 text-[12px]">
                <span className="font-mono">{t.name}</span>
                <span className="muted font-mono text-[11px]">{JSON.stringify(t.args)}</span>
                {t.error_kind && <span className="chip">{t.error_kind}</span>}
                <span className="ml-auto"><StatusBadge status={t.status} /></span>
              </div>
            ))}
          </div>
        </Section>
      )}

      {trace.searches && trace.searches.length > 0 && (
        <Section title="Retrieval" right={pack ? <span className="chip">{String(pack.corpus_tokens)} corpus tokens</span> : null}>
          {trace.searches.map((s, i) => (
            <div key={i} className="mb-2">
              <div><span className="muted">query</span> “{s.query}” <span className="muted">as of {s.as_of}</span></div>
              <div className="mt-1 flex flex-wrap gap-1">
                {s.hits.map((h) => <span key={h} className="chip font-mono text-[11px]">{h}</span>)}
                {s.upcoming.map((h) => <span key={h} className="chip font-mono text-[11px]"
                  style={{ color: "var(--warn)" }}>{h} (upcoming)</span>)}
              </div>
            </div>
          ))}
          {pack && Array.isArray(pack.dropped) && pack.dropped.length > 0 && (
            <div className="muted text-[11px]">Dropped to stay within budget: {(pack.dropped as string[]).join(", ")}</div>
          )}
        </Section>
      )}

      {trace.resolutions && trace.resolutions.length > 0 && (
        <Section title="Precedence decisions" right={trace.coverage ? <span className="chip">coverage: {trace.coverage}</span> : null}>
          <div className="space-y-2">
            {trace.resolutions.map((r, i) => (
              <div key={i} className="rounded-lg p-2.5" style={{ background: "var(--panel-2)" }}>
                <div className="flex items-center gap-2">
                  <span className="font-medium">{r.rule}</span>
                  <span className="chip ml-auto" style={r.status === "conflict" ? { color: "var(--warn)" } : undefined}>{r.status}</span>
                </div>
                {r.winners.map(([doc, val]) => (
                  <div key={doc + val} className="mt-1 text-[12px]">✓ <span className="font-mono">{doc}</span>: {val}</div>
                ))}
                {r.overruled.map(([doc, val, why]) => (
                  <div key={doc + val} className="mt-0.5 text-[12px] muted line-through decoration-1">
                    <span className="font-mono">{doc}</span>: {val} <span className="no-underline">(lost on {why})</span>
                  </div>
                ))}
                {r.upcoming && (
                  <div className="mt-1 text-[12px]" style={{ color: "var(--warn)" }}>
                    ↗ upcoming <span className="font-mono">{r.upcoming[0]}</span> from {r.upcoming[2]}: {r.upcoming[1]}
                  </div>
                )}
              </div>
            ))}
          </div>
        </Section>
      )}
    </div>
  );
}
