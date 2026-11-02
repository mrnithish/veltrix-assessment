"use client";

import {
  Activity, Bot, Check, CheckCircle2, Copy, Cpu, ExternalLink, FlaskConical, KeyRound, Loader2, Monitor, Moon, Plug,
  RefreshCw, RotateCcw, Search, SlidersHorizontal, Sun, XCircle,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ErrorNote, Page, PageHeader, Toggle, formatDate } from "@/components/ui";
import { API_URL, api, type CatalogModel, type LlmSelection, type McpTokenInfo, type ModelProbe } from "@/lib/api";
import { useAppData } from "@/lib/app-data";
import { useAuth } from "@/lib/auth";
import { usePrefs, type Theme } from "@/lib/prefs";

type Tab = "general" | "model" | "integrations" | "about";
const TABS: { id: Tab; label: string; icon: typeof Bot }[] = [
  { id: "general", label: "General", icon: SlidersHorizontal },
  { id: "model", label: "Model & agent", icon: Cpu },
  { id: "integrations", label: "Integrations (MCP)", icon: Plug },
  { id: "about", label: "About & system", icon: Activity },
];

function Card({ title, description, children }: { title: string; description?: string; children: React.ReactNode }) {
  return (
    <section className="card p-6">
      <h2 className="text-[15px] font-semibold">{title}</h2>
      {description && <p className="muted mt-1 text-[12.5px]">{description}</p>}
      <div className="mt-4">{children}</div>
    </section>
  );
}

function CopyButton({ text, label = "Copy" }: { text: string; label?: string }) {
  const [done, setDone] = useState(false);
  return (
    <button className="btn !py-1 !text-[12px]" onClick={() => {
      navigator.clipboard?.writeText(text);
      setDone(true);
      setTimeout(() => setDone(false), 1200);
    }}>{done ? <Check size={13} /> : <Copy size={13} />} {done ? "Copied" : label}</button>
  );
}

// ---------------------------------------------------------------------------------------------- general
function GeneralTab() {
  const { prefs, update } = usePrefs();
  const themes: { id: Theme; label: string; icon: typeof Sun }[] = [
    { id: "system", label: "System", icon: Monitor }, { id: "light", label: "Light", icon: Sun }, { id: "dark", label: "Dark", icon: Moon },
  ];
  return (
    <div className="space-y-5">
      <Card title="Assistant" description="How answers are shown in the chat.">
        <div className="divide-y divide-[var(--border)]">
          <Toggle checked={prefs.streaming} onChange={(v) => update({ streaming: v })} label="Live thinking"
            description="Stream each step (plan, Code Mode program, tool calls, retrieval, precedence, model fallbacks) while the answer is prepared." />
          <Toggle checked={prefs.thinkingExpanded} onChange={(v) => update({ thinkingExpanded: v })} label="Keep thinking expanded"
            description="Leave the thinking panel open after the answer arrives." />
          <Toggle checked={prefs.showRouteBadges} onChange={(v) => update({ showRouteBadges: v })} label="Show answer type"
            description="Label answers as Documents, Leave data, Needs details, Not covered or Declined." />
        </div>
      </Card>
      <Card title="Appearance" description="Light, dark, or follow your system.">
        <div className="grid grid-cols-3 gap-2">
          {themes.map((t) => (
            <button key={t.id} onClick={() => update({ theme: t.id })} className="flex flex-col items-center gap-2 rounded-xl border p-4"
              style={{ borderColor: prefs.theme === t.id ? "var(--accent)" : "var(--border)", background: prefs.theme === t.id ? "var(--accent-soft)" : "var(--panel)" }}>
              <t.icon size={18} /> <span className="text-[13px] font-medium">{t.label}</span>
            </button>
          ))}
        </div>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------------------------------------- model
function ModelTab() {
  const { refreshInfo } = useAppData();
  const [sel, setSel] = useState<LlmSelection | null>(null);
  const [provider, setProvider] = useState("");
  const [model, setModel] = useState("");
  const [mode, setMode] = useState("codemode");
  const [catalog, setCatalog] = useState<CatalogModel[]>([]);
  const [catalogInfo, setCatalogInfo] = useState<{ live: number; error: string | null } | null>(null);
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [query, setQuery] = useState("");
  const [probe, setProbe] = useState<ModelProbe | null>(null);
  const [probing, setProbing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.llm().then((s) => { setSel(s); setProvider(s.provider); setModel(s.model); setMode(s.agent_mode); })
      .catch((e) => setError(e.message));
  }, []);

  const loadCatalog = useCallback((p: string, refresh = false) => {
    if (!p) return;
    setCatalogLoading(true);
    api.models(p, refresh).then((c) => { setCatalog(c.models); setCatalogInfo({ live: c.live_count, error: c.error }); })
      .catch(() => setCatalog([])).finally(() => setCatalogLoading(false));
  }, []);
  useEffect(() => loadCatalog(provider), [provider, loadCatalog]);

  const shown = useMemo(() => catalog.filter((m) => m.id.toLowerCase().includes(query.toLowerCase())), [catalog, query]);
  const current = sel?.providers.find((p) => p.provider === provider);

  const apply = async (body: Parameters<typeof api.setLlm>[0]) => {
    setSaving(true); setError(null); setSaved(false);
    try {
      const s = await api.setLlm(body);
      setSel(s); setProvider(s.provider); setModel(s.model); setMode(s.agent_mode);
      setSaved(true); refreshInfo();
      setTimeout(() => setSaved(false), 2000);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  const test = async () => {
    setProbing(true); setProbe(null);
    try {
      setProbe(await api.testModel(provider, model));
    } catch (e) {
      setProbe({ ok: false, provider, model, latency_ms: 0, error: e instanceof Error ? e.message : String(e) });
    } finally {
      setProbing(false);
    }
  };

  return (
    <div className="space-y-5">
      <Card title="Model" description="Applies to new messages for everyone on this server until restart. Failures and slow replies fall back to backup models automatically.">
        {error && <div className="mb-3"><ErrorNote message={error} /></div>}
        <div className="grid gap-4 sm:grid-cols-[220px_1fr]">
          <div>
            <label className="label" htmlFor="prov">Provider</label>
            <select id="prov" className="input" value={provider} onChange={(e) => {
              const p = sel?.providers.find((x) => x.provider === e.target.value);
              setProvider(e.target.value); setModel(p?.default_model ?? ""); setProbe(null);
            }}>
              {sel?.providers.map((p) => (
                <option key={p.provider} value={p.provider} disabled={!p.configured}>{p.label}{p.configured ? "" : ` — set ${p.key_env}`}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="label" htmlFor="model">Model id</label>
            <div className="flex gap-2">
              <input id="model" className="input font-mono !text-[13px]" value={model} placeholder={current?.default_model}
                onChange={(e) => { setModel(e.target.value); setProbe(null); }} />
              <button className="btn shrink-0" onClick={test} disabled={probing || !model} title="Send one tiny request to this exact model">
                {probing ? <Loader2 size={14} className="animate-spin" /> : <FlaskConical size={14} />} Test
              </button>
            </div>
            {probe && (
              <div className="mt-2 flex items-center gap-2 text-[12.5px]" style={{ color: probe.ok ? "var(--ok)" : "var(--bad)" }}>
                {probe.ok ? <CheckCircle2 size={14} /> : <XCircle size={14} />}
                {probe.ok ? `Available · answered in ${(probe.latency_ms / 1000).toFixed(1)} s` : probe.error}
              </div>
            )}
          </div>
        </div>

        <div className="mt-5 overflow-hidden rounded-xl border" style={{ borderColor: "var(--border)" }}>
          <div className="flex flex-wrap items-center gap-2 border-b px-3 py-2" style={{ borderColor: "var(--border)", background: "var(--panel-2)" }}>
            <span className="text-[13px] font-semibold">Catalog</span>
            <span className="muted text-[12px]">
              {catalogInfo ? `${catalog.length} models · ${catalogInfo.live} listed live by ${current?.label ?? provider}` : ""}
              {catalogInfo?.error ? " · live list unavailable" : ""}
            </span>
            <div className="relative ml-auto">
              <Search size={13} className="muted absolute left-2.5 top-1/2 -translate-y-1/2" />
              <input className="input !w-[200px] !py-1 !pl-7 !text-[12.5px]" placeholder="Filter models" value={query} onChange={(e) => setQuery(e.target.value)} />
            </div>
            <button className="btn !p-1.5" title="Refresh from provider" onClick={() => loadCatalog(provider, true)}>
              <RefreshCw size={13} className={catalogLoading ? "animate-spin" : undefined} />
            </button>
          </div>
          <div className="scroll-thin max-h-[280px] overflow-y-auto">
            {shown.map((m) => (
              <button key={m.id} onClick={() => { setModel(m.id); setProbe(null); }}
                className="flex w-full items-center gap-2 border-b px-3 py-2 text-left text-[12.5px] last:border-b-0 hover:bg-[var(--panel-2)]"
                style={{ borderColor: "var(--border)", background: model === m.id ? "var(--accent-soft)" : undefined }}>
                <span className="font-mono">{m.id}</span>
                {m.default && <span className="badge" style={{ color: "var(--accent-text)", background: "var(--accent-soft)" }}>default</span>}
                {m.listed_by_provider ? <span className="badge" style={{ color: "var(--ok)", background: "var(--ok-soft)" }}>live</span>
                  : <span className="badge" style={{ color: "var(--muted)", background: "var(--panel-2)" }}>not listed</span>}
                {m.note && <span className="muted ml-auto truncate pl-2 text-[11.5px]">{m.note}</span>}
              </button>
            ))}
            {!catalogLoading && shown.length === 0 && <div className="muted p-4 text-[12.5px]">No models match.</div>}
          </div>
        </div>
      </Card>

      <Card title="Agent mode" description="How the assistant plans its tool calls.">
        <div className="grid gap-2 sm:grid-cols-2">
          {[
            { id: "codemode", title: "Code Mode", body: "The model writes one Python program that calls the tools in an isolated sandbox. Fewer round trips; chained logic." },
            { id: "tools", title: "Tool calling", body: "Classic function calling, one tool at a time. Same tools, permissions and checks." },
          ].map((m) => (
            <button key={m.id} onClick={() => setMode(m.id)} className="rounded-xl border p-3.5 text-left transition-colors"
              style={{ borderColor: mode === m.id ? "var(--accent)" : "var(--border)", background: mode === m.id ? "var(--accent-soft)" : "var(--panel)" }}>
              <div className="text-[13.5px] font-semibold">{m.title}</div>
              <div className="muted mt-0.5 text-[12px]">{m.body}</div>
            </button>
          ))}
        </div>
        <div className="mt-5 flex flex-wrap items-center gap-2">
          <button className="btn btn-primary" disabled={saving || !provider} onClick={() => apply({ provider, model, agent_mode: mode })}>
            {saving ? "Applying…" : "Apply model & mode"}
          </button>
          <button className="btn" disabled={saving} onClick={() => apply({ reset: true })}><RotateCcw size={14} /> Reset to server defaults</button>
          {saved && <span className="flex items-center gap-1 text-[13px]" style={{ color: "var(--ok)" }}><CheckCircle2 size={15} /> Saved</span>}
        </div>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------------------------------------- MCP
function IntegrationsTab() {
  const [info, setInfo] = useState<McpTokenInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [client, setClient] = useState<"claude_code" | "cursor" | "vscode" | "claude_desktop">("claude_code");
  const url = `${API_URL}/mcp/`;

  const generate = async () => {
    setLoading(true); setError(null);
    try { setInfo(await api.mcpToken()); } catch (e) { setError(e instanceof Error ? e.message : String(e)); } finally { setLoading(false); }
  };
  const snippet = info ? (typeof info.configs[client] === "string" ? info.configs[client] as string
    : JSON.stringify(info.configs[client], null, 2)) : "";
  const where: Record<string, string> = {
    claude_code: "Run in a terminal", cursor: "~/.cursor/mcp.json", vscode: ".vscode/mcp.json", claude_desktop: "claude_desktop_config.json",
  };

  return (
    <div className="space-y-5">
      <Card title="Use this API from your own MCP client" description="The server exposes a Model Context Protocol endpoint. Connect Claude Code, Cursor, VS Code, Claude Desktop or your own agent. Every call runs as you, with the same permission checks, audit log and PII masking as the chat.">
        <div className="grid gap-3 sm:grid-cols-[140px_1fr] sm:items-center">
          <span className="muted text-[13px]">Endpoint</span>
          <div className="flex items-center gap-2"><code className="chip !rounded-lg !py-1 font-mono">{url}</code><CopyButton text={url} /></div>
          <span className="muted text-[13px]">Transport</span><span className="text-[13px]">Streamable HTTP · Bearer token</span>
          <span className="muted text-[13px]">Tools</span>
          <div className="flex flex-wrap gap-1.5">
            {["whoami", "ask_hr_assistant", "get_leave_balance", "list_leave_requests", "get_team_leave", "list_holidays", "list_documents", "search_hr_documents"]
              .map((t) => <span key={t} className="chip font-mono !text-[11.5px]">{t}</span>)}
          </div>
        </div>
      </Card>

      <Card title="Personal access token" description="Valid for 30 days. Anyone with this token can act as you through MCP — keep it private.">
        {error && <div className="mb-3"><ErrorNote message={error} /></div>}
        {!info ? (
          <button className="btn btn-primary" onClick={generate} disabled={loading}>
            {loading ? <Loader2 size={15} className="animate-spin" /> : <KeyRound size={15} />} Generate token
          </button>
        ) : (
          <>
            <div className="flex items-center gap-2">
              <code className="scroll-thin block flex-1 overflow-x-auto rounded-lg px-3 py-2 font-mono text-[12px]" style={{ background: "var(--panel-2)" }}>{info.token}</code>
              <CopyButton text={info.token} />
            </div>
            <div className="mt-5 flex flex-wrap gap-1 rounded-lg p-1" style={{ background: "var(--panel-2)" }}>
              {(["claude_code", "cursor", "vscode", "claude_desktop"] as const).map((c) => (
                <button key={c} onClick={() => setClient(c)} className="rounded-md px-3 py-1 text-[12.5px]"
                  style={{ background: client === c ? "var(--panel)" : "transparent", fontWeight: client === c ? 600 : 500 }}>
                  {{ claude_code: "Claude Code", cursor: "Cursor", vscode: "VS Code", claude_desktop: "Claude Desktop" }[c]}
                </button>
              ))}
            </div>
            <div className="mt-3 flex items-center justify-between">
              <span className="muted text-[12px]">{where[client]}</span><CopyButton text={snippet} />
            </div>
            <pre className="code mt-2">{snippet}</pre>
          </>
        )}
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------------------------------------- about
function AboutTab() {
  const { profile } = useAuth();
  const { info } = useAppData();
  return (
    <Card title="System" description="Service status and observability links.">
      <dl className="grid grid-cols-[150px_1fr] gap-y-2.5 text-[13.5px]">
        <dt className="muted">Status</dt><dd>{info?.ready ? <span style={{ color: "var(--ok)" }}>● ready</span> : "starting…"}</dd>
        <dt className="muted">Assistant date</dt><dd>{profile ? `${formatDate(profile.today)} · ${profile.timezone ?? ""}` : "—"}</dd>
        <dt className="muted">Model</dt><dd className="font-mono text-[12.5px]">{info ? `${info.llm_provider} · ${info.llm_model} · ${info.agent_mode}` : "—"}</dd>
        <dt className="muted">Ingestion</dt>
        <dd>{info?.ingestion ? `${info.ingestion.documents} documents · ${info.ingestion.chunks} chunks · ${info.ingestion.holiday_records} holiday dates · ${info.ingestion.seconds}s` : "—"}</dd>
        <dt className="muted">API</dt><dd className="font-mono text-[12.5px]">{API_URL}</dd>
      </dl>
      <div className="mt-4 flex flex-wrap gap-2">
        <Link className="btn !text-[12.5px]" href="/system"><Activity size={13} /> Architecture & token usage</Link>
        {info?.phoenix_url && <a className="btn !text-[12.5px]" href={info.phoenix_url} target="_blank" rel="noreferrer"><ExternalLink size={13} /> Phoenix traces</a>}
        <a className="btn !text-[12.5px]" href={`${API_URL}/metrics`} target="_blank" rel="noreferrer"><ExternalLink size={13} /> Prometheus metrics</a>
        <a className="btn !text-[12.5px]" href={`${API_URL}/docs`} target="_blank" rel="noreferrer"><ExternalLink size={13} /> API docs</a>
      </div>
    </Card>
  );
}

export default function SettingsPage() {
  const [tab, setTab] = useState<Tab>("general");
  useEffect(() => {
    const sync = () => {
      const h = window.location.hash.slice(1) as Tab;
      if (TABS.some((t) => t.id === h)) setTab(h);
    };
    sync();
    window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, []);
  return (
    <Page wide>
      <PageHeader title="Settings" subtitle="Assistant behaviour, model, integrations and appearance." />
      <div className="grid gap-6 lg:grid-cols-[220px_1fr]">
        <nav className="flex gap-1 overflow-x-auto lg:flex-col">
          {TABS.map((t) => (
            <button key={t.id} onClick={() => { setTab(t.id); history.replaceState(null, "", `#${t.id}`); }}
              className="flex shrink-0 items-center gap-2.5 rounded-lg px-3 py-2 text-left text-[13.5px]"
              style={{ background: tab === t.id ? "var(--panel-3)" : undefined, fontWeight: tab === t.id ? 600 : 500 }}>
              <t.icon size={16} style={{ color: tab === t.id ? "var(--accent)" : "var(--muted)" }} /> {t.label}
            </button>
          ))}
        </nav>
        <div className="min-w-0">
          {tab === "general" && <GeneralTab />}
          {tab === "model" && <ModelTab />}
          {tab === "integrations" && <IntegrationsTab />}
          {tab === "about" && <AboutTab />}
        </div>
      </div>
    </Page>
  );
}
