"use client";

import { CalendarDays, CalendarOff, FileText, Sparkles } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { EmptyState, ErrorNote, Page, PageHeader, SkeletonRows, StatCard, formatDate } from "@/components/ui";
import { api, type Holidays } from "@/lib/api";
import { useAuth } from "@/lib/auth";

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
  "November", "December"];

export default function HolidaysPage() {
  const { profile } = useAuth();
  const thisYear = Number((profile?.today ?? "2026").slice(0, 4));
  const [year, setYear] = useState(thisYear);
  const [data, setData] = useState<Holidays | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showRestricted, setShowRestricted] = useState(true);

  useEffect(() => {
    setData(null);
    setError(null);
    api.holidays(year).then(setData).catch((e) => setError(e.message));
  }, [year]);

  const today = profile?.today ?? "";
  const list = useMemo(() => (data?.holidays ?? []).filter((h) => showRestricted || h.kind === "public"), [data, showRestricted]);
  const byMonth = useMemo(() => {
    const m: Record<number, typeof list> = {};
    for (const h of list) (m[Number(h.date.slice(5, 7)) - 1] ??= []).push(h);
    return m;
  }, [list]);
  const publicDays = (data?.holidays ?? []).filter((h) => h.kind === "public");
  const weekdayPublic = publicDays.filter((h) => !["Saturday", "Sunday"].includes(h.weekday));
  const next = publicDays.find((h) => h.date >= today);

  return (
    <Page>
      <PageHeader title="Holidays"
        subtitle={data?.calendar ? <>From <span className="font-medium">{data.calendar.title}</span> — the calendar that applies to your office ({profile?.region}).</> : `Office: ${profile?.region ?? ""}`}
        actions={
          <div className="flex gap-1 rounded-lg p-1" style={{ background: "var(--panel-2)" }}>
            {[thisYear - 1, thisYear].map((y) => (
              <button key={y} onClick={() => setYear(y)} className="rounded-md px-3 py-1 text-[13px]"
                style={{ background: year === y ? "var(--panel)" : "transparent", fontWeight: year === y ? 600 : 500,
                  boxShadow: year === y ? "var(--shadow)" : undefined }}>{y}</button>
            ))}
          </div>
        } />
      {error && <ErrorNote message={error} />}

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard label="Public holidays" icon={CalendarDays} value={data ? publicDays.length : "—"} hint={`in ${year}`} />
        <StatCard label="On working days" icon={CalendarOff} tone="ok" value={data ? weekdayPublic.length : "—"}
          hint="not deducted when you take leave" />
        <StatCard label="Next holiday" icon={Sparkles} tone="info"
          value={next ? formatDate(next.date, { day: "numeric", month: "short" }) : "—"} hint={next?.name ?? "none left this year"} />
      </div>

      <div className="card mt-6 overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b px-5 py-3.5" style={{ borderColor: "var(--border)" }}>
          <h2 className="text-[15px] font-semibold">{year} calendar</h2>
          <label className="flex items-center gap-2 text-[13px]">
            <input type="checkbox" checked={showRestricted} onChange={(e) => setShowRestricted(e.target.checked)} />
            Show restricted / optional holidays
          </label>
        </div>
        {!data && !error && <SkeletonRows rows={6} />}
        {data && !data.calendar && <EmptyState icon={CalendarDays} title={`No holiday calendar for ${year}`}
          body="No calendar document applies to your office for this year." />}
        {data?.calendar && (
          <div className="grid gap-px sm:grid-cols-2" style={{ background: "var(--border)" }}>
            {MONTHS.map((name, i) => byMonth[i]?.length ? (
              <div key={name} className="p-4" style={{ background: "var(--panel)" }}>
                <div className="muted mb-2 text-[12px] font-semibold uppercase tracking-wide">{name}</div>
                <div className="space-y-2">
                  {byMonth[i].map((h) => {
                    const weekend = ["Saturday", "Sunday"].includes(h.weekday);
                    const past = h.date < today;
                    return (
                      <div key={h.date + h.name} className="flex items-center gap-3" style={{ opacity: past ? 0.55 : 1 }}>
                        <div className="w-11 shrink-0 rounded-lg py-1 text-center"
                          style={{ background: h.kind === "public" ? "var(--accent-soft)" : "var(--panel-2)" }}>
                          <div className="text-[15px] font-semibold leading-none tabular-nums">{Number(h.date.slice(8, 10))}</div>
                          <div className="muted mt-0.5 text-[10px]">{h.weekday.slice(0, 3)}</div>
                        </div>
                        <div className="min-w-0">
                          <div className="truncate text-[13.5px] font-medium">{h.name}</div>
                          <div className="muted text-[11.5px]">
                            {h.kind === "restricted" ? "Restricted — office open, optional day" : weekend ? "Falls on a weekend" : "Office closed"}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            ) : null)}
          </div>
        )}
      </div>
      {data?.calendar && (
        <p className="muted mt-3 flex items-center gap-1.5 text-[12px]">
          <FileText size={12} /> Source: {data.calendar.doc_id}, effective {formatDate(data.calendar.effective_date)}.
          Extracted automatically at ingestion; these dates drive working-day counts for leave.
        </p>
      )}
    </Page>
  );
}
