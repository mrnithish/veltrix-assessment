"use client";

import { ChevronDown, FileText, Lock, MessageSquareText, Search } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { EmptyState, ErrorNote, Page, PageHeader, SkeletonRows, formatDate } from "@/components/ui";
import { api, type DocumentInfo } from "@/lib/api";
import { useAuth } from "@/lib/auth";

const TYPE_LABEL: Record<string, string> = {
  policy: "Policy", addendum: "Regional addendum", memo: "Memo", handbook: "Handbook", calendar: "Calendar",
  faq: "FAQ", wiki: "Wiki",
};

export default function DocumentsPage() {
  const { profile } = useAuth();
  const [docs, setDocs] = useState<DocumentInfo[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [type, setType] = useState("all");
  const [open, setOpen] = useState<string | null>(null);

  useEffect(() => {
    api.documents().then((d) => setDocs(d.documents)).catch((e) => setError(e.message));
  }, []);

  const types = useMemo(() => ["all", ...Array.from(new Set((docs ?? []).map((d) => d.doc_type)))], [docs]);
  const shown = (docs ?? []).filter((d) => (type === "all" || d.doc_type === type)
    && `${d.title} ${d.doc_id} ${d.sections.join(" ")}`.toLowerCase().includes(query.toLowerCase()));
  const inEffect = shown.filter((d) => d.status === "in_effect");
  const upcoming = shown.filter((d) => d.status === "upcoming");

  const card = (d: DocumentInfo) => (
    <div key={d.doc_id} className="card overflow-hidden">
      <button className="flex w-full items-start gap-3 p-4 text-left" onClick={() => setOpen(open === d.doc_id ? null : d.doc_id)}>
        <span className="mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-lg" style={{ background: "var(--panel-2)" }}>
          <FileText size={16} style={{ color: d.authoritative ? "var(--accent)" : "var(--muted)" }} />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block text-[14px] font-semibold">{d.title}</span>
          <span className="mt-1 flex flex-wrap items-center gap-1.5">
            <span className="chip !py-0 !text-[11px]">{TYPE_LABEL[d.doc_type] ?? d.doc_type}</span>
            <span className="chip !py-0 !text-[11px]">{d.regions.join(", ")}</span>
            <span className="chip !py-0 !text-[11px]">from {formatDate(d.effective_date)}</span>
            {d.access_level !== "all" && <span className="chip !py-0 !text-[11px]"><Lock size={10} /> {d.access_level}</span>}
            {!d.authoritative && <span className="chip !py-0 !text-[11px]" style={{ color: "var(--warn)" }}>lower authority</span>}
          </span>
        </span>
        <span className="muted hidden font-mono text-[11px] sm:block">{d.doc_id}</span>
        <ChevronDown size={16} className="muted mt-1 transition-transform" style={{ transform: open === d.doc_id ? "rotate(180deg)" : "none" }} />
      </button>
      {open === d.doc_id && (
        <div className="border-t px-4 pb-4 pt-3" style={{ borderColor: "var(--border)" }}>
          <div className="muted mb-2 text-[12px] font-semibold uppercase tracking-wide">Sections</div>
          <div className="flex flex-wrap gap-1.5">
            {d.sections.map((s) => <span key={s} className="chip !text-[12px]">{s}</span>)}
          </div>
          <Link className="btn mt-4 !text-[12.5px]"
            href={`/chat?new=${Date.now()}&q=${encodeURIComponent(`What does "${d.title}" say about `)}`}>
            <MessageSquareText size={14} /> Ask about this document
          </Link>
        </div>
      )}
    </div>
  );

  return (
    <Page>
      <PageHeader title="Documents"
        subtitle={`HR documents you can read as ${profile?.role === "hr" ? "HR" : profile?.role} in ${profile?.region}. Restricted documents for other roles are not shown.`} />
      {error && <ErrorNote message={error} />}

      <div className="mb-5 flex flex-wrap gap-3">
        <div className="relative min-w-[240px] flex-1">
          <Search size={15} className="muted absolute left-3 top-1/2 -translate-y-1/2" />
          <input className="input !pl-9" placeholder="Search titles and sections" value={query} onChange={(e) => setQuery(e.target.value)} />
        </div>
        <select className="input !w-auto" value={type} onChange={(e) => setType(e.target.value)}>
          {types.map((t) => <option key={t} value={t}>{t === "all" ? "All types" : TYPE_LABEL[t] ?? t}</option>)}
        </select>
      </div>

      {!docs && !error && <div className="card"><SkeletonRows rows={6} /></div>}
      {docs && shown.length === 0 && <EmptyState icon={FileText} title="No documents match" />}

      {inEffect.length > 0 && (
        <>
          <h2 className="mb-2.5 text-[13px] font-semibold">In effect <span className="muted font-normal">· {inEffect.length}</span></h2>
          <div className="space-y-2.5">{inEffect.map(card)}</div>
        </>
      )}
      {upcoming.length > 0 && (
        <>
          <h2 className="mb-2.5 mt-7 text-[13px] font-semibold">Upcoming <span className="muted font-normal">· not yet in effect</span></h2>
          <div className="space-y-2.5">{upcoming.map(card)}</div>
        </>
      )}
      <div className="card mt-7 p-4 text-[13px]">
        <div className="font-semibold">How the assistant picks between documents</div>
        <p className="muted mt-1">
          A document counts only if your role can read it, it is for your region (or global), and it is in effect on the date you
          ask about. When documents disagree: policies, addenda, memos, handbooks and calendars outrank FAQs and wikis; then a
          regional document outranks a global one; then the newer one wins. Remaining ties are shown as conflicts.
        </p>
      </div>
    </Page>
  );
}
