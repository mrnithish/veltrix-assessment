"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/** Markdown answer. Inline "[DOC-ID, section]" references become small citation chips. */
export function Markdown({ text, docIds, titles }: {
  text: string; docIds: Set<string>; titles: Record<string, string>;
}) {
  const withChips = text.replace(/\[([A-Z0-9][A-Z0-9-]+)(?:,\s*([^\]\n]+))?\]/g, (whole, id: string, section?: string) =>
    docIds.has(id) ? `[${id}${section ? ` · ${section}` : ""}](#cite:${id})` : whole);
  return (
    <div className="prose-chat">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) => {
            if (href?.startsWith("#cite:")) {
              const id = href.slice(6);
              return (
                <span className="mx-0.5 inline-flex translate-y-[-1px] items-center rounded-md px-1.5 align-middle font-mono text-[11px]"
                  style={{ background: "var(--accent-soft)", color: "var(--accent-text)" }} title={titles[id] ?? id}>
                  {children}
                </span>
              );
            }
            return <a href={href} target="_blank" rel="noreferrer">{children}</a>;
          },
        }}
      >
        {withChips}
      </ReactMarkdown>
    </div>
  );
}
