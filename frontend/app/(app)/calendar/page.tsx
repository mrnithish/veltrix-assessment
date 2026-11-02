"use client";

import { CalendarPlus, ChevronLeft, ChevronRight, List, PartyPopper, Plane, Users } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { StatusBadge } from "@/components/Badges";
import { localDateISO, useNow } from "@/components/TopBar";
import { ErrorNote, Page, PageHeader, formatDate, formatRange } from "@/components/ui";
import { api, type Holiday, type LeaveRequest } from "@/lib/api";
import { useAuth } from "@/lib/auth";

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function iso(d: Date) {
  return localDateISO(d);
}
function addDays(d: Date, n: number) {
  const x = new Date(d);
  x.setDate(x.getDate() + n);
  return x;
}
function monthGrid(first: Date) {
  const start = addDays(first, -((first.getDay() + 6) % 7)); // back to Monday
  return Array.from({ length: 42 }, (_, i) => addDays(start, i));
}
const within = (day: string, r: { start_date: string; end_date: string }) => r.start_date <= day && day <= r.end_date;

export default function CalendarPage() {
  const { profile } = useAuth();
  const now = useNow(30_000);
  const assistantToday = profile?.today ?? "";
  const [cursor, setCursor] = useState(() => {
    const d = profile?.today ? new Date(`${profile.today}T00:00:00`) : new Date();
    return new Date(d.getFullYear(), d.getMonth(), 1);
  });
  const [holidays, setHolidays] = useState<Record<number, Holiday[]>>({});
  const [calendarTitle, setCalendarTitle] = useState<string | null>(null);
  const [mine, setMine] = useState<LeaveRequest[]>([]);
  const [team, setTeam] = useState<LeaveRequest[]>([]);
  const [showTeam, setShowTeam] = useState(true);
  const [showRestricted, setShowRestricted] = useState(true);
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const isManager = profile?.role === "manager";

  const days = useMemo(() => monthGrid(cursor), [cursor]);
  const rangeStart = iso(days[0]);
  const rangeEnd = iso(days[41]);

  useEffect(() => {
    api.myLeave().then((d) => setMine(d.requests)).catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    const years = Array.from(new Set([days[0].getFullYear(), days[41].getFullYear()]));
    years.filter((y) => !(y in holidays)).forEach((y) => {
      api.holidays(y).then((h) => {
        setHolidays((cur) => ({ ...cur, [y]: h.holidays }));
        if (h.calendar) setCalendarTitle(h.calendar.title);
      }).catch(() => setHolidays((cur) => ({ ...cur, [y]: [] })));
    });
  }, [days, holidays]);

  useEffect(() => {
    if (!isManager) return;
    api.team(rangeStart, rangeEnd).then((t) => setTeam(t.leave)).catch(() => setTeam([]));
  }, [isManager, rangeStart, rangeEnd]);

  const holidayMap = useMemo(() => {
    const m: Record<string, Holiday[]> = {};
    Object.values(holidays).flat().forEach((h) => {
      if (h.kind === "public" || showRestricted) (m[h.date] ??= []).push(h);
    });
    return m;
  }, [holidays, showRestricted]);

  const activeMine = mine.filter((r) => r.status !== "cancelled");
  const localToday = now ? iso(now) : assistantToday;
  const month = cursor.getMonth();
  const workingDays = days.filter((d) => d.getMonth() === month && d.getDay() % 6 !== 0
    && !(holidayMap[iso(d)] ?? []).some((h) => h.kind === "public")).length;
  const myDaysThisMonth = activeMine.reduce((n, r) => n + days.filter((d) => d.getMonth() === month
    && d.getDay() % 6 !== 0 && within(iso(d), r) && !(holidayMap[iso(d)] ?? []).some((h) => h.kind === "public")).length, 0);

  const upcoming = useMemo(() => {
    const items: { date: string; kind: "holiday" | "leave"; label: string; sub: string }[] = [];
    Object.values(holidays).flat().filter((h) => h.kind === "public" && h.date >= assistantToday)
      .forEach((h) => items.push({ date: h.date, kind: "holiday", label: h.name, sub: h.weekday }));
    activeMine.filter((r) => r.end_date >= assistantToday).forEach((r) => items.push({
      date: r.start_date, kind: "leave", label: `${r.leave_type} leave · ${formatRange(r.start_date, r.end_date)}`,
      sub: `${r.working_days} working day(s) · ${r.status}` }));
    return items.sort((a, b) => a.date.localeCompare(b.date)).slice(0, 8);
  }, [holidays, activeMine, assistantToday]);

  const sel = selected;
  const selHolidays = sel ? holidayMap[sel] ?? [] : [];
  const selMine = sel ? activeMine.filter((r) => within(sel, r)) : [];
  const selTeam = sel ? team.filter((r) => within(sel, r)) : [];

  return (
    <Page wide>
      <PageHeader title="Calendar"
        subtitle={<>Holidays from <span className="font-medium">{calendarTitle ?? "your office calendar"}</span>, your leave{isManager ? " and your team's leave" : ""}.</>}
        actions={<>
          <Link href="/holidays" className="btn"><List size={15} /> Holiday list</Link>
          <Link href={`/chat?new=${Date.now()}&q=${encodeURIComponent("I'd like to take leave from ")}`} className="btn btn-primary">
            <CalendarPlus size={15} /> Request leave
          </Link>
        </>} />
      {error && <ErrorNote message={error} />}

      <div className="grid gap-5 xl:grid-cols-[1fr_320px]">
        <div className="card overflow-hidden">
          <div className="flex flex-wrap items-center gap-2 border-b px-4 py-3" style={{ borderColor: "var(--border)" }}>
            <div className="flex items-center gap-1">
              <button className="btn !p-1.5" aria-label="Previous month" onClick={() => setCursor(new Date(cursor.getFullYear(), month - 1, 1))}><ChevronLeft size={16} /></button>
              <button className="btn !p-1.5" aria-label="Next month" onClick={() => setCursor(new Date(cursor.getFullYear(), month + 1, 1))}><ChevronRight size={16} /></button>
            </div>
            <h2 className="min-w-[150px] text-[17px] font-semibold">
              {cursor.toLocaleDateString("en-GB", { month: "long", year: "numeric" })}
            </h2>
            <button className="btn !py-1 !text-[12.5px]" onClick={() => {
              const d = new Date(`${localToday}T00:00:00`);
              setCursor(new Date(d.getFullYear(), d.getMonth(), 1));
              setSelected(localToday);
            }}>Today</button>
            <div className="ml-auto flex flex-wrap items-center gap-3 text-[12.5px]">
              <span className="muted">{workingDays} working days{myDaysThisMonth ? ` · ${myDaysThisMonth} on leave` : ""}</span>
              <label className="flex items-center gap-1.5"><input type="checkbox" checked={showRestricted} onChange={(e) => setShowRestricted(e.target.checked)} /> Restricted</label>
              {isManager && <label className="flex items-center gap-1.5"><input type="checkbox" checked={showTeam} onChange={(e) => setShowTeam(e.target.checked)} /> Team</label>}
            </div>
          </div>

          <div className="grid grid-cols-7 border-b text-center text-[11.5px] font-semibold uppercase tracking-wide" style={{ borderColor: "var(--border)", background: "var(--panel-2)" }}>
            {WEEKDAYS.map((w, i) => <div key={w} className="py-2" style={{ color: i >= 5 ? "var(--muted)" : "var(--text-2)" }}>{w}</div>)}
          </div>

          <div className="grid grid-cols-7">
            {days.map((d, i) => {
              const key = iso(d);
              const inMonth = d.getMonth() === month;
              const weekend = d.getDay() === 0 || d.getDay() === 6;
              const hol = holidayMap[key] ?? [];
              const myLeave = activeMine.filter((r) => within(key, r));
              const teamLeave = showTeam ? team.filter((r) => within(key, r)) : [];
              const isToday = key === localToday;
              const isAssistantToday = key === assistantToday && assistantToday !== localToday;
              const isSel = key === selected;
              return (
                <button key={key} onClick={() => setSelected(key)}
                  className="relative flex min-h-[104px] flex-col gap-1 border-b border-r p-1.5 text-left transition-colors hover:bg-[var(--panel-2)]"
                  style={{
                    borderColor: "var(--border)",
                    background: isSel ? "var(--accent-soft)" : weekend ? "var(--panel-2)" : undefined,
                    opacity: inMonth ? 1 : 0.45,
                    borderRightWidth: (i + 1) % 7 === 0 ? 0 : 1,
                  }}>
                  <span className="flex items-center justify-between">
                    <span className="grid h-6 min-w-6 place-items-center rounded-full px-1 text-[12.5px] font-semibold tabular-nums"
                      style={isToday ? { background: "var(--accent)", color: "#fff" } : isAssistantToday
                        ? { outline: "2px dashed var(--warn)" } : undefined}>
                      {d.getDate()}
                    </span>
                    {teamLeave.length > 0 && (
                      <span className="flex -space-x-1.5">
                        {teamLeave.slice(0, 3).map((r) => (
                          <span key={r.request_id} title={`${r.full_name} · ${r.leave_type} · ${r.status}`}
                            className="grid h-5 w-5 place-items-center rounded-full border text-[9px] font-semibold"
                            style={{ background: "var(--info-soft)", color: "var(--info)", borderColor: "var(--panel)" }}>
                            {(r.full_name ?? "?").split(" ").map((p) => p[0]).slice(0, 2).join("")}
                          </span>
                        ))}
                      </span>
                    )}
                  </span>
                  {hol.map((h) => (
                    <span key={h.name} className="truncate rounded-md px-1.5 py-0.5 text-[11px] font-medium" title={h.name}
                      style={h.kind === "public" ? { background: "var(--bad-soft)", color: "var(--bad)" }
                        : { border: "1px dashed var(--border-strong)", color: "var(--muted)" }}>
                      {h.name}
                    </span>
                  ))}
                  {myLeave.map((r) => (
                    <span key={r.request_id} className="truncate rounded-md px-1.5 py-0.5 text-[11px] font-medium capitalize"
                      title={`${r.leave_type} leave · ${r.status}`}
                      style={r.status === "approved" ? { background: "var(--ok-soft)", color: "var(--ok)" }
                        : { background: "var(--warn-soft)", color: "var(--warn)" }}>
                      {r.leave_type}{r.status === "pending" ? " · pending" : ""}
                    </span>
                  ))}
                </button>
              );
            })}
          </div>

          <div className="flex flex-wrap gap-4 px-4 py-3 text-[12px]" style={{ background: "var(--panel-2)" }}>
            <Legend style={{ background: "var(--accent)" }} label="Today (your computer)" round />
            {assistantToday !== localToday && <Legend style={{ outline: "2px dashed var(--warn)" }} label="Assistant date" round />}
            <Legend style={{ background: "var(--bad-soft)", border: "1px solid var(--bad)" }} label="Public holiday" />
            <Legend style={{ border: "1px dashed var(--border-strong)" }} label="Restricted (office open)" />
            <Legend style={{ background: "var(--ok-soft)", border: "1px solid var(--ok)" }} label="My leave · approved" />
            <Legend style={{ background: "var(--warn-soft)", border: "1px solid var(--warn)" }} label="My leave · pending" />
            {isManager && <Legend style={{ background: "var(--info-soft)", border: "1px solid var(--info)" }} label="Team member off" round />}
          </div>
        </div>

        <div className="space-y-5">
          <div className="card p-4">
            <h3 className="text-[14px] font-semibold">{sel ? formatDate(sel, { weekday: "long", day: "numeric", month: "long", year: "numeric" }) : "Select a day"}</h3>
            {!sel && <p className="muted mt-1 text-[12.5px]">Click a day to see holidays and who is off.</p>}
            {sel && (
              <div className="mt-3 space-y-3 text-[13px]">
                {selHolidays.length === 0 && selMine.length === 0 && selTeam.length === 0 && (
                  <p className="muted">{[0, 6].includes(new Date(`${sel}T00:00:00`).getDay()) ? "Weekend." : "A regular working day."}</p>
                )}
                {selHolidays.map((h) => (
                  <div key={h.name} className="flex items-start gap-2">
                    <PartyPopper size={15} style={{ color: h.kind === "public" ? "var(--bad)" : "var(--muted)" }} className="mt-0.5" />
                    <div><div className="font-medium">{h.name}</div><div className="muted text-[12px]">{h.kind === "public" ? "Office closed" : "Restricted holiday — office open"}</div></div>
                  </div>
                ))}
                {selMine.map((r) => (
                  <div key={r.request_id} className="flex items-start gap-2">
                    <Plane size={15} className="mt-0.5" style={{ color: "var(--ok)" }} />
                    <div className="flex-1"><div className="font-medium capitalize">My {r.leave_type} leave</div>
                      <div className="muted text-[12px]">{formatRange(r.start_date, r.end_date)} · {r.working_days} day(s)</div></div>
                    <StatusBadge status={r.status} />
                  </div>
                ))}
                {selTeam.length > 0 && (
                  <div>
                    <div className="muted mb-1.5 flex items-center gap-1.5 text-[12px] font-semibold uppercase"><Users size={13} /> Team</div>
                    {selTeam.map((r) => (
                      <div key={r.request_id} className="flex items-center justify-between py-1">
                        <span>{r.full_name} <span className="muted capitalize">· {r.leave_type}</span></span>
                        <StatusBadge status={r.status} />
                      </div>
                    ))}
                  </div>
                )}
                {sel >= assistantToday && ![0, 6].includes(new Date(`${sel}T00:00:00`).getDay()) && !selHolidays.some((h) => h.kind === "public") && (
                  <Link className="btn w-full" href={`/chat?new=${Date.now()}&q=${encodeURIComponent(`I'd like to take leave on ${formatDate(sel, { day: "numeric", month: "long", year: "numeric" })}. Leave type: `)}`}>
                    <CalendarPlus size={15} /> Request leave on this day
                  </Link>
                )}
              </div>
            )}
          </div>

          <div className="card p-4">
            <h3 className="mb-3 text-[14px] font-semibold">Coming up</h3>
            {upcoming.length === 0 && <p className="muted text-[12.5px]">Nothing scheduled.</p>}
            <div className="space-y-2.5">
              {upcoming.map((u, i) => (
                <button key={i} className="flex w-full items-center gap-3 text-left" onClick={() => {
                  const d = new Date(`${u.date}T00:00:00`);
                  setCursor(new Date(d.getFullYear(), d.getMonth(), 1));
                  setSelected(u.date);
                }}>
                  <span className="w-11 shrink-0 rounded-lg py-1 text-center" style={{ background: u.kind === "holiday" ? "var(--bad-soft)" : "var(--ok-soft)" }}>
                    <span className="block text-[14px] font-semibold leading-none">{Number(u.date.slice(8, 10))}</span>
                    <span className="muted text-[10px]">{new Date(`${u.date}T00:00:00`).toLocaleDateString("en-GB", { month: "short" })}</span>
                  </span>
                  <span className="min-w-0">
                    <span className="block truncate text-[13px] font-medium capitalize">{u.label}</span>
                    <span className="muted text-[11.5px]">{u.sub}</span>
                  </span>
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </Page>
  );
}

function Legend({ style, label, round }: { style: React.CSSProperties; label: string; round?: boolean }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className={`inline-block h-3 w-3 ${round ? "rounded-full" : "rounded-sm"}`} style={style} />
      <span className="muted">{label}</span>
    </span>
  );
}
