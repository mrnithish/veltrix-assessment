"use client";

import { CalendarRange, ChevronRight, HeartPulse, Plane, ShieldCheck, Users } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { StatusBadge } from "@/components/Badges";
import { EmptyState, ErrorNote, Page, PageHeader, SkeletonRows, formatDate, formatRange } from "@/components/ui";
import { api, type LeaveRequest, type TeamView } from "@/lib/api";
import { useAuth } from "@/lib/auth";

function addDays(iso: string, n: number) {
  const d = new Date(`${iso}T00:00:00`);
  d.setDate(d.getDate() + n);
  return d.toISOString().slice(0, 10);
}

export default function TeamPage() {
  const { profile } = useAuth();
  const today = profile?.today ?? new Date().toISOString().slice(0, 10);
  const [start, setStart] = useState(today);
  const [end, setEnd] = useState(addDays(today, 30));
  const [data, setData] = useState<TeamView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [member, setMember] = useState<{ balances: Record<string, number>; requests: LeaveRequest[] } | null>(null);
  const [memberError, setMemberError] = useState<string | null>(null);

  const load = useCallback(() => {
    setError(null);
    setData(null);
    api.team(start, end).then(setData).catch((e) => setError(e.message));
  }, [start, end]);

  useEffect(() => {
    if (profile?.role === "manager") load();
  }, [profile, load]);

  useEffect(() => {
    if (!selected) return;
    setMember(null);
    setMemberError(null);
    api.teamMember(selected).then(setMember).catch((e) => setMemberError(e.message));
  }, [selected]);

  if (profile && profile.role !== "manager") {
    return <Page><EmptyState icon={ShieldCheck} title="Team view is for managers"
      body="Leave data is only visible for yourself, or — for managers — for direct reports." /></Page>;
  }

  const presets = [
    { label: "Next 7 days", s: today, e: addDays(today, 7) },
    { label: "Next 30 days", s: today, e: addDays(today, 30) },
    { label: "Rest of 2026", s: today, e: "2026-12-31" },
  ];
  const sel = data?.team.find((t) => t.employee_id === selected);

  return (
    <Page wide>
      <PageHeader title="My team" subtitle="Pending and approved leave of your direct reports. Balances open one person at a time." />

      <div className="card mb-5 flex flex-wrap items-end gap-3 p-4">
        <div>
          <label className="label" htmlFor="from">From</label>
          <input id="from" type="date" className="input !w-[170px]" value={start} onChange={(e) => setStart(e.target.value)} />
        </div>
        <div>
          <label className="label" htmlFor="to">To</label>
          <input id="to" type="date" className="input !w-[170px]" value={end} onChange={(e) => setEnd(e.target.value)} />
        </div>
        <div className="flex flex-wrap gap-1.5">
          {presets.map((p) => (
            <button key={p.label} className="btn !py-2 !text-[12.5px]" onClick={() => { setStart(p.s); setEnd(p.e); }}>{p.label}</button>
          ))}
        </div>
      </div>

      {error && <ErrorNote message={error} />}

      <div className="grid gap-5 lg:grid-cols-[1fr_340px]">
        <div className="card overflow-hidden">
          <div className="flex items-center gap-2 border-b px-5 py-3.5" style={{ borderColor: "var(--border)" }}>
            <CalendarRange size={16} style={{ color: "var(--accent)" }} />
            <h2 className="text-[15px] font-semibold">Leave {data ? `· ${formatRange(data.start_date, data.end_date)}` : ""}</h2>
          </div>
          {!data && !error && <SkeletonRows />}
          {data && data.leave.length === 0 && <EmptyState icon={CalendarRange} title="Nobody is off in this period" />}
          {data && data.leave.length > 0 && (
            <div className="overflow-x-auto">
              <table className="table">
                <thead><tr><th>Employee</th><th>Dates</th><th>Type</th><th>Days</th><th>Status</th></tr></thead>
                <tbody>
                  {data.leave.map((r) => (
                    <tr key={r.request_id}>
                      <td><div className="font-medium">{r.full_name}</div><div className="muted font-mono text-[11.5px]">{r.employee_id}</div></td>
                      <td>{formatRange(r.start_date, r.end_date)}</td>
                      <td className="capitalize">{r.leave_type}</td>
                      <td className="tabular-nums">{r.working_days}</td>
                      <td><StatusBadge status={r.status} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="card overflow-hidden">
          <div className="flex items-center gap-2 border-b px-5 py-3.5" style={{ borderColor: "var(--border)" }}>
            <Users size={16} style={{ color: "var(--accent)" }} />
            <h2 className="text-[15px] font-semibold">Direct reports</h2>
            <span className="muted ml-auto text-[12.5px]">{data?.team.length ?? ""}</span>
          </div>
          <div className="p-2">
            {data?.team.map((t) => (
              <button key={t.employee_id} onClick={() => setSelected(t.employee_id === selected ? null : t.employee_id)}
                className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left transition-colors hover:bg-[var(--panel-2)]"
                style={selected === t.employee_id ? { background: "var(--panel-3)" } : undefined}>
                <span className="grid h-8 w-8 place-items-center rounded-full text-[12px] font-semibold"
                  style={{ background: "var(--accent-soft)", color: "var(--accent-text)" }}>
                  {t.full_name.split(" ").map((p) => p[0]).slice(0, 2).join("")}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[13.5px] font-medium">{t.full_name}</span>
                  <span className="muted text-[11.5px]">{t.employee_id} · {t.level} · {t.region}</span>
                </span>
                <ChevronRight size={15} className="muted transition-transform"
                  style={{ transform: selected === t.employee_id ? "rotate(90deg)" : "none" }} />
              </button>
            ))}
          </div>
          {sel && (
            <div className="border-t p-4" style={{ borderColor: "var(--border)" }}>
              <div className="mb-3 text-[13px] font-semibold">{sel.full_name}</div>
              {memberError && <ErrorNote message={memberError} />}
              {!member && !memberError && <div className="skeleton h-16" />}
              {member && (
                <>
                  <div className="grid grid-cols-2 gap-2">
                    <div className="rounded-lg p-3" style={{ background: "var(--panel-2)" }}>
                      <div className="muted flex items-center gap-1.5 text-[12px]"><Plane size={13} /> Annual</div>
                      <div className="mt-1 text-[20px] font-semibold tabular-nums">{member.balances.annual ?? 0}</div>
                    </div>
                    <div className="rounded-lg p-3" style={{ background: "var(--panel-2)" }}>
                      <div className="muted flex items-center gap-1.5 text-[12px]"><HeartPulse size={13} /> Sick</div>
                      <div className="mt-1 text-[20px] font-semibold tabular-nums">{member.balances.sick ?? 0}</div>
                    </div>
                  </div>
                  <div className="mt-3 space-y-1.5">
                    {member.requests.slice(-5).reverse().map((r) => (
                      <div key={r.request_id} className="flex items-center justify-between text-[12.5px]">
                        <span>{formatRange(r.start_date, r.end_date)} <span className="muted capitalize">· {r.leave_type}</span></span>
                        <StatusBadge status={r.status} />
                      </div>
                    ))}
                  </div>
                  <p className="muted mt-3 text-[11.5px]">Viewed {formatDate(today)} · access is audited.</p>
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </Page>
  );
}
