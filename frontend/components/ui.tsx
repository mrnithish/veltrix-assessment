import type { LucideIcon } from "lucide-react";

export function Page({ children, wide }: { children: React.ReactNode; wide?: boolean }) {
  return (
    <div className="scroll-thin h-full overflow-y-auto">
      <div className={`mx-auto px-4 py-6 sm:px-8 sm:py-8 ${wide ? "max-w-6xl" : "max-w-5xl"}`}>{children}</div>
    </div>
  );
}

export function PageHeader({ title, subtitle, actions }: {
  title: string; subtitle?: React.ReactNode; actions?: React.ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-[22px] font-semibold tracking-tight">{title}</h1>
        {subtitle && <p className="muted mt-1 text-[13.5px]">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function StatCard({ label, value, hint, icon: Icon, tone = "accent" }: {
  label: string; value: React.ReactNode; hint?: React.ReactNode; icon: LucideIcon;
  tone?: "accent" | "ok" | "warn" | "info";
}) {
  const colors = {
    accent: ["var(--accent)", "var(--accent-soft)"],
    ok: ["var(--ok)", "var(--ok-soft)"],
    warn: ["var(--warn)", "var(--warn-soft)"],
    info: ["var(--info)", "var(--info-soft)"],
  }[tone];
  return (
    <div className="card p-5">
      <div className="flex items-center justify-between">
        <span className="muted text-[13px] font-medium">{label}</span>
        <span className="grid h-8 w-8 place-items-center rounded-lg" style={{ color: colors[0], background: colors[1] }}>
          <Icon size={16} />
        </span>
      </div>
      <div className="mt-3 text-[28px] font-semibold tracking-tight tabular-nums">{value}</div>
      {hint && <div className="muted mt-1 text-[12.5px]">{hint}</div>}
    </div>
  );
}

export function EmptyState({ icon: Icon, title, body, action }: {
  icon: LucideIcon; title: string; body?: React.ReactNode; action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-14 text-center">
      <span className="grid h-12 w-12 place-items-center rounded-2xl" style={{ background: "var(--panel-2)" }}>
        <Icon size={20} className="muted" />
      </span>
      <p className="mt-4 text-[14.5px] font-medium">{title}</p>
      {body && <p className="muted mt-1 max-w-md text-[13px]">{body}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorNote({ message }: { message: string }) {
  return (
    <div className="rounded-xl px-4 py-3 text-[13px]" style={{ background: "var(--bad-soft)", color: "var(--bad)" }}>
      {message}
    </div>
  );
}

export function SkeletonRows({ rows = 4 }: { rows?: number }) {
  return (
    <div className="space-y-3 p-5">
      {Array.from({ length: rows }).map((_, i) => <div key={i} className="skeleton h-9" />)}
    </div>
  );
}

export function Toggle({ checked, onChange, label, description }: {
  checked: boolean; onChange: (v: boolean) => void; label: string; description?: string;
}) {
  return (
    <label className="flex cursor-pointer items-start justify-between gap-6 py-3">
      <span>
        <span className="block text-[14px] font-medium">{label}</span>
        {description && <span className="muted mt-0.5 block text-[12.5px]">{description}</span>}
      </span>
      <button type="button" role="switch" aria-checked={checked} onClick={() => onChange(!checked)}
        className="relative mt-0.5 h-6 w-11 shrink-0 rounded-full transition-colors"
        style={{ background: checked ? "var(--accent)" : "var(--border-strong)" }}>
        <span className="absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform"
          style={{ left: 2, transform: checked ? "translateX(20px)" : "none" }} />
      </button>
    </label>
  );
}

export function formatDate(iso: string, opts: Intl.DateTimeFormatOptions = { day: "numeric", month: "short", year: "numeric" }) {
  const d = new Date(`${iso.slice(0, 10)}T00:00:00`);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString("en-GB", opts);
}

export function formatRange(start: string, end: string) {
  if (start === end) return formatDate(start);
  const s = new Date(`${start}T00:00:00`);
  const e = new Date(`${end}T00:00:00`);
  if (s.getFullYear() === e.getFullYear() && s.getMonth() === e.getMonth()) {
    return `${s.getDate()}–${formatDate(end)}`;
  }
  return `${formatDate(start, { day: "numeric", month: "short" })} – ${formatDate(end)}`;
}

export function relativeTime(iso: string) {
  const d = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : `${iso}Z`);
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)} min ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} h ago`;
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}
