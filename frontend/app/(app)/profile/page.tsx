"use client";

import { BadgeCheck, Briefcase, CalendarDays, Clock3, EyeOff, Globe2, HeartPulse, Mail, MessageSquareText, Plane,
  ShieldCheck, UserRound, Users } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { RoleBadge } from "@/components/Badges";
import { useNow } from "@/components/TopBar";
import { Page, formatDate } from "@/components/ui";
import { api, type MyLeave } from "@/lib/api";
import { useAuth } from "@/lib/auth";

const REGION_NAME: Record<string, string> = { IN: "India", US: "United States", DE: "Germany" };

function Field({ icon: Icon, label, children }: { icon: typeof Mail; label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-3">
      <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg" style={{ background: "var(--panel-2)" }}>
        <Icon size={16} className="muted" />
      </span>
      <div className="min-w-0">
        <div className="muted text-[12px]">{label}</div>
        <div className="truncate text-[14px] font-medium">{children}</div>
      </div>
    </div>
  );
}

export default function ProfilePage() {
  const { profile } = useAuth();
  const now = useNow();
  const [leave, setLeave] = useState<MyLeave | null>(null);

  useEffect(() => {
    api.myLeave().then(setLeave).catch(() => undefined);
  }, []);

  if (!profile) return null;
  const initials = profile.full_name.split(" ").map((p) => p[0]).slice(0, 2).join("");
  const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const pending = leave?.requests.filter((r) => r.status === "pending").length ?? 0;
  const next = leave?.requests.filter((r) => r.status !== "cancelled" && r.start_date > profile.today)
    .sort((a, b) => a.start_date.localeCompare(b.start_date))[0];

  return (
    <Page>
      <div className="card overflow-hidden">
        <div className="h-28" style={{ background: "radial-gradient(600px 200px at 0% 0%, #6366f1 0%, transparent 70%), radial-gradient(500px 200px at 100% 100%, #8b5cf6 0%, transparent 70%), #1e1b4b" }} />
        <div className="px-6 pb-6">
          <div className="-mt-10 flex flex-wrap items-start gap-4">
            <div className="grid h-20 w-20 place-items-center rounded-2xl border-4 text-[26px] font-semibold shadow-lg"
              style={{ background: "var(--accent-soft)", color: "var(--accent-text)", borderColor: "var(--panel)" }}>{initials}</div>
            <div className="mt-12">
              <h1 className="text-[22px] font-semibold tracking-tight">{profile.full_name}</h1>
              <div className="muted mt-0.5 flex flex-wrap items-center gap-2 text-[13px]">
                <span className="font-mono">{profile.employee_id}</span> · {profile.level} · {REGION_NAME[profile.region] ?? profile.region}
                <RoleBadge role={profile.role} />
              </div>
            </div>
            <div className="ml-auto mt-12 flex gap-2">
              <Link href="/leave" className="btn"><Plane size={15} /> My leave</Link>
              <Link href={`/chat?new=${Date.now()}`} className="btn btn-primary"><MessageSquareText size={15} /> Ask the assistant</Link>
            </div>
          </div>

          <div className="mt-7 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            <Field icon={Mail} label="Work email (masked)">{profile.email}</Field>
            <Field icon={Globe2} label="Office / region">{REGION_NAME[profile.region] ?? profile.region} ({profile.region})</Field>
            <Field icon={Briefcase} label="Role · level">{profile.role === "hr" ? "HR" : profile.role} · {profile.level}</Field>
            <Field icon={CalendarDays} label="Joined">{formatDate(profile.join_date)} · {profile.length_of_service}</Field>
            <Field icon={UserRound} label="Manager">{profile.manager_id ?? "—"}</Field>
            <Field icon={Clock3} label="Local time">
              {now ? now.toLocaleString("en-GB", { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "—"}
              <span className="muted text-[12px]"> · {tz}</span>
            </Field>
          </div>
        </div>
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-3">
        <div className="card p-5">
          <div className="muted text-[13px] font-medium">Leave balances</div>
          <div className="mt-3 grid grid-cols-2 gap-3">
            <div className="rounded-xl p-3" style={{ background: "var(--accent-soft)" }}>
              <div className="flex items-center gap-1.5 text-[12px]" style={{ color: "var(--accent-text)" }}><Plane size={13} /> Annual</div>
              <div className="mt-1 text-[24px] font-semibold tabular-nums">{leave?.balances.annual ?? "—"}</div>
            </div>
            <div className="rounded-xl p-3" style={{ background: "var(--ok-soft)" }}>
              <div className="flex items-center gap-1.5 text-[12px]" style={{ color: "var(--ok)" }}><HeartPulse size={13} /> Sick</div>
              <div className="mt-1 text-[24px] font-semibold tabular-nums">{leave?.balances.sick ?? "—"}</div>
            </div>
          </div>
          <div className="muted mt-3 text-[12.5px]">
            {pending} pending · next leave {next ? formatDate(next.start_date) : "not booked"}
          </div>
        </div>

        <div className="card p-5">
          <div className="muted flex items-center gap-1.5 text-[13px] font-medium"><Users size={14} /> Direct reports</div>
          {profile.direct_reports.length === 0 && <p className="muted mt-3 text-[13px]">No direct reports.</p>}
          <div className="mt-2 space-y-1">
            {profile.direct_reports.map((r) => (
              <div key={r.employee_id} className="flex items-center gap-2.5 py-1.5">
                <span className="grid h-7 w-7 place-items-center rounded-full text-[11px] font-semibold" style={{ background: "var(--info-soft)", color: "var(--info)" }}>
                  {r.full_name.split(" ").map((p) => p[0]).slice(0, 2).join("")}
                </span>
                <span className="text-[13.5px]">{r.full_name}</span>
                <span className="muted ml-auto font-mono text-[11.5px]">{r.employee_id} · {r.level}</span>
              </div>
            ))}
          </div>
          {profile.role === "manager" && <Link href="/team" className="btn mt-3 w-full !text-[12.5px]"><Users size={14} /> Team view</Link>}
        </div>

        <div className="card p-5">
          <div className="muted flex items-center gap-1.5 text-[13px] font-medium"><ShieldCheck size={14} /> What the assistant knows about you</div>
          <ul className="mt-3 space-y-2 text-[13px]">
            {[
              `Employee ID ${profile.employee_id}, ${profile.role === "hr" ? "HR" : profile.role}, ${profile.region}, ${profile.level}`,
              `Joined ${formatDate(profile.join_date)} (${profile.length_of_service})`,
              `Manager ${profile.manager_id ?? "none"}; ${profile.direct_reports.length} direct report(s) by ID`,
              `Today is ${formatDate(profile.today)}${profile.timezone ? ` (${profile.timezone})` : ""}`,
            ].map((t) => <li key={t} className="flex gap-2"><BadgeCheck size={15} className="mt-0.5 shrink-0" style={{ color: "var(--ok)" }} />{t}</li>)}
            <li className="flex gap-2"><EyeOff size={15} className="mt-0.5 shrink-0 muted" />
              <span className="muted">Never your phone; your email only masked; your first name only to address you.</span></li>
          </ul>
          <p className="muted mt-3 text-[11.5px]">Identity always comes from the HR database — claims typed in the chat are ignored.</p>
        </div>
      </div>
    </Page>
  );
}
