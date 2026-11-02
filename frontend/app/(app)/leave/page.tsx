"use client";

import { CalendarClock, CalendarPlus, HeartPulse, Hourglass, MessageSquareText, Plane, Wallet } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { StatusBadge } from "@/components/Badges";
import { EmptyState, ErrorNote, Page, PageHeader, SkeletonRows, StatCard, formatDate, formatRange } from "@/components/ui";
import { api, type MyLeave } from "@/lib/api";
import { useAuth } from "@/lib/auth";

type Filter = "all" | "upcoming" | "pending" | "past" | "cancelled";

export default function LeavePage() {
  const { profile } = useAuth();
  const [data, setData] = useState<MyLeave | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("all");

  useEffect(() => {
    api.myLeave().then(setData).catch((e) => setError(e.message));
  }, []);

  const today = data?.today ?? profile?.today ?? "";
  const stats = useMemo(() => {
    const reqs = data?.requests ?? [];
    const active = reqs.filter((r) => r.status !== "cancelled");
    const upcoming = active.filter((r) => r.start_date > today).sort((a, b) => a.start_date.localeCompare(b.start_date));
    return {
      pending: active.filter((r) => r.status === "pending").length,
      next: upcoming[0],
      takenThisYear: active.filter((r) => r.end_date < today && r.start_date.startsWith(today.slice(0, 4)))
        .reduce((n, r) => n + r.working_days, 0),
    };
  }, [data, today]);

  const rows = (data?.requests ?? []).filter((r) => {
    if (filter === "all") return true;
    if (filter === "cancelled") return r.status === "cancelled";
    if (filter === "pending") return r.status === "pending";
    if (filter === "upcoming") return r.status !== "cancelled" && r.start_date > today;
    return r.status !== "cancelled" && r.end_date < today;
  }).sort((a, b) => b.start_date.localeCompare(a.start_date));

  return (
    <Page>
      <PageHeader title="My leave"
        subtitle={profile ? `${profile.full_name} · ${profile.employee_id} · ${profile.region} · joined ${formatDate(profile.join_date)} (${profile.length_of_service})` : undefined}
        actions={<Link href={`/chat?new=${Date.now()}&q=${encodeURIComponent("Apply for annual leave from ")}`}
          className="btn btn-primary"><CalendarPlus size={16} /> Request leave</Link>} />

      {error && <ErrorNote message={error} />}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Annual leave" icon={Plane} tone="accent"
          value={data ? `${data.balances.annual ?? 0}` : "—"} hint="days remaining (pending & approved already deducted)" />
        <StatCard label="Sick leave" icon={HeartPulse} tone="ok"
          value={data ? `${data.balances.sick ?? 0}` : "—"} hint="days remaining" />
        <StatCard label="Awaiting approval" icon={Hourglass} tone="warn" value={data ? stats.pending : "—"}
          hint="pending requests" />
        <StatCard label="Next leave" icon={CalendarClock} tone="info"
          value={stats.next ? formatDate(stats.next.start_date, { day: "numeric", month: "short" }) : "—"}
          hint={stats.next ? `${stats.next.leave_type} · ${stats.next.working_days} working day(s)` : "nothing booked"} />
      </div>

      <div className="card mt-6 overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b px-5 py-3.5" style={{ borderColor: "var(--border)" }}>
          <div>
            <h2 className="text-[15px] font-semibold">Leave requests</h2>
            <p className="muted text-[12.5px]">{stats.takenThisYear} working day(s) taken so far this year</p>
          </div>
          <div className="flex gap-1 rounded-lg p-1" style={{ background: "var(--panel-2)" }}>
            {(["all", "upcoming", "pending", "past", "cancelled"] as Filter[]).map((f) => (
              <button key={f} onClick={() => setFilter(f)} className="rounded-md px-2.5 py-1 text-[12.5px] capitalize"
                style={{ background: filter === f ? "var(--panel)" : "transparent", boxShadow: filter === f ? "var(--shadow)" : undefined,
                  fontWeight: filter === f ? 600 : 500 }}>{f}</button>
            ))}
          </div>
        </div>
        {!data && !error && <SkeletonRows />}
        {data && rows.length === 0 && (
          <EmptyState icon={Wallet} title="No leave requests here" body="Ask the assistant to book leave — it checks your balance, holidays and overlaps first." />
        )}
        {data && rows.length > 0 && (
          <div className="overflow-x-auto">
            <table className="table">
              <thead>
                <tr><th>Dates</th><th>Type</th><th>Working days</th><th>Status</th><th>Requested</th><th className="text-right">Actions</th></tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.request_id}>
                    <td className="font-medium">{formatRange(r.start_date, r.end_date)}</td>
                    <td className="capitalize">{r.leave_type}</td>
                    <td className="tabular-nums">{r.working_days}</td>
                    <td><StatusBadge status={r.status} /></td>
                    <td className="muted">{formatDate(r.created_at)}</td>
                    <td className="text-right">
                      {r.cancellable ? (
                        <Link className="btn !py-1 !text-[12.5px]"
                          href={`/chat?new=${Date.now()}&q=${encodeURIComponent(`Cancel my ${r.leave_type} leave request ${r.request_id} (${r.start_date} to ${r.end_date})`)}`}>
                          <MessageSquareText size={13} /> Cancel via assistant
                        </Link>
                      ) : <span className="muted text-[12px]">—</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      <p className="muted mt-3 text-[12px]">
        Changes go through the assistant so the same rules apply everywhere: whole days in 2026, no past start dates, no overlaps,
        enough balance, and an explicit confirmation before anything is saved.
      </p>
    </Page>
  );
}
