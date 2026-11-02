"use client";

import {
  AlertTriangle, ArrowRight, Boxes, Coins, Cpu, Database, FileSearch, Gauge, GitBranch, Layers, Plug, RefreshCw,
  Scale, ShieldCheck, Shuffle, Timer, Workflow,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ErrorNote, Page, PageHeader, SkeletonRows, StatCard } from "@/components/ui";
import { api, type LlmSelection, type Usage } from "@/lib/api";

const fmt = (n: number | null | undefined) => (n ?? 0).toLocaleString("en-US");
const short = (m: string) => m.split("/").pop() ?? m;

// ---------------------------------------------------------------- charts (plain HTML; thin marks, one axis)
function TokensByDay({ rows }: { rows: Usage["by_day"] }) {
  const [hover, setHover] = useState<number | null>(null);
  const [table, setTable] = useState(false);
  const max = Math.max(1, ...rows.map((r) => r.prompt_tokens + r.completion_tokens));
  if (rows.length === 0) return <p className="muted py-8 text-center text-[13px]">No LLM calls yet in this period.</p>;
  return (
    <div>
      <div className="mb-3 flex items-center gap-4 text-[12px]">
        <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: "var(--series-1)" }} /> Prompt tokens</span>
        <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: "var(--series-2)" }} /> Completion tokens</span>
        <button className="muted ml-auto underline-offset-2 hover:underline" onClick={() => setTable((t) => !t)}>{table ? "Chart" : "Table"} view</button>
      </div>
      {table ? (
        <table className="table">
          <thead><tr><th>Day</th><th className="text-right">Calls</th><th className="text-right">Prompt</th><th className="text-right">Completion</th><th className="text-right">Corpus</th></tr></thead>
          <tbody>{rows.map((r) => (
            <tr key={r.day}><td>{r.day}</td><td className="text-right tabular-nums">{fmt(r.calls)}</td><td className="text-right tabular-nums">{fmt(r.prompt_tokens)}</td>
              <td className="text-right tabular-nums">{fmt(r.completion_tokens)}</td><td className="text-right tabular-nums">{fmt(r.corpus_tokens)}</td></tr>
          ))}</tbody>
        </table>
      ) : (
        <div className="relative">
          <div className="flex h-44 items-end gap-2 border-b" style={{ borderColor: "var(--border-strong)" }}>
            {rows.map((r, i) => {
              const total = r.prompt_tokens + r.completion_tokens;
              const h = (total / max) * 100;
              return (
                <div key={r.day} className="relative flex h-full flex-1 cursor-default items-end justify-center"
                  onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
                  <div className="flex w-full max-w-[34px] flex-col-reverse overflow-hidden rounded-t" style={{ height: `${h}%`, gap: 2 }}>
                    <div style={{ background: "var(--series-1)", flexGrow: r.prompt_tokens || 0.0001 }} />
                    <div style={{ background: "var(--series-2)", flexGrow: r.completion_tokens || 0.0001 }} />
                  </div>
                  {hover === i && (
                    <div className="card pointer-events-none absolute bottom-full z-10 mb-2 w-44 p-2.5 text-[12px] !shadow-[var(--shadow-lg)]">
                      <div className="font-semibold">{r.day}</div>
                      <div className="mt-1 flex justify-between"><span className="muted">Calls</span><span className="tabular-nums">{fmt(r.calls)}</span></div>
                      <div className="flex justify-between"><span className="muted">Prompt</span><span className="tabular-nums">{fmt(r.prompt_tokens)}</span></div>
                      <div className="flex justify-between"><span className="muted">Completion</span><span className="tabular-nums">{fmt(r.completion_tokens)}</span></div>
                      <div className="flex justify-between"><span className="muted">Corpus (in prompt)</span><span className="tabular-nums">{fmt(r.corpus_tokens)}</span></div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
          <div className="mt-1.5 flex gap-2">
            {rows.map((r) => <div key={r.day} className="muted flex-1 text-center text-[10.5px]">{r.day.slice(5)}</div>)}
          </div>
          <div className="muted absolute -top-1 right-0 text-[10.5px]">max {fmt(max)} tokens/day</div>
        </div>
      )}
    </div>
  );
}

function BudgetHistogram({ rows }: { rows: Usage["corpus_budget"] }) {
  const order = ["0", "1-1000", "1001-2000", "2001-3000"];
  const data = order.map((b) => ({ bucket: b, calls: rows.find((r) => r.bucket === b)?.calls ?? 0 }));
  const max = Math.max(1, ...data.map((d) => d.calls));
  return (
    <div className="space-y-2">
      {data.map((d) => (
        <div key={d.bucket} className="grid grid-cols-[86px_1fr_44px] items-center gap-2 text-[12.5px]" title={`${d.calls} call(s) with ${d.bucket} corpus tokens`}>
          <span className="muted tabular-nums">{d.bucket}</span>
          <div className="h-3 rounded" style={{ background: "var(--panel-2)" }}>
            <div className="h-3 rounded" style={{ width: `${(d.calls / max) * 100}%`, background: "var(--series-1)", minWidth: d.calls ? 4 : 0 }} />
          </div>
          <span className="text-right tabular-nums">{fmt(d.calls)}</span>
        </div>
      ))}
      <p className="muted pt-1 text-[11.5px]">Corpus tokens per LLM call (cl100k_base). Hard limit 3,000 — enforced before every call.</p>
    </div>
  );
}

// ---------------------------------------------------------------- architecture
function Node({ icon: Icon, title, body, tone = "var(--accent)" }: { icon: typeof Cpu; title: string; body: string; tone?: string }) {
  return (
    <div className="rounded-xl border p-3" style={{ borderColor: "var(--border)", background: "var(--panel)" }}>
      <div className="flex items-center gap-2 text-[13px] font-semibold"><Icon size={15} style={{ color: tone }} /> {title}</div>
      <div className="muted mt-1 text-[11.5px] leading-snug">{body}</div>
    </div>
  );
}

function Arrow() {
  return <div className="flex items-center justify-center"><ArrowRight size={16} className="muted rotate-90 lg:rotate-0" /></div>;
}

function Architecture() {
  return (
    <div className="space-y-3">
      <div className="grid gap-2 lg:grid-cols-[1fr_auto_1.2fr_auto_1fr] lg:items-stretch">
        <div className="space-y-2">
          <div className="muted text-[11px] font-semibold uppercase tracking-wide">Clients</div>
          <Node icon={Boxes} title="Web app" body="Next.js · login · live thinking via /chat/stream" />
          <Node icon={Plug} title="Your MCP client" body="Claude Code · Cursor · VS Code · agents → /mcp/" />
          <Node icon={Workflow} title="Graded API" body="POST /chat · X-Employee-Id · exact contract" />
        </div>
        <Arrow />
        <div className="space-y-2">
          <div className="muted text-[11px] font-semibold uppercase tracking-wide">Agent pipeline (FastAPI)</div>
          <Node icon={ShieldCheck} title="1 · Identity & session" body="Header/token → HR DB · 401/403 · session ownership · pending proposal" tone="var(--ok)" />
          <Node icon={Cpu} title="2 · Plan (LLM, 0 corpus tokens)" body="Writes a Python program (Code Mode) or clarify / refuse" />
          <Node icon={Layers} title="3 · Sandbox" body="AST allowlist · subprocess · no DB/net/secrets · uid nobody · RPC to tools" tone="var(--ok)" />
          <Node icon={FileSearch} title="4 · Retrieve" body="Eligibility filter inside Qdrant + BM25 · RRF + per-retriever top-3 · pack ≤ 3,000 tokens" tone="var(--info)" />
          <Node icon={Scale} title="5 · Extract → resolve (Python)" body="LLM lists candidates · grounding check · precedence authority → scope → recency" />
          <Node icon={Cpu} title="6 · Compose (LLM)" body="Answer from resolved facts + tool results · route · citations · PII masking" />
        </div>
        <Arrow />
        <div className="space-y-2">
          <div className="muted text-[11px] font-semibold uppercase tracking-wide">State & observability</div>
          <Node icon={Database} title="HR DB (veltrix.db)" body="Employees, balances, requests · writes in one transaction" tone="var(--info)" />
          <Node icon={Database} title="Qdrant + state DB" body="Vectors with payload filter · sessions, proposals, traces, audit, llm_usage, holidays" tone="var(--info)" />
          <Node icon={Gauge} title="Telemetry" body="OTel → Phoenix · JSON logs (PII-scrubbed) · Prometheus · per-request trace · token usage" tone="var(--warn)" />
        </div>
      </div>
    </div>
  );
}

export default function SystemPage() {
  const [usage, setUsage] = useState<Usage | null>(null);
  const [llm, setLlm] = useState<LlmSelection | null>(null);
  const [days, setDays] = useState(14);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setError(null);
    api.usage(days).then(setUsage).catch((e) => setError(e.message));
    api.llm().then(setLlm).catch(() => undefined);
  }, [days]);
  useEffect(load, [load]);

  const t = usage?.totals;
  const fallbackRate = t && t.calls ? Math.round((t.fallbacks / t.calls) * 100) : 0;
  const purposes = useMemo(() => usage?.by_purpose ?? [], [usage]);

  return (
    <Page wide>
      <PageHeader title="Architecture & usage"
        subtitle="How a request flows, how failures fall back, and what every LLM call consumes."
        actions={<>
          <select className="input !w-auto !py-1.5" value={days} onChange={(e) => setDays(Number(e.target.value))}>
            {[1, 7, 14, 30, 90].map((d) => <option key={d} value={d}>Last {d} day{d > 1 ? "s" : ""}</option>)}
          </select>
          <button className="btn" onClick={load}><RefreshCw size={14} /> Refresh</button>
        </>} />
      {error && <ErrorNote message={error} />}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="LLM calls" icon={Cpu} value={t ? fmt(t.calls) : "—"} hint={t ? `${fmt(t.requests)} chat requests${usage?.mine ? ` · ${fmt(usage.mine.calls)} yours` : ""}` : undefined} />
        <StatCard label="Tokens consumed" icon={Coins} tone="info" value={t ? fmt(t.prompt_tokens + t.completion_tokens) : "—"}
          hint={t ? `${fmt(t.prompt_tokens)} prompt · ${fmt(t.completion_tokens)} completion` : undefined} />
        <StatCard label="Max corpus tokens / call" icon={Gauge} tone="ok" value={t ? `${fmt(t.max_corpus_tokens)}` : "—"} hint="budget 3,000 (cl100k_base)" />
        <StatCard label="Fallback rate" icon={Shuffle} tone="warn" value={t ? `${fallbackRate}%` : "—"}
          hint={t ? `${fmt(t.fallbacks)} answered by a backup model · ${fmt(t.errors)} failed · avg ${fmt(t.avg_latency_ms)} ms` : undefined} />
      </div>

      <div className="mt-5 grid gap-5 xl:grid-cols-[1.5fr_1fr]">
        <div className="card p-5">
          <h2 className="mb-4 text-[15px] font-semibold">Token consumption per day</h2>
          {!usage ? <SkeletonRows rows={3} /> : <TokensByDay rows={usage.by_day} />}
        </div>
        <div className="card p-5">
          <h2 className="mb-4 text-[15px] font-semibold">Corpus tokens per call</h2>
          {!usage ? <SkeletonRows rows={3} /> : <BudgetHistogram rows={usage.corpus_budget} />}
        </div>
      </div>

      <div className="mt-5 grid gap-5 xl:grid-cols-2">
        <div className="card overflow-hidden">
          <div className="border-b px-5 py-3.5 text-[15px] font-semibold" style={{ borderColor: "var(--border)" }}>By pipeline step</div>
          <table className="table">
            <thead><tr><th>Step</th><th className="text-right">Calls</th><th className="text-right">Prompt</th><th className="text-right">Completion</th><th className="text-right">Avg corpus</th><th className="text-right">Avg ms</th></tr></thead>
            <tbody>{purposes.map((p) => (
              <tr key={p.purpose}><td className="font-medium">{p.purpose}</td><td className="text-right tabular-nums">{fmt(p.calls)}</td>
                <td className="text-right tabular-nums">{fmt(p.prompt_tokens)}</td><td className="text-right tabular-nums">{fmt(p.completion_tokens)}</td>
                <td className="text-right tabular-nums">{fmt(p.avg_corpus_tokens)}</td><td className="text-right tabular-nums">{fmt(p.avg_latency_ms)}</td></tr>
            ))}</tbody>
          </table>
        </div>
        <div className="card overflow-hidden">
          <div className="border-b px-5 py-3.5 text-[15px] font-semibold" style={{ borderColor: "var(--border)" }}>By model</div>
          <table className="table">
            <thead><tr><th>Model</th><th className="text-right">Calls</th><th className="text-right">Tokens</th><th className="text-right">Avg ms</th><th className="text-right">Errors</th></tr></thead>
            <tbody>{(usage?.by_model ?? []).map((m) => (
              <tr key={m.provider + m.model}><td><span className="font-mono text-[12.5px]">{short(m.model)}</span> <span className="muted text-[11.5px]">{m.provider}</span></td>
                <td className="text-right tabular-nums">{fmt(m.calls)}</td><td className="text-right tabular-nums">{fmt(m.tokens)}</td>
                <td className="text-right tabular-nums">{fmt(m.avg_latency_ms)}</td>
                <td className="text-right tabular-nums">{m.errors ? <span className="inline-flex items-center gap-1"><AlertTriangle size={12} style={{ color: "var(--warn)" }} />{m.errors}</span> : 0}</td></tr>
            ))}</tbody>
          </table>
        </div>
      </div>

      <div className="card mt-5 p-5">
        <div className="mb-4 flex items-center gap-2"><GitBranch size={16} style={{ color: "var(--accent)" }} /><h2 className="text-[15px] font-semibold">Fallback & hedging policy</h2></div>
        {llm && (
          <div className="flex flex-wrap items-center gap-2 text-[12.5px]">
            <span className="chip !py-1"><b>{llm.provider}</b>&nbsp;· {short(llm.model)} <span className="muted">primary</span></span>
            {(llm.fallbacks ?? []).map((f, i) => (
              <span key={f} className="flex items-center gap-2"><ArrowRight size={14} className="muted" />
                <span className="chip !py-1">{short(f)} <span className="muted">fallback {i + 1}</span></span></span>
            ))}
          </div>
        )}
        <ul className="muted mt-4 grid gap-2 text-[12.5px] md:grid-cols-2">
          <li className="flex gap-2"><Timer size={14} className="mt-0.5 shrink-0" /> Slow primary (&gt; {llm?.hedge_after_s ?? 4} s): the next model starts in parallel; first good reply wins (hedged request).</li>
          <li className="flex gap-2"><Shuffle size={14} className="mt-0.5 shrink-0" /> Timeout, 5xx overload, 404/410 or rate limit: move to the next model at once.</li>
          <li className="flex gap-2"><Gauge size={14} className="mt-0.5 shrink-0" /> Each call ≤ {llm?.llm_timeout_s ?? 20} s; whole request finishes by {llm?.request_deadline_s ?? 26} s (contract: 30 s) with a graceful answer and a saved trace.</li>
          <li className="flex gap-2"><ShieldCheck size={14} className="mt-0.5 shrink-0" /> Unsupported parameters (JSON mode, max_tokens, temperature, seed) are adapted once and remembered per model.</li>
        </ul>
      </div>

      <div className="card mt-5 overflow-hidden">
        <div className="border-b px-5 py-3.5 text-[15px] font-semibold" style={{ borderColor: "var(--border)" }}>Recent LLM calls</div>
        <div className="overflow-x-auto">
          <table className="table">
            <thead><tr><th>Time (UTC)</th><th>Step</th><th>Model chain</th><th className="text-right">Prompt</th><th className="text-right">Completion</th><th className="text-right">Corpus</th><th className="text-right">ms</th></tr></thead>
            <tbody>{(usage?.recent ?? []).map((r, i) => (
              <tr key={i}>
                <td className="muted whitespace-nowrap text-[12px]">{r.ts.slice(5, 16).replace("T", " ")}</td>
                <td className="font-medium">{r.purpose}</td>
                <td className="text-[12px]">
                  <span className="flex flex-wrap items-center gap-1">
                    {(r.attempts.length ? r.attempts : [{ model: r.model, outcome: r.outcome, ms: r.latency_ms }]).map((a, j) => (
                      <span key={j} className="flex items-center gap-1">
                        {j > 0 && <ArrowRight size={11} className="muted" />}
                        <span className="chip !py-0 !text-[11px]" style={{ color: a.outcome === "ok" ? "var(--ok)" : a.outcome === "cancelled" || a.outcome === "slow" ? "var(--muted)" : "var(--bad)" }}>
                          {short(a.model)} · {a.outcome}
                        </span>
                      </span>
                    ))}
                  </span>
                </td>
                <td className="text-right tabular-nums">{fmt(r.prompt_tokens)}</td><td className="text-right tabular-nums">{fmt(r.completion_tokens)}</td>
                <td className="text-right tabular-nums">{fmt(r.corpus_tokens)}</td><td className="text-right tabular-nums">{fmt(Math.round(r.latency_ms))}</td>
              </tr>
            ))}</tbody>
          </table>
          {usage && usage.recent.length === 0 && <p className="muted p-5 text-[13px]">No calls yet — ask the assistant something.</p>}
        </div>
      </div>

      <div className="card mt-5 p-5">
        <div className="mb-4 flex items-center gap-2"><Workflow size={16} style={{ color: "var(--accent)" }} /><h2 className="text-[15px] font-semibold">Request architecture</h2></div>
        <Architecture />
      </div>

      <div className="card mt-5 flex flex-wrap items-center gap-3 p-5">
        <Plug size={18} style={{ color: "var(--accent)" }} />
        <div className="min-w-0 flex-1">
          <div className="text-[14px] font-semibold">Bring your own MCP client</div>
          <div className="muted text-[12.5px]">Streamable HTTP at /mcp/ with a personal token — same permissions, audit and masking as the chat.</div>
        </div>
        <Link href="/settings#integrations" className="btn btn-primary">Set up MCP</Link>
      </div>
    </Page>
  );
}
