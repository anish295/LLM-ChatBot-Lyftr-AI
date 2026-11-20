import { useEffect, useRef } from "react";

interface Props {
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
  busy: boolean;
}

const MAX = 4000;

export function Composer({ value, onChange, onSend, busy }: Props) {
  const ref = useRef<HTMLTextAreaElement>(null);

  // Auto-grow the textarea up to a max height.
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 220)}px`;
  }, [value]);

  useEffect(() => {
    if (!busy) ref.current?.focus();
  }, [busy]);

  const over = value.trim().length > MAX;

  return (
    <form
      className="composer"
      onSubmit={(e) => {
        e.preventDefault();
        if (!busy && value.length > 0) onSend();
      }}
    >
      <label htmlFor="chat-input" className="sr-only">
        Message
      </label>
      <textarea
        id="chat-input"
        ref={ref}
        data-testid="chat-input"
        className="composer-input"
        placeholder="Ask anything…  (Enter to send, Shift+Enter for a new line)"
        rows={1}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            if (!busy && value.length > 0) onSend();
          }
        }}
        aria-describedby="composer-hint"
      />
      <div className="composer-side">
        <span id="composer-hint" className={`char-count ${over ? "char-over" : ""}`} aria-live="polite">
          {value.trim().length}/{MAX}
        </span>
        <button
          type="submit"
          className="btn btn-primary send-btn"
          data-testid="send-button"
          disabled={busy || value.length === 0}
          aria-label="Send message"
        >
          {busy ? <span className="spinner" aria-hidden="true" /> : <SendIcon />}
          <span className="send-label">Send</span>
        </button>
      </div>
    </form>
  );
}

function SendIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M4 12l16-8-6 16-2.5-6.5L4 12z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
    </svg>
  );
}
