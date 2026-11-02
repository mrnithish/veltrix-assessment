"use client";

import {
  AlertTriangle, BrainCircuit, ChevronDown, CircleDot, Code2, Cpu, FileSearch, Info, Loader2, Scale, ShieldCheck,
  ShieldX, Terminal,
} from "lucide-react";
import { useEffect, useState } from "react";
import type { ThinkingStep, ThinkingSummary } from "@/lib/thinking";
import { CodeBlock } from "./CodeBlock";

const BUDGET = 3000;

function shortModel(model?: string) {
  return model ? model.split("/").pop() : "";
}

function argText(args: Record<string, unknown>) {
  return Object.entries(args).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(", ");
}

function Row({ icon: Icon, tone, children, spin }: {
  icon: typeof CircleDot; tone?: string; children: React.ReactNode; spin?: boolean;
}) {
  return (
    <li className="fade-up relative flex gap-3 pb-3 last:pb-0">
      <span className="relative z-10 mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full border"
        style={{ background: "var(--panel)", borderColor: "var(--border)", color: tone ?? "var(--muted)" }}>
        <Icon size={13} className={spin ? "animate-spin" : undefined} />
      </span>
      <div className="min-w-0 flex-1 pt-0.5 text-[13px]">{children}</div>
    </li>
  );
}

function Step({ step }: { step: ThinkingStep }) {
  switch (step.kind) {
    case "phase":
      return <Row icon={CircleDot} tone="var(--accent)"><span className="font-medium">{step.label}</span></Row>;
    case "plan":
      return (
        <Row icon={Code2} tone="var(--accent)">
          <div className="mb-1.5 font-medium">
            {step.action === "code" ? "Wrote a program (Code Mode)"
              : step.action === "refuse" ? `Decided to decline${step.reason ? ` — ${step.reason.replaceAll("_", " ")}` : ""}`
                : step.action === "clarify" ? "Decided to ask for more details"
                  : step.action === "respond" ? "Short reply" : `Plan: ${step.action}`}
            {step.attempt > 0 && <span className="muted ml-1.5 font-normal">(retry {step.attempt})</span>}
          </div>
          {step.code && <CodeBlock code={step.code} title="agent_code.py · runs in sandbox" />}
        </Row>
      );
    case "call":
      return (
        <Row icon={step.pending ? Loader2 : Terminal} spin={step.pending}
          tone={step.pending ? "var(--accent)" : step.ok === false ? "var(--bad)" : "var(--ok)"}>
          <div className="truncate font-mono text-[12.5px]">
            <span style={{ color: "var(--accent-text)" }}>{step.fn}</span>
            <span className="muted">({argText(step.args)})</span>
          </div>
          {step.summary && (
            <div className="mt-0.5 text-[12.5px]" style={{ color: step.ok === false ? "var(--bad)" : "var(--text-2)" }}>
              → {step.summary}{step.ms ? <span className="muted"> · {step.ms} ms</span> : null}
            </div>
          )}
        </Row>
      );
    case "sandbox":
      return (
        <Row icon={step.ok ? ShieldCheck : ShieldX} tone={step.ok ? "var(--ok)" : "var(--bad)"}>
          {step.ok
            ? <span>Sandbox finished · {step.calls} call{step.calls === 1 ? "" : "s"} · {step.ms} ms
              <span className="muted"> · isolated process, no DB/network/secrets</span></span>
            : <span style={{ color: "var(--bad)" }}>Sandbox rejected/failed: {step.error}</span>}
        </Row>
      );
    case "llm":
      return (
        <Row icon={Cpu}>
          <span className="muted">
            Model call <span className="font-medium" style={{ color: "var(--text-2)" }}>{step.purpose}</span>
            {" · "}{shortModel(step.model)} · {(step.latency_ms / 1000).toFixed(1)} s · corpus{" "}
            <span style={{ color: step.corpus_tokens > BUDGET ? "var(--bad)" : "var(--ok)" }}>
              {step.corpus_tokens}/{BUDGET}
            </span> tokens · {(step.prompt_tokens ?? 0) + (step.completion_tokens ?? 0)} used
          </span>
          {step.attempts && step.attempts.length > 1 && (
            <div className="mt-1 flex flex-wrap items-center gap-1 text-[11.5px]">
              <span className="muted">fallback:</span>
              {step.attempts.map((a, i) => (
                <span key={i} className="chip !py-0 !text-[11px]"
                  style={{ color: a.outcome === "ok" ? "var(--ok)" : a.outcome === "slow" || a.outcome === "cancelled" ? "var(--muted)" : "var(--bad)" }}>
                  {shortModel(a.model)} · {a.outcome} · {a.ms} ms
                </span>
              ))}
            </div>
          )}
        </Row>
      );
    case "evidence":
      return (
        <Row icon={FileSearch} tone="var(--info)">
          <div className="mb-1.5">
            Read {step.items.length} passage{step.items.length === 1 ? "" : "s"} you are allowed to see
            {typeof step.corpus_tokens === "number" && step.corpus_tokens > 0 &&
              <span className="muted"> · {step.corpus_tokens.toLocaleString()} / {BUDGET.toLocaleString()} tokens</span>}
            {step.dropped ? <span className="muted"> · {step.dropped} dropped for budget</span> : null}
          </div>
          <div className="flex flex-wrap gap-1.5">
            {step.items.map((it, i) => (
              <span key={i} className="chip !text-[11.5px]" style={it.upcoming ? { color: "var(--warn)" } : undefined}>
                <span className="font-mono">{it.doc_id}</span>
                <span className="muted max-w-[180px] truncate">{it.section}</span>
                {it.upcoming && <span>· upcoming</span>}
              </span>
            ))}
          </div>
        </Row>
      );
    case "resolution":
      return (
        <Row icon={Scale} tone="var(--accent)">
          <div className="mb-1.5 font-medium">Applied precedence (authority → scope → recency)</div>
          <div className="space-y-2">
            {step.rules.map((r, i) => (
              <div key={i} className="rounded-lg border p-2.5" style={{ borderColor: "var(--border)", background: "var(--panel-2)" }}>
                <div className="flex items-center gap-2">
                  <span className="font-medium">{r.rule}</span>
                  {r.status === "conflict" && <span className="badge" style={{ color: "var(--warn)", background: "var(--warn-soft)" }}>conflict</span>}
                </div>
                {r.winners.map(([doc, val]) => (
                  <div key={doc + val} className="mt-1 text-[12.5px]">
                    <span style={{ color: "var(--ok)" }}>✓</span> <span className="font-mono">{doc}</span>: {val}
                  </div>
                ))}
                {r.overruled.map(([doc, val, why]) => (
                  <div key={doc + val} className="muted mt-0.5 text-[12.5px]">
                    <span className="line-through"><span className="font-mono">{doc}</span>: {val}</span>
                    <span> — lost on {why}</span>
                  </div>
                ))}
                {r.upcoming && (
                  <div className="mt-1 text-[12.5px]" style={{ color: "var(--warn)" }}>
                    ↗ from {r.upcoming[2]}: <span className="font-mono">{r.upcoming[0]}</span> — {r.upcoming[1]}
                  </div>
                )}
              </div>
            ))}
          </div>
        </Row>
      );
    case "note":
      return (
        <Row icon={step.tone === "bad" || step.tone === "warn" ? AlertTriangle : Info}
          tone={step.tone === "bad" ? "var(--bad)" : step.tone === "warn" ? "var(--warn)" : "var(--info)"}>
          <span style={{ color: "var(--text-2)" }}>{step.text}</span>
        </Row>
      );
  }
}

export function ThinkingBlock({ steps, summary, defaultOpen, loading }: {
  steps: ThinkingStep[]; summary: ThinkingSummary | null; defaultOpen: boolean; loading?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const running = summary?.running ?? false;
  useEffect(() => {
    if (running) setOpen(true);
  }, [running]);
  useEffect(() => {
    if (summary && !summary.running) setOpen(defaultOpen);
    // collapse once the answer is in (if the user prefers)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [summary?.running]);

  const label = running
    ? summary?.currentLabel ?? "Thinking"
    : summary?.totalMs ? `Thought for ${(summary.totalMs / 1000).toFixed(1)} s` : "How this answer was made";

  return (
    <div className="mb-3 overflow-hidden rounded-xl border" style={{ borderColor: "var(--border)", background: "var(--panel-2)" }}>
      <button className="flex w-full items-center gap-2.5 px-3.5 py-2.5 text-left" onClick={() => setOpen((o) => !o)}
        aria-expanded={open}>
        <BrainCircuit size={16} style={{ color: "var(--accent)" }} />
        <span className="whitespace-nowrap text-[13px] font-medium">{label}</span>
        {running && <span className="ml-0.5 flex gap-1"><span className="dot" /><span className="dot" style={{ animationDelay: "0.15s" }} /><span className="dot" style={{ animationDelay: "0.3s" }} /></span>}
        {summary && !running && (
          <span className="ml-1 hidden flex-wrap gap-1.5 sm:flex">
            <span className="chip !py-0 !text-[11px]">{summary.mode === "tools" ? "Tool calling" : "Code Mode"}</span>
            {summary.model && <span className="chip !py-0 !text-[11px]">{shortModel(summary.model)}</span>}
            <span className="chip !py-0 !text-[11px]">{summary.llmCalls} model call{summary.llmCalls === 1 ? "" : "s"}</span>
            {summary.maxCorpusTokens > 0 && <span className="chip !py-0 !text-[11px]">≤ {summary.maxCorpusTokens} corpus tokens</span>}
          </span>
        )}
        <ChevronDown size={16} className="muted ml-auto transition-transform" style={{ transform: open ? "rotate(180deg)" : "none" }} />
      </button>
      {open && (
        <div className="border-t px-3.5 py-3" style={{ borderColor: "var(--border)" }}>
          {loading && <div className="space-y-2"><div className="skeleton h-5 w-2/3" /><div className="skeleton h-20" /></div>}
          {!loading && steps.length === 0 && <div className="muted text-[13px]">Starting…</div>}
          <ol className="relative">
            <span className="absolute bottom-3 left-3 top-3 w-px" style={{ background: "var(--border)" }} />
            {steps.map((s, i) => <Step key={i} step={s} />)}
          </ol>
        </div>
      )}
    </div>
  );
}
