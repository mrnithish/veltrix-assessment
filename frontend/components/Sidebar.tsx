"use client";

import {
  Activity, CalendarDays, FileText, LogOut, MessageSquarePlus, MessagesSquare, Settings, Trash2, UserRound, Users,
  Wallet,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import { RoleBadge } from "@/components/Badges";
import { relativeTime } from "@/components/ui";
import type { SessionSummary } from "@/lib/api";
import { useAppData } from "@/lib/app-data";
import { useAuth } from "@/lib/auth";

function groupSessions(sessions: SessionSummary[]) {
  const groups: Record<string, SessionSummary[]> = { Today: [], "Previous 7 days": [], Older: [] };
  const now = Date.now();
  for (const s of sessions) {
    const t = new Date(s.updated_at.endsWith("Z") || s.updated_at.includes("+") ? s.updated_at : `${s.updated_at}Z`).getTime();
    const days = (now - t) / 86_400_000;
    (days < 1 ? groups.Today : days < 7 ? groups["Previous 7 days"] : groups.Older).push(s);
  }
  return Object.entries(groups).filter(([, v]) => v.length);
}

export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const { profile, logout } = useAuth();
  const { sessions, sessionsLoading, removeSession } = useAppData();
  const pathname = usePathname();
  const params = useSearchParams();
  const router = useRouter();
  const active = params.get("s");
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const grouped = useMemo(() => groupSessions(sessions), [sessions]);
  if (!profile) return null;

  const nav = [
    { href: "/chat", label: "Assistant", icon: MessagesSquare },
    { href: "/leave", label: "My leave", icon: Wallet },
    ...(profile.role === "manager" ? [{ href: "/team", label: "My team", icon: Users }] : []),
    { href: "/calendar", label: "Calendar", icon: CalendarDays },
    { href: "/documents", label: "Documents", icon: FileText },
    { href: "/profile", label: "Profile", icon: UserRound },
    { href: "/system", label: "Architecture & usage", icon: Activity },
    { href: "/settings", label: "Settings", icon: Settings },
  ];
  const initials = profile.full_name.split(" ").map((p) => p[0]).slice(0, 2).join("");

  return (
    <div className="flex h-full flex-col" style={{ background: "var(--sidebar)" }}>
      <div className="flex items-center gap-2.5 px-4 pb-3 pt-4">
        <div className="grid h-8 w-8 place-items-center rounded-lg text-[14px] font-bold text-white"
          style={{ background: "linear-gradient(135deg, var(--accent), #8b5cf6)" }}>V</div>
        <div className="leading-tight">
          <div className="text-[14px] font-semibold">Veltrix PeopleOps</div>
          <div className="muted text-[11.5px]">HR assistant</div>
        </div>
      </div>

      <div className="px-3">
        <button className="btn w-full justify-start" onClick={() => {
          router.push(`/chat?new=${Date.now()}`);
          onNavigate?.();
        }}>
          <MessageSquarePlus size={16} /> New chat
        </button>
      </div>

      <nav className="mt-3 space-y-0.5 px-3">
        {nav.map((n) => {
          const on = pathname === n.href;
          return (
            <Link key={n.href} href={n.href} onClick={onNavigate}
              className="flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-[13.5px] transition-colors"
              style={{ background: on ? "var(--panel-3)" : undefined, color: on ? "var(--text)" : "var(--text-2)",
                fontWeight: on ? 600 : 500 }}>
              <n.icon size={16} style={{ color: on ? "var(--accent)" : "var(--muted)" }} />
              {n.label}
            </Link>
          );
        })}
      </nav>

      <div className="muted mt-5 px-5 text-[11.5px] font-semibold uppercase tracking-wide">Chat history</div>
      <div className="scroll-thin mt-1.5 min-h-0 flex-1 overflow-y-auto px-3 pb-3">
        {sessionsLoading && <div className="space-y-2 p-2">{[0, 1, 2].map((i) => <div key={i} className="skeleton h-7" />)}</div>}
        {!sessionsLoading && sessions.length === 0 && (
          <p className="muted px-2.5 py-2 text-[12.5px]">Your conversations will appear here.</p>
        )}
        {grouped.map(([label, items]) => (
          <div key={label} className="mb-2">
            <div className="muted px-2.5 py-1 text-[11px]">{label}</div>
            {items.map((s) => {
              const on = pathname === "/chat" && active === s.session_id;
              return (
                <div key={s.session_id} className="group relative">
                  <Link href={`/chat?s=${s.session_id}`} onClick={onNavigate}
                    className="block truncate rounded-lg py-2 pl-2.5 pr-8 text-[13px] transition-colors hover:bg-[var(--panel-2)]"
                    style={{ background: on ? "var(--panel-3)" : undefined, fontWeight: on ? 600 : 400 }}
                    title={`${s.title} · ${relativeTime(s.updated_at)}`}>
                    {s.title}
                  </Link>
                  {confirmDelete === s.session_id ? (
                    <button className="absolute right-1 top-1.5 rounded-md px-1.5 py-0.5 text-[11px] font-medium"
                      style={{ background: "var(--bad-soft)", color: "var(--bad)" }}
                      onClick={async () => {
                        await removeSession(s.session_id);
                        setConfirmDelete(null);
                        if (on) router.push("/chat");
                      }} onMouseLeave={() => setConfirmDelete(null)}>
                      Delete?
                    </button>
                  ) : (
                    <button className="absolute right-1.5 top-2 hidden rounded p-0.5 group-hover:block" title="Delete conversation"
                      onClick={() => setConfirmDelete(s.session_id)}>
                      <Trash2 size={13} className="muted" />
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        ))}
      </div>

      <div className="border-t p-3" style={{ borderColor: "var(--border)" }}>
        <div className="flex items-center gap-2.5 rounded-xl p-2">
          <div className="grid h-9 w-9 shrink-0 place-items-center rounded-full text-[13px] font-semibold"
            style={{ background: "var(--accent-soft)", color: "var(--accent-text)" }}>{initials}</div>
          <Link href="/profile" onClick={onNavigate} className="min-w-0 flex-1 leading-tight" title="Open profile">
            <div className="truncate text-[13.5px] font-semibold hover:underline">{profile.full_name}</div>
            <div className="muted mt-0.5 flex items-center gap-1.5 text-[11.5px]">
              {profile.employee_id} · {profile.region} <RoleBadge role={profile.role} />
            </div>
          </Link>
          <button className="btn btn-ghost !p-2" title="Sign out" onClick={() => { logout(); router.replace("/login"); }}>
            <LogOut size={16} />
          </button>
        </div>
      </div>
    </div>
  );
}
