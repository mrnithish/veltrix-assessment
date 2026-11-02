"use client";

import { ArrowUp, Square } from "lucide-react";
import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";

export interface ComposerHandle {
  setText: (text: string) => void;
  focus: () => void;
}

export const Composer = forwardRef<ComposerHandle, {
  disabled: boolean; busy: boolean; onSend: (text: string) => void; onStop?: () => void; placeholder?: string;
  initial?: string;
}>(function Composer({ disabled, busy, onSend, onStop, placeholder, initial }, ref) {
  const [text, setText] = useState(initial ?? "");
  const area = useRef<HTMLTextAreaElement>(null);

  useImperativeHandle(ref, () => ({
    setText: (t: string) => {
      setText(t);
      requestAnimationFrame(() => {
        area.current?.focus();
        area.current?.setSelectionRange(t.length, t.length);
      });
    },
    focus: () => area.current?.focus(),
  }));

  useEffect(() => {
    const el = area.current;
    if (!el) return;
    el.style.height = "0px";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [text]);

  const submit = () => {
    const t = text.trim();
    if (!t || disabled || busy) return;
    onSend(t);
    setText("");
  };

  return (
    <div className="rounded-2xl border p-2 shadow-sm transition-shadow focus-within:shadow-md"
      style={{ borderColor: "var(--border-strong)", background: "var(--panel)" }}>
      <textarea ref={area} rows={1} value={text} disabled={disabled}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            submit();
          }
        }}
        placeholder={placeholder ?? "Ask about policies, holidays or your leave…"}
        className="block max-h-[200px] w-full resize-none bg-transparent px-2.5 py-2 text-[14.5px] outline-none"
        style={{ color: "var(--text)" }} />
      <div className="flex items-center justify-between px-1.5 pt-1">
        <span className="muted hidden text-[11.5px] sm:inline">Enter to send · Shift + Enter for a new line</span>
        {busy && onStop ? (
          <button className="btn !h-8 !w-8 !p-0" onClick={onStop} title="Stop"><Square size={14} /></button>
        ) : (
          <button className="btn btn-primary !h-8 !w-8 !rounded-full !p-0" onClick={submit}
            disabled={disabled || busy || !text.trim()} title="Send">
            <ArrowUp size={16} />
          </button>
        )}
      </div>
    </div>
  );
});
