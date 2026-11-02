import type { Route } from "@/lib/api";

const ROUTE_STYLE: Record<Route, { label: string; fg: string; bg: string; hint: string }> = {
  rag: { label: "Documents", fg: "var(--accent-text)", bg: "var(--accent-soft)", hint: "Answered from HR documents" },
  tool: { label: "Leave data", fg: "var(--ok)", bg: "var(--ok-soft)", hint: "Answered from leave tools" },
  hybrid: { label: "Docs + leave data", fg: "var(--info)", bg: "var(--info-soft)",
    hint: "Combines documents and leave tools" },
  clarify: { label: "Needs details", fg: "var(--warn)", bg: "var(--warn-soft)", hint: "More information needed" },
  no_answer: { label: "Not covered", fg: "var(--muted)", bg: "var(--panel-2)", hint: "No eligible document answers this" },
  refuse: { label: "Declined", fg: "var(--bad)", bg: "var(--bad-soft)", hint: "Out of scope or not permitted" },
};

export function RouteBadge({ route, answer }: { route: Route; answer?: string }) {
  // The contract has no separate route for conversational replies (greetings, "who am I", today's date):
  // they use `clarify`. Label them by what they are when the reply is not a question.
  const conversational = route === "clarify" && answer !== undefined && !answer.includes("?");
  const s = conversational
    ? { label: "From your profile", fg: "var(--text-2)", bg: "var(--panel-2)", hint: "Answered from your HR record or the date" }
    : ROUTE_STYLE[route] ?? ROUTE_STYLE.no_answer;
  return (
    <span className="badge" style={{ color: s.fg, background: s.bg }} title={`route: ${route} — ${s.hint}`}>
      {s.label}
    </span>
  );
}

const STATUS_STYLE: Record<string, { fg: string; bg: string; label?: string }> = {
  success: { fg: "var(--ok)", bg: "var(--ok-soft)" },
  approved: { fg: "var(--ok)", bg: "var(--ok-soft)" },
  error: { fg: "var(--bad)", bg: "var(--bad-soft)" },
  cancelled: { fg: "var(--muted)", bg: "var(--panel-2)" },
  pending: { fg: "var(--warn)", bg: "var(--warn-soft)" },
  pending_confirmation: { fg: "var(--warn)", bg: "var(--warn-soft)", label: "awaiting confirmation" },
};

export function StatusBadge({ status }: { status: string }) {
  const s = STATUS_STYLE[status] ?? { fg: "var(--muted)", bg: "var(--panel-2)" };
  return (
    <span className="badge" style={{ color: s.fg, background: s.bg }}>
      {s.label ?? status.replaceAll("_", " ")}
    </span>
  );
}

const ROLE_STYLE: Record<string, { fg: string; bg: string }> = {
  employee: { fg: "var(--text-2)", bg: "var(--panel-2)" },
  manager: { fg: "var(--info)", bg: "var(--info-soft)" },
  hr: { fg: "var(--accent-text)", bg: "var(--accent-soft)" },
};

export function RoleBadge({ role }: { role: string }) {
  const s = ROLE_STYLE[role] ?? ROLE_STYLE.employee;
  return <span className="badge" style={{ color: s.fg, background: s.bg }}>{role === "hr" ? "HR" : role}</span>;
}
