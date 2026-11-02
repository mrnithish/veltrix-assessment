"use client";

import { ArrowRight, BrainCircuit, FileCheck2, Loader2, LockKeyhole, ScanSearch } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { RoleBadge } from "@/components/Badges";
import { api, type DemoAccount } from "@/lib/api";
import { useAuth } from "@/lib/auth";

const FEATURES = [
  { icon: FileCheck2, title: "Grounded answers", body: "Only the HR documents that apply to your role, region and date — every answer cites its source." },
  { icon: BrainCircuit, title: "Code Mode agent", body: "The assistant writes a small program that calls permission-checked tools in a sandbox." },
  { icon: ScanSearch, title: "Fully traceable", body: "See each step live: plan, code, tool calls, retrieval, precedence and token budget." },
];

export default function LoginPage() {
  const { login, token, ready } = useAuth();
  const router = useRouter();
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [accounts, setAccounts] = useState<DemoAccount[]>([]);
  const [filter, setFilter] = useState<"all" | "employee" | "manager" | "hr">("all");
  const [apiDown, setApiDown] = useState(false);

  useEffect(() => {
    if (ready && token) router.replace("/chat");
  }, [ready, token, router]);

  useEffect(() => {
    api.demoAccounts().then(setAccounts).catch(() => setApiDown(true));
  }, []);

  const shown = useMemo(() => accounts.filter((a) => filter === "all" || a.role === filter), [accounts, filter]);

  const submit = async (e?: React.FormEvent) => {
    e?.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login(identifier, password);
      router.replace("/chat");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="grid min-h-dvh lg:grid-cols-[1.05fr_1fr]">
      <section className="relative hidden overflow-hidden p-12 text-white lg:flex lg:flex-col"
        style={{ background: "radial-gradient(1200px 600px at -10% -10%, #6366f1 0%, transparent 60%), radial-gradient(900px 600px at 120% 110%, #8b5cf6 0%, transparent 55%), #0f1222" }}>
        <div className="flex items-center gap-2.5">
          <div className="grid h-9 w-9 place-items-center rounded-xl bg-white/15 text-[15px] font-bold backdrop-blur">V</div>
          <span className="text-[15px] font-semibold">Veltrix PeopleOps</span>
        </div>
        <div className="mt-auto max-w-lg">
          <h1 className="text-[40px] font-semibold leading-[1.1] tracking-tight">Your HR questions, answered with sources.</h1>
          <p className="mt-4 text-[15px] text-white/75">
            Policies, holidays, benefits and your leave — in one assistant that applies the right document for your office
            and never changes anything without your confirmation.
          </p>
          <div className="mt-10 space-y-5">
            {FEATURES.map((f) => (
              <div key={f.title} className="flex gap-3.5">
                <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-white/10"><f.icon size={18} /></span>
                <div>
                  <div className="text-[14px] font-semibold">{f.title}</div>
                  <div className="text-[13px] text-white/70">{f.body}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
        <div className="mt-12 text-[12px] text-white/50">Veltrix Systems · internal tool · demo environment</div>
      </section>

      <section className="flex items-center justify-center p-6 sm:p-10">
        <div className="w-full max-w-[420px]">
          <div className="mb-8 lg:hidden">
            <div className="grid h-10 w-10 place-items-center rounded-xl text-[16px] font-bold text-white"
              style={{ background: "linear-gradient(135deg, var(--accent), #8b5cf6)" }}>V</div>
          </div>
          <h2 className="text-[24px] font-semibold tracking-tight">Sign in</h2>
          <p className="muted mt-1 text-[14px]">Use your employee ID or work email.</p>

          <form onSubmit={submit} className="mt-7 space-y-4">
            <div>
              <label className="label" htmlFor="ident">Employee ID or email</label>
              <input id="ident" className="input" autoComplete="username" placeholder="e.g. E2004" value={identifier}
                onChange={(e) => setIdentifier(e.target.value)} autoFocus />
            </div>
            <div>
              <label className="label" htmlFor="pw">Password</label>
              <input id="pw" type="password" className="input" autoComplete="current-password" value={password}
                onChange={(e) => setPassword(e.target.value)} />
              <p className="muted mt-1.5 flex items-center gap-1.5 text-[12px]">
                <LockKeyhole size={12} /> Demo environment: the password is <code className="font-mono">veltrix</code>
              </p>
            </div>
            {error && (
              <div className="rounded-lg px-3 py-2 text-[13px]" style={{ background: "var(--bad-soft)", color: "var(--bad)" }}>{error}</div>
            )}
            {apiDown && (
              <div className="rounded-lg px-3 py-2 text-[13px]" style={{ background: "var(--warn-soft)", color: "var(--warn)" }}>
                The API is not reachable yet. If it just started, ingestion may still be running.
              </div>
            )}
            <button type="submit" className="btn btn-primary w-full !py-2.5" disabled={loading || !identifier || !password}>
              {loading ? <Loader2 size={16} className="animate-spin" /> : <>Sign in <ArrowRight size={16} /></>}
            </button>
          </form>

          {accounts.length > 0 && (
            <div className="mt-9">
              <div className="mb-2.5 flex items-center justify-between">
                <span className="text-[13px] font-medium">Demo accounts</span>
                <div className="flex gap-1">
                  {(["all", "employee", "manager", "hr"] as const).map((f) => (
                    <button key={f} onClick={() => setFilter(f)} className="rounded-md px-2 py-0.5 text-[11.5px]"
                      style={{ background: filter === f ? "var(--panel-3)" : "transparent", color: filter === f ? "var(--text)" : "var(--muted)" }}>
                      {f === "hr" ? "HR" : f}
                    </button>
                  ))}
                </div>
              </div>
              <div className="scroll-thin grid max-h-[220px] grid-cols-2 gap-2 overflow-y-auto pr-1 sm:grid-cols-3">
                {shown.map((a) => (
                  <button key={a.employee_id} type="button"
                    onClick={() => { setIdentifier(a.employee_id); setPassword("veltrix"); }}
                    className="card !rounded-xl p-2.5 text-left transition-colors hover:border-[var(--accent)]"
                    style={identifier === a.employee_id ? { borderColor: "var(--accent)" } : undefined}>
                    <div className="font-mono text-[12.5px] font-semibold">{a.employee_id}</div>
                    <div className="mt-1 flex items-center gap-1.5">
                      <RoleBadge role={a.role} />
                      <span className="muted text-[11.5px]">{a.region} · {a.level}</span>
                    </div>
                  </button>
                ))}
              </div>
              <p className="muted mt-2 text-[11.5px]">Only IDs, roles and regions are shown here — names stay private until you sign in.</p>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
