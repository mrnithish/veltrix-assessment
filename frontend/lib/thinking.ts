import type { AgentEvent, Resolution, Trace } from "./api";

export interface LlmAttempt {
  model: string;
  outcome: string;
  ms: number;
}

export interface EvidenceItem {
  doc_id: string;
  section: string;
  tokens?: number;
  upcoming?: boolean;
}

export type ThinkingStep =
  | { kind: "phase"; label: string; name: string }
  | { kind: "plan"; action: string; code?: string | null; reason?: string | null; attempt: number }
  | { kind: "call"; fn: string; args: Record<string, unknown>; summary?: string; ok?: boolean; ms?: number;
      pending: boolean }
  | { kind: "sandbox"; ok: boolean; error?: string | null; ms?: number; calls?: number }
  | { kind: "llm"; purpose: string; model: string; corpus_tokens: number; latency_ms: number;
      prompt_tokens?: number; completion_tokens?: number; attempts?: LlmAttempt[] }
  | { kind: "evidence"; items: EvidenceItem[]; corpus_tokens?: number; dropped?: number }
  | { kind: "resolution"; rules: Resolution[] }
  | { kind: "note"; text: string; tone?: "info" | "warn" | "bad" };

export interface ThinkingSummary {
  mode: string;
  provider?: string;
  model?: string;
  totalMs?: number;
  llmCalls: number;
  maxCorpusTokens: number;
  running: boolean;
  currentLabel?: string;
}

/** Live: fold stream events into display steps. */
export function stepsFromEvents(events: AgentEvent[]): { steps: ThinkingStep[]; summary: ThinkingSummary } {
  const steps: ThinkingStep[] = [];
  const summary: ThinkingSummary = { mode: "codemode", llmCalls: 0, maxCorpusTokens: 0, running: true };
  for (const e of events) {
    switch (e.type) {
      case "start":
        summary.mode = String(e.mode);
        summary.provider = String(e.provider);
        summary.model = String(e.model);
        break;
      case "phase":
        steps.push({ kind: "phase", label: String(e.label), name: String(e.name) });
        summary.currentLabel = String(e.label);
        break;
      case "plan":
        steps.push({ kind: "plan", action: String(e.action), code: e.code as string | null,
          reason: e.refuse_reason as string | null, attempt: Number(e.attempt ?? 0) });
        break;
      case "call":
        steps.push({ kind: "call", fn: String(e.fn), args: (e.args as Record<string, unknown>) ?? {}, pending: true });
        break;
      case "call_done": {
        const idx = findLastIndex(steps, (s) => s.kind === "call" && s.fn === e.fn && s.pending);
        const done = { summary: String(e.summary ?? ""), ok: Boolean(e.ok), ms: Number(e.ms ?? 0), pending: false };
        if (idx >= 0) steps[idx] = { ...(steps[idx] as Extract<ThinkingStep, { kind: "call" }>), ...done };
        else steps.push({ kind: "call", fn: String(e.fn), args: {}, ...done });
        break;
      }
      case "sandbox":
        steps.push({ kind: "sandbox", ok: Boolean(e.ok), error: e.error as string | null, ms: Number(e.ms ?? 0),
          calls: Number(e.calls ?? 0) });
        break;
      case "llm":
        summary.llmCalls += 1;
        summary.maxCorpusTokens = Math.max(summary.maxCorpusTokens, Number(e.corpus_tokens ?? 0));
        steps.push({ kind: "llm", purpose: String(e.purpose), model: String(e.model),
          corpus_tokens: Number(e.corpus_tokens ?? 0), latency_ms: Number(e.latency_ms ?? 0),
          prompt_tokens: Number(e.prompt_tokens ?? 0), completion_tokens: Number(e.completion_tokens ?? 0),
          attempts: (e.attempts as LlmAttempt[]) ?? [] });
        break;
      case "evidence":
        steps.push({ kind: "evidence", items: (e.items as EvidenceItem[]) ?? [],
          corpus_tokens: Number(e.corpus_tokens ?? 0), dropped: Number(e.dropped ?? 0) });
        break;
      case "resolution":
        steps.push({ kind: "resolution", rules: (e.rules as Resolution[]) ?? [] });
        break;
      case "note":
        steps.push({ kind: "note", text: String(e.text) });
        break;
      case "final":
        summary.running = false;
        summary.totalMs = Number(e.total_ms ?? e.t_ms ?? 0);
        summary.currentLabel = undefined;
        break;
    }
  }
  return { steps, summary };
}

/** History: rebuild the same steps from a stored trace (GET /traces/{id}). */
export function stepsFromTrace(t: Trace): { steps: ThinkingStep[]; summary: ThinkingSummary } {
  const steps: ThinkingStep[] = [];
  const llm = t.llm_calls ?? [];
  const pushLlm = (purpose: string) => {
    for (const c of llm.filter((x) => x.purpose === purpose)) {
      steps.push({ kind: "llm", purpose: c.purpose, model: c.model, corpus_tokens: c.corpus_tokens,
        latency_ms: c.latency_ms, prompt_tokens: c.prompt_tokens, completion_tokens: c.completion_tokens,
        attempts: (c as { attempts?: LlmAttempt[] }).attempts ?? [] });
    }
  };
  if (t.pending_proposal) {
    steps.push({ kind: "note", text: t.pending_proposal.confirmed
      ? `Confirmed the pending ${t.pending_proposal.name} proposal and executed it.`
      : `Previous ${t.pending_proposal.name} proposal discarded (not a confirmation).` });
  }
  pushLlm("plan");
  pushLlm("plan_tools");
  const execs = (t.steps ?? []).filter((s) => s.name === "codemode.execute");
  const records = [...(t.all_tool_records ?? [])];
  [t.plan_0, t.plan_1].forEach((p, i) => {
    if (!p) return;
    steps.push({ kind: "plan", action: p.action, code: p.code ?? null, reason: p.refuse_reason ?? null, attempt: i });
    const ex = execs[i];
    if (!ex) return;
    for (const c of (ex.calls as { fn: string; kwargs: Record<string, unknown> }[]) ?? []) {
      const recIdx = records.findIndex((r) => r.name === c.fn);
      const rec = recIdx >= 0 ? records.splice(recIdx, 1)[0] : undefined;
      steps.push({ kind: "call", fn: c.fn, args: c.kwargs, pending: false, ok: rec ? rec.status !== "error" : true,
        summary: rec ? `${rec.status.replaceAll("_", " ")}${rec.error_kind ? ` (${rec.error_kind})` : ""}` : undefined });
    }
    steps.push({ kind: "sandbox", ok: Boolean(ex.ok), error: (ex.error as string) ?? null,
      ms: Number(ex.sandbox_ms ?? ex.duration_ms ?? 0), calls: ((ex.calls as unknown[]) ?? []).length });
  });
  const pack = (t.steps ?? []).find((s) => s.name === "budget.pack");
  if (t.searches?.length) {
    const items = (pack?.items as { chunk: string; tokens: number }[] | undefined)?.map((i) => ({
      doc_id: i.chunk.split("#")[0], section: `chunk ${i.chunk.split("#")[1]}`, tokens: i.tokens,
    })) ?? t.searches.flatMap((s) => s.hits.map((h) => ({ doc_id: h.split("#")[0], section: `chunk ${h.split("#")[1]}` })));
    steps.push({ kind: "evidence", items, corpus_tokens: Number(pack?.corpus_tokens ?? 0),
      dropped: ((pack?.dropped as unknown[]) ?? []).length });
  }
  pushLlm("extract");
  if (t.ungrounded_candidates?.length) {
    steps.push({ kind: "note", tone: "warn", text: `Dropped ${t.ungrounded_candidates.length} extracted value(s) not `
      + "supported by their passage." });
  }
  if (t.resolutions?.length) steps.push({ kind: "resolution", rules: t.resolutions });
  for (const g of [t.leave_type_guard, t.leave_action_guard]) if (g) steps.push({ kind: "note", text: g });
  pushLlm("compose");
  if (t.error) steps.push({ kind: "note", tone: "bad", text: t.error });
  return {
    steps,
    summary: {
      mode: t.agent_mode, provider: t.llm?.provider, model: t.llm?.model, totalMs: t.total_ms,
      llmCalls: llm.length, maxCorpusTokens: Math.max(0, ...llm.map((c) => c.corpus_tokens)), running: false,
    },
  };
}

function findLastIndex<T>(arr: T[], pred: (x: T) => boolean): number {
  for (let i = arr.length - 1; i >= 0; i -= 1) if (pred(arr[i])) return i;
  return -1;
}
