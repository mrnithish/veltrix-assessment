"use client";

import { Check, Copy } from "lucide-react";
import { useState } from "react";

const KEYWORDS = new Set([
  "if", "elif", "else", "for", "while", "in", "not", "and", "or", "is", "try", "except", "finally", "return",
  "break", "continue", "pass", "True", "False", "None", "raise",
]);
const TOKEN = /(#[^\n]*)|("(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*')|(\b\d+(?:\.\d+)?\b)|([A-Za-z_][A-Za-z0-9_]*)(?=\s*\()|([A-Za-z_][A-Za-z0-9_]*)/g;

/** Tiny Python highlighter (comments, strings, numbers, calls, keywords) — enough for Code Mode programs. */
function highlight(code: string): React.ReactNode[] {
  const out: React.ReactNode[] = [];
  let last = 0;
  let i = 0;
  for (const m of code.matchAll(TOKEN)) {
    const idx = m.index ?? 0;
    if (idx > last) out.push(code.slice(last, idx));
    const [text, cmt, str, num, fn, word] = m;
    const cls = cmt ? "tok-cmt" : str ? "tok-str" : num ? "tok-num" : fn ? "tok-fn"
      : word && KEYWORDS.has(word) ? "tok-kw" : null;
    out.push(cls ? <span key={i++} className={cls}>{text}</span> : text);
    last = idx + text.length;
  }
  if (last < code.length) out.push(code.slice(last));
  return out;
}

export function CodeBlock({ code, title = "python" }: { code: string; title?: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="overflow-hidden rounded-xl border" style={{ borderColor: "var(--border)" }}>
      <div className="flex items-center justify-between px-3 py-1.5 text-[11.5px]"
        style={{ background: "var(--panel-3)", color: "var(--muted)" }}>
        <span className="font-mono">{title}</span>
        <button className="inline-flex items-center gap-1 hover:opacity-80" onClick={() => {
          navigator.clipboard?.writeText(code);
          setCopied(true);
          setTimeout(() => setCopied(false), 1200);
        }}>
          {copied ? <Check size={12} /> : <Copy size={12} />} {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre className="code !rounded-none">{highlight(code)}</pre>
    </div>
  );
}
