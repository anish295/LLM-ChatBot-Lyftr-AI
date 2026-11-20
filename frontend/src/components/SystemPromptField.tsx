import { useEffect, useRef } from "react";

interface Props {
  value: string;
  onChange: (v: string) => void;
}

const PRESETS = [
  { label: "Pirate", text: "You are a cheerful pirate. Answer in pirate speak, briefly." },
  { label: "Teacher", text: "You are a patient teacher. Explain simply with one example." },
  { label: "Terse", text: "Answer in at most one sentence." },
];

/**
 * Always-visible, compact system-prompt bar above the composer (data-testid
 * "system-prompt-input"). Sent with each message; the backend stores it per session.
 */
export function SystemPromptField({ value, onChange }: Props) {
  const ref = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 96)}px`;
  }, [value]);

  return (
    <div className={`sp-bar ${value.trim() ? "sp-bar-active" : ""}`}>
      <label htmlFor="system-prompt" className="sp-label" title="Optional system prompt for this session">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="M12 3l2.2 4.6 5 .7-3.6 3.5.9 5-4.5-2.4-4.5 2.4.9-5L4.8 8.3l5-.7L12 3z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
        </svg>
        <span>System prompt</span>
      </label>
      <textarea
        id="system-prompt"
        ref={ref}
        data-testid="system-prompt-input"
        className="sp-input"
        rows={1}
        maxLength={4000}
        placeholder="Optional: e.g. “Answer like a pirate”. Applies to this session."
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
      <div className="sp-presets">
        {PRESETS.map((p) => (
          <button key={p.label} type="button" className="btn btn-sm btn-ghost" onClick={() => onChange(p.text)}>
            {p.label}
          </button>
        ))}
        {value && (
          <button type="button" className="btn btn-sm btn-ghost" onClick={() => onChange("")} aria-label="Clear system prompt">
            Clear
          </button>
        )}
      </div>
    </div>
  );
}
