"use client";

import { CalendarClock, ChevronDown, Clock3, LogOut, Menu, Settings, UserRound } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { RoleBadge } from "@/components/Badges";
import { formatDate } from "@/components/ui";
import { useAuth } from "@/lib/auth";

const TITLES: Record<string, string> = {
  "/chat": "Assistant", "/leave": "My leave", "/team": "My team", "/calendar": "Calendar", "/holidays": "Holidays",
  "/documents": "Documents", "/settings": "Settings", "/profile": "Profile", "/system": "Architecture & usage",
};

/** Live clock of the signed-in user's computer (local timezone). */
export function useNow(intervalMs = 1000) {
  const [now, setNow] = useState<Date | null>(null);
  useEffect(() => {
    setNow(new Date());
    const id = setInterval(() => setNow(new Date()), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);
  return now;
}

export function localDateISO(d: Date) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function TopBar({ onMenu }: { onMenu: () => void }) {
  const { profile, logout } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const now = useNow();
  const [open, setOpen] = useState(false);
  const menu = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const close = (e: MouseEvent) => { if (menu.current && !menu.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  if (!profile) return null;
  const tz = typeof Intl !== "undefined" ? Intl.DateTimeFormat().resolvedOptions().timeZone : "";
  const tzShort = now ? now.toLocaleTimeString("en-US", { timeZoneName: "short" }).split(" ").pop() : "";
  const localToday = now ? localDateISO(now) : profile.today;
  const assistantDiffers = profile.today !== localToday;
  const initials = profile.full_name.split(" ").map((p) => p[0]).slice(0, 2).join("");

  return (
    <header className="flex h-14 shrink-0 items-center gap-3 border-b px-3 sm:px-5" style={{ borderColor: "var(--border)", background: "var(--bg)" }}>
      <button className="btn btn-ghost !p-2 lg:hidden" onClick={onMenu} aria-label="Open menu"><Menu size={18} /></button>
      <h1 className="truncate text-[15px] font-semibold">{TITLES[pathname] ?? "Veltrix PeopleOps"}</h1>

      <div className="ml-auto flex items-center gap-2">
        {assistantDiffers && (
          <span className="chip hidden md:inline-flex" title="The assistant's 'today' (APP_TODAY / server date) differs from your computer's date"
            style={{ color: "var(--warn)", background: "var(--warn-soft)", borderColor: "transparent" }}>
            <CalendarClock size={13} /> Assistant date {formatDate(profile.today)}
          </span>
        )}
        <span className="chip hidden !py-1 sm:inline-flex" title={`Your computer's time · ${tz}`}>
          <Clock3 size={13} className="muted" />
          {now ? (
            <span className="tabular-nums">
              {now.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", year: "numeric" })}
              <span className="muted"> · </span>
              {now.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
              <span className="muted"> {tzShort}</span>
            </span>
          ) : "—"}
        </span>

        <div className="relative" ref={menu}>
          <button className="flex items-center gap-2 rounded-full border py-1 pl-1 pr-2.5 transition-colors hover:bg-[var(--panel-2)]"
            style={{ borderColor: "var(--border)" }} onClick={() => setOpen((o) => !o)} aria-expanded={open}>
            <span className="grid h-7 w-7 place-items-center rounded-full text-[11.5px] font-semibold"
              style={{ background: "var(--accent-soft)", color: "var(--accent-text)" }}>{initials}</span>
            <span className="hidden text-[13px] font-medium md:inline">{profile.full_name.split(" ")[0]}</span>
            <ChevronDown size={14} className="muted" />
          </button>
          {open && (
            <div className="card fade-up absolute right-0 z-30 mt-2 w-64 overflow-hidden !shadow-[var(--shadow-lg)]">
              <div className="border-b p-4" style={{ borderColor: "var(--border)" }}>
                <div className="text-[14px] font-semibold">{profile.full_name}</div>
                <div className="muted mt-0.5 text-[12px]">{profile.email}</div>
                <div className="mt-2 flex items-center gap-1.5 text-[12px]">
                  <span className="font-mono">{profile.employee_id}</span> · {profile.region} · {profile.level} <RoleBadge role={profile.role} />
                </div>
              </div>
              <div className="p-1.5">
                <Link href="/profile" onClick={() => setOpen(false)} className="flex items-center gap-2.5 rounded-lg px-3 py-2 text-[13.5px] hover:bg-[var(--panel-2)]">
                  <UserRound size={15} className="muted" /> Profile
                </Link>
                <Link href="/settings" onClick={() => setOpen(false)} className="flex items-center gap-2.5 rounded-lg px-3 py-2 text-[13.5px] hover:bg-[var(--panel-2)]">
                  <Settings size={15} className="muted" /> Settings
                </Link>
                <button onClick={() => { logout(); router.replace("/login"); }}
                  className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-[13.5px] hover:bg-[var(--panel-2)]" style={{ color: "var(--bad)" }}>
                  <LogOut size={15} /> Sign out
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
